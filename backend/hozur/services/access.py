"""Who is acting, and whom they may see (CLAUDE.md rule 8: role plus designation subtree).

The organization is the designation tree. A person's "parent" is whoever holds the nearest
filled designation above theirs; their "subordinates" are everyone holding a designation below
a designation they hold. So:

- the system admin and the CEO (holder of the CEO designation) see everyone;
- a manager sees themself and everyone below their designations (and below the designations of
  people who delegated their authority to them);
- everybody else sees themself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from hozur.clock import today_jalali
from hozur.db.models import (
	ApprovalDelegation,
	AppUser,
	Designation,
	DesignationAssignment,
	Employee,
)
from hozur.db.models.access import ADMIN
from hozur.db.models.org import ACTIVE
from hozur.i18n import _
from hozur.services.errors import PermissionDenied


@dataclass(frozen=True)
class Actor:
	user_id: int | None
	employee_id: int | None = None
	roles: frozenset[str] = field(default_factory=frozenset)
	language: str = "fa"
	is_ceo: bool = False  # holds the CEO designation today

	@property
	def is_admin(self) -> bool:
		return ADMIN in self.roles

	@property
	def sees_all(self) -> bool:
		return self.is_admin or self.is_ceo


# Jobs, the CLI and install run as the system.
SYSTEM = Actor(user_id=None, roles=frozenset({ADMIN}))


def actor_for(session: Session, user: AppUser, today: str | None = None) -> Actor:
	employee_id = session.scalar(select(Employee.id).where(Employee.user_id == user.id))
	today = today or today_jalali()
	return Actor(
		user_id=user.id,
		employee_id=employee_id,
		roles=frozenset(user.role_names),
		language=user.language,
		is_ceo=bool(employee_id) and employee_id in ceo_ids(session, today),
	)


# the designation tree ---------------------------------------------------------------------------


def _active(column_from, column_to, today: str):
	return (column_from <= today) & (column_to.is_(None) | (column_to >= today))


def _working(today: str):
	"""Employees who can act today: active and inside their employment dates."""
	return (
		(Employee.status == ACTIVE)
		& (Employee.start_date <= today)
		& (Employee.end_date.is_(None) | (Employee.end_date >= today))
	)


def designations_on(session: Session, employee_id: int, today: str) -> list[int]:
	"""The designations a person holds today, oldest assignment first."""
	return list(
		session.scalars(
			select(DesignationAssignment.designation_id)
			.where(
				DesignationAssignment.employee_id == employee_id,
				_active(DesignationAssignment.valid_from, DesignationAssignment.valid_to, today),
			)
			.order_by(DesignationAssignment.valid_from, DesignationAssignment.id)
		)
	)


def holders(session: Session, designation_ids: set[int] | list[int], today: str) -> list[int]:
	"""Working employees who hold any of the designations today."""
	if not designation_ids:
		return []
	return sorted(
		set(
			session.scalars(
				select(DesignationAssignment.employee_id)
				.join(Employee, Employee.id == DesignationAssignment.employee_id)
				.where(
					DesignationAssignment.designation_id.in_(list(designation_ids)),
					_active(DesignationAssignment.valid_from, DesignationAssignment.valid_to, today),
					_working(today),
				)
			)
		)
	)


def descendants(session: Session, roots: set[int]) -> set[int]:
	"""The designations and everything below them (recursive CTE)."""
	if not roots:
		return set()
	tree = select(Designation.id).where(Designation.id.in_(roots)).cte("tree", recursive=True)
	tree = tree.union(select(Designation.id).where(Designation.parent_id == tree.c.id))
	return set(session.scalars(select(tree.c.id)))


def ancestors(session: Session, designation_id: int | None) -> list[int]:
	"""The designations above this one, nearest first (not including it)."""
	out: list[int] = []
	seen = {designation_id}
	current = session.scalar(select(Designation.parent_id).where(Designation.id == designation_id))
	while current and current not in seen:
		out.append(current)
		seen.add(current)
		current = session.scalar(select(Designation.parent_id).where(Designation.id == current))
	return out


def ceo_designation_id(session: Session) -> int | None:
	return session.scalar(select(Designation.id).where(Designation.is_ceo))


def ceo_ids(session: Session, today: str) -> list[int]:
	ceo = ceo_designation_id(session)
	return holders(session, {ceo}, today) if ceo else []


def parent_approvers(session: Session, employee_id: int, today: str) -> list[int]:
	"""The people who approve this person's requests: for each designation they hold, the
	holders of the nearest filled designation above it. Someone with nobody above them reports
	to the CEO. The CEO has no parent."""
	own = designations_on(session, employee_id, today)
	found: set[int] = set()
	for d in own:
		for above in ancestors(session, d):
			people = [e for e in holders(session, {above}, today) if e != employee_id]
			if people:
				found.update(people)
				break
	if not found:
		found.update(e for e in ceo_ids(session, today) if e != employee_id)
	return sorted(found)


# delegation ------------------------------------------------------------------------------------


def delegators_of(session: Session, employee_id: int, today: str) -> list[int]:
	"""The people whose approval authority this person holds today."""
	return list(
		session.scalars(
			select(ApprovalDelegation.delegator_id).where(
				ApprovalDelegation.delegate_id == employee_id,
				_active(ApprovalDelegation.valid_from, ApprovalDelegation.valid_to, today),
			)
		)
	)


def acting_employee_ids(session: Session, employee_id: int | None, today: str) -> set[int]:
	"""Whom this person can approve as: themself and everyone who delegated to them."""
	if not employee_id:
		return set()
	return {employee_id, *delegators_of(session, employee_id, today)}


def acting_user_ids(session: Session, employee_id: int | None, today: str) -> set[int]:
	ids = acting_employee_ids(session, employee_id, today)
	return set(session.scalars(select(Employee.user_id).where(Employee.id.in_(ids)))) if ids else set()


# visibility -------------------------------------------------------------------------------------


def subordinate_ids(session: Session, employee_id: int | None, today: str) -> set[int]:
	"""Everyone below the designations this person (or someone who delegated to them) holds."""
	people = acting_employee_ids(session, employee_id, today)
	own: set[int] = set()
	for e in people:
		own.update(designations_on(session, e, today))
	if not own:
		return set()
	below = descendants(session, own) - own
	return {e for e in holders(session, below, today)} - people


def visible_employee_ids(session: Session, actor: Actor, today: str) -> set[int] | None:
	"""Employee ids the actor may see, or None for everyone."""
	if actor.sees_all:
		return None
	if not actor.employee_id:
		return set()
	return {actor.employee_id} | subordinate_ids(session, actor.employee_id, today)


def can_see(session: Session, actor: Actor, employee_id: int, today: str) -> bool:
	visible = visible_employee_ids(session, actor, today)
	return visible is None or employee_id in visible


def assert_can_see(session: Session, actor: Actor, employee_id: int, today: str) -> None:
	if not can_see(session, actor, employee_id, today):
		raise PermissionDenied(_("Not permitted"))


def is_manager(session: Session, actor: Actor, today: str) -> bool:
	if actor.sees_all:
		return True
	return bool(actor.employee_id) and bool(subordinate_ids(session, actor.employee_id, today))


def user_of(session: Session, employee_id: int | None) -> int | None:
	if not employee_id:
		return None
	return session.scalar(select(Employee.user_id).where(Employee.id == employee_id))
