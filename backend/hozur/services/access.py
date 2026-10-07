"""Who is acting, and whom they may see (CLAUDE.md rule 8: role plus department subtree).

- admin, operator and ceo see everyone;
- a manager sees their direct reports and everyone in the departments they manage (or act
  for as deputy today), including all sub-departments;
- everybody sees themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import literal, or_, select
from sqlalchemy.orm import Session

from hozur.db.models import AppUser, Department, Employee, Organization
from hozur.db.models.access import ADMIN, CEO, MANAGER, OPERATOR
from hozur.i18n import _
from hozur.services.errors import PermissionDenied

ALL_ACCESS = frozenset({ADMIN, OPERATOR, CEO})


@dataclass(frozen=True)
class Actor:
	user_id: int | None
	employee_id: int | None = None
	roles: frozenset[str] = field(default_factory=frozenset)
	language: str = "fa"

	@property
	def is_admin(self) -> bool:
		return ADMIN in self.roles

	@property
	def is_operator(self) -> bool:
		return bool({ADMIN, OPERATOR} & self.roles)

	@property
	def sees_all(self) -> bool:
		return bool(ALL_ACCESS & self.roles)


# Jobs, the CLI and install run as the system.
SYSTEM = Actor(user_id=None, roles=frozenset({ADMIN}))


def actor_for(session: Session, user: AppUser) -> Actor:
	employee_id = session.scalar(select(Employee.id).where(Employee.user_id == user.id))
	return Actor(
		user_id=user.id, employee_id=employee_id, roles=frozenset(user.role_names), language=user.language
	)


# the department tree -----------------------------------------------------------------------


def subtree(session: Session, roots: set[int]) -> set[int]:
	"""The departments and all their descendants (recursive CTE)."""
	if not roots:
		return set()
	tree = select(Department.id).where(Department.id.in_(roots)).cte("tree", recursive=True)
	tree = tree.union(select(Department.id).where(Department.parent_id == tree.c.id))
	return set(session.scalars(select(tree.c.id)))


def ancestors(session: Session, department_id: int | None) -> list[int]:
	"""The department and its parents, nearest first."""
	out: list[int] = []
	seen: set[int] = set()
	while department_id and department_id not in seen:
		out.append(department_id)
		seen.add(department_id)
		department_id = session.scalar(select(Department.parent_id).where(Department.id == department_id))
	return out


def _deputy_active(d: Department, today: str) -> bool:
	return (
		bool(d.deputy_id)
		and bool(d.deputy_from)
		and d.deputy_from <= today
		and (not d.deputy_to or today <= d.deputy_to)
	)


def acting_manager(session: Session, department_id: int | None, today: str) -> int | None:
	"""The department's manager, or its deputy while the deputy period covers today."""
	if not department_id:
		return None
	d = session.get(Department, department_id)
	if d is None:
		return None
	return d.deputy_id if _deputy_active(d, today) else d.manager_id


def managed_departments(session: Session, employee_id: int, today: str) -> set[int]:
	rows = session.scalars(
		select(Department).where(
			or_(Department.manager_id == employee_id, Department.deputy_id == employee_id)
		)
	)
	roots = {
		d.id
		for d in rows
		if (d.manager_id == employee_id and not _deputy_active(d, today))
		or (d.deputy_id == employee_id and _deputy_active(d, today))
	}
	return subtree(session, roots)


def visible_employee_ids(session: Session, actor: Actor, today: str) -> set[int] | None:
	"""Employee ids the actor may see, or None for everyone."""
	if actor.sees_all:
		return None
	if not actor.employee_id:
		return set()
	ids = {actor.employee_id}
	ids.update(session.scalars(select(Employee.id).where(Employee.reports_to_id == actor.employee_id)))
	departments = managed_departments(session, actor.employee_id, today)
	if departments:
		ids.update(session.scalars(select(Employee.id).where(Employee.department_id.in_(departments))))
	return ids


def can_see(session: Session, actor: Actor, employee_id: int, today: str) -> bool:
	visible = visible_employee_ids(session, actor, today)
	return visible is None or employee_id in visible


def assert_can_see(session: Session, actor: Actor, employee_id: int, today: str) -> None:
	if not can_see(session, actor, employee_id, today):
		raise PermissionDenied(_("Not permitted"))


def is_manager(session: Session, actor: Actor, today: str) -> bool:
	if MANAGER in actor.roles or actor.sees_all:
		return True
	visible = visible_employee_ids(session, actor, today)
	return visible is None or len(visible) > 1


# approvers ----------------------------------------------------------------------------------


def _manager_above(session: Session, employee_id: int, department_id: int | None, today: str) -> int | None:
	"""Walk up the tree to the first acting manager who is not the employee."""
	for dep in ancestors(session, department_id):
		manager = acting_manager(session, dep, today)
		if manager and manager != employee_id:
			return manager
	return None


def direct_manager(session: Session, employee_id: int, today: str) -> int | None:
	"""reports_to, else the department's manager; a manager's direct manager is the manager of
	the department above (design doc, approval section)."""
	emp = session.get(Employee, employee_id)
	if emp is None:
		return None
	if emp.reports_to_id and emp.reports_to_id != employee_id:
		return emp.reports_to_id
	return _manager_above(session, employee_id, emp.department_id, today)


def parent_department_manager(session: Session, employee_id: int, today: str) -> int | None:
	emp = session.get(Employee, employee_id)
	if emp is None or not emp.department_id:
		return None
	direct = direct_manager(session, employee_id, today)
	chain = ancestors(session, emp.department_id)[1:]
	for i, dep in enumerate(chain):
		manager = acting_manager(session, dep, today)
		if manager and manager != employee_id:
			if manager == direct:
				# the direct manager already runs this department: go one level higher
				return _manager_above(
					session, employee_id, chain[i + 1] if i + 1 < len(chain) else None, today
				)
			return manager
	return None


def ceo_id(session: Session) -> int | None:
	return session.scalar(select(Organization.ceo_id).where(Organization.id == literal(1)))


def user_of(session: Session, employee_id: int | None) -> int | None:
	if not employee_id:
		return None
	return session.scalar(select(Employee.user_id).where(Employee.id == employee_id))
