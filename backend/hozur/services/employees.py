"""Employees. Every employee is also a user: creating one creates the login (username and
password) in the same step, and a person who has left can no longer log in."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from hozur.db.models import AppUser, DesignationAssignment, Employee
from hozur.db.models.access import ADMIN, EMPLOYEE
from hozur.db.models.org import ACTIVE
from hozur.i18n import _
from hozur.services import audit, resources, users
from hozur.services.errors import NotFound, ValidationError

FIELDS = (
	"code",
	"detail_code",
	"first_name",
	"last_name",
	"national_id",
	"gender",
	"mobile",
	"email",
	"status",
	"contract_type",
	"start_date",
	"end_date",
	"work_location_id",
	"department_id",
	"overtime_consent_on_file",
	"overtime_consent_date",
	"birth_date",
	"biometric_consent_date",
	"uses_card_instead_of_biometrics",
	"nursing_until",
)


def get(session: Session, employee_id: int) -> Employee:
	employee = session.get(Employee, employee_id)
	if employee is None:
		raise NotFound(_("Employee not found"))
	return employee


def view(session: Session, employee: Employee, today: str) -> dict[str, Any]:
	"""The employee, their login and the designations they hold today."""
	out = audit.snapshot(employee)
	user = session.get(AppUser, employee.user_id)
	out["username"] = user.username
	out["is_admin"] = ADMIN in user.role_names
	out["is_active_user"] = user.is_active
	held = session.scalars(
		select(DesignationAssignment)
		.where(DesignationAssignment.employee_id == employee.id)
		.order_by(DesignationAssignment.valid_from.desc(), DesignationAssignment.id.desc())
	)
	out["designations"] = [
		{
			"assignment_id": a.id,
			"designation_id": a.designation_id,
			"valid_from": a.valid_from,
			"valid_to": a.valid_to,
			"current": a.valid_from <= today and (a.valid_to is None or a.valid_to >= today),
		}
		for a in held
	]
	return out


def _audit_view(session: Session, employee: Employee) -> dict[str, Any]:
	return {**audit.snapshot(employee), "username": session.get(AppUser, employee.user_id).username}


def save(ctx: resources.Context, values: dict[str, Any], employee_id: int | None = None) -> Employee:
	"""Create or change an employee and their login (system admin only).

	On create: `password` is required; `username` defaults to the personnel code; an optional
	`designation_id` (with `designation_from`, default the start date) gives the first
	designation. On change, `password` resets the password and `username` renames the login.
	`is_admin` makes the person a system admin."""
	resources.check(ctx.actor, resources.ADMIN)
	session = ctx.session
	employee = get(session, employee_id) if employee_id else Employee()
	before = _audit_view(session, employee) if employee_id else None
	for key in FIELDS:
		if key in values:
			setattr(employee, key, resources.coerce(Employee, key, values[key]))
	if not employee_id:
		if not (employee.code and employee.first_name and employee.last_name and employee.start_date):
			raise ValidationError(_("Enter the personnel code, the name and the start date"))
	resources._employee(ctx, employee, before)
	flags = {"is_admin": bool(values.get("is_admin"))} if "is_admin" in values else {}
	user = _save_user(session, employee, values, flags, new=not employee_id)
	if not employee_id:
		employee.user_id = user.id
		session.add(employee)
	resources.flush(session)
	user.full_name = employee.full_name
	if user.is_active != (employee.status == ACTIVE):
		user.is_active = employee.status == ACTIVE
		if not user.is_active:
			users.end_all_sessions(session, user.id)
	if not employee_id and values.get("designation_id"):
		session.add(
			DesignationAssignment(
				employee_id=employee.id,
				designation_id=int(values["designation_id"]),
				valid_from=resources.coerce(
					DesignationAssignment, "valid_from", values.get("designation_from") or employee.start_date
				),
			)
		)
	resources.flush(session)
	audit.log(
		session,
		"employee",
		employee.id,
		"update" if before else "insert",
		ctx.actor.user_id,
		(values.get("reason") or None),
		before,
		_audit_view(session, employee),
	)
	resources._employee_changed(ctx, employee, before)
	return employee


def _save_user(
	session: Session, employee: Employee, values: dict[str, Any], flags: dict[str, bool], new: bool
) -> AppUser:
	if new:
		username = (values.get("username") or employee.code or "").strip().lower()
		roles = [EMPLOYEE] + ([ADMIN] if flags.get("is_admin") else [])
		return users.create_user(
			session,
			username,
			f"{employee.first_name} {employee.last_name}",
			values.get("password"),
			roles,
			require_password=True,
		)
	user = session.get(AppUser, employee.user_id)
	if values.get("username") and values["username"].strip().lower() != user.username:
		taken = session.scalar(
			select(AppUser.id).where(AppUser.username == values["username"].strip().lower())
		)
		if taken:
			raise ValidationError(_("The username {0} is taken"), values["username"])
		user.username = values["username"].strip().lower()
	if values.get("password"):
		user.password_hash = users.hash_password(values["password"])
		users.end_all_sessions(session, user.id)
	if "is_admin" in flags:
		roles = {EMPLOYEE} | ({ADMIN} if flags["is_admin"] else set())
		users.update_user(session, user, {"roles": sorted(roles)}, None)
	return user
