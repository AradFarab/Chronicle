"""Employees (who are also users) and the delegation of approval authority."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Admin, Today
from hozur.db.models import ApprovalDelegation, Employee
from hozur.i18n import _
from hozur.services import access, delegations, employees, resources
from hozur.services.errors import NotFound, PermissionDenied

router = APIRouter(prefix="/api", tags=["people"])


def _ctx(db, actor, today) -> resources.Context:
	return resources.Context(db, actor, today)


# employees -------------------------------------------------------------------------------------


@router.get("/admin/employees")
def list_employees(actor: Actor, db: DB, today: Today) -> list[dict]:
	"""The employees this user may see (everyone for the admin and the CEO)."""
	visible = access.visible_employee_ids(db, actor, today)
	query = select(Employee).order_by(Employee.code)
	if visible is not None:
		query = query.where(Employee.id.in_(visible or {0}))
	return [employees.view(db, e, today) for e in db.scalars(query)]


@router.get("/people/active")
def active_people(actor: Actor, db: DB, today: Today) -> list[dict]:
	"""Everyone who works here now (id, code, name): the pick-list for handing approvals to
	someone. Only for those who can delegate, since it shows people outside their own team."""
	if not (actor.is_admin or access.is_manager(db, actor, today)):
		raise PermissionDenied(_("Not permitted"))
	rows = db.execute(
		select(Employee.id, Employee.code, Employee.full_name)
		.where(Employee.status == "active", Employee.start_date <= today)
		.order_by(Employee.code)
	)
	return [{"id": i, "code": c, "full_name": n, "status": "active"} for i, c, n in rows]


@router.get("/admin/employees/{employee_id:int}")
def get_employee(employee_id: int, actor: Actor, db: DB, today: Today) -> dict:
	if not access.can_see(db, actor, employee_id, today):
		raise NotFound(_("Employee not found"))
	return employees.view(db, employees.get(db, employee_id), today)


@router.post("/admin/employees")
def create_employee(values: dict[str, Any], actor: Admin, db: DB, today: Today) -> dict:
	employee = employees.save(_ctx(db, actor, today), values)
	return employees.view(db, employee, today)


@router.patch("/admin/employees/{employee_id:int}")
def update_employee(employee_id: int, values: dict[str, Any], actor: Admin, db: DB, today: Today) -> dict:
	employee = employees.save(_ctx(db, actor, today), values, employee_id)
	return employees.view(db, employee, today)


# delegation ------------------------------------------------------------------------------------


class Delegation(BaseModel):
	delegate_id: int
	valid_from: str | None = None
	valid_to: str | None = None
	note: str | None = None
	delegator_id: int | None = None  # the system admin may set it for someone else


@router.get("/delegations")
def list_delegations(actor: Actor, db: DB, today: Today) -> list[dict]:
	"""Delegations you gave or received (all of them for the system admin)."""
	query = select(ApprovalDelegation).order_by(
		ApprovalDelegation.valid_from.desc(), ApprovalDelegation.id.desc()
	)
	if not actor.is_admin:
		me = actor.employee_id or 0
		query = query.where((ApprovalDelegation.delegator_id == me) | (ApprovalDelegation.delegate_id == me))
	return [delegations.view(db, d, today) for d in db.scalars(query)]


@router.post("/delegations")
def create_delegation(body: Delegation, actor: Actor, db: DB, today: Today) -> dict:
	row = delegations.create(db, actor, body.model_dump(), today)
	return delegations.view(db, row, today)


@router.delete("/delegations/{delegation_id}")
def end_delegation(delegation_id: int, actor: Actor, db: DB, today: Today) -> dict:
	delegations.remove(db, actor, delegation_id)
	return {"ok": True}
