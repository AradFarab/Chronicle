"""Delegating approval authority. Someone with people below them hands their approvals to
another person for a while; both can approve, and the request's history says who did."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from chronicle.db.models import ApprovalDelegation, Employee
from chronicle.i18n import _
from chronicle.jalali.dates import normalize_jdate
from chronicle.services import access, audit
from chronicle.services.errors import NotFound, PermissionDenied, ValidationError


def view(session: Session, d: ApprovalDelegation, today: str) -> dict[str, Any]:
	names = {
		e.id: e.full_name
		for e in session.query(Employee).filter(Employee.id.in_([d.delegator_id, d.delegate_id]))
	}
	return {
		"id": d.id,
		"delegator_id": d.delegator_id,
		"delegator_name": names.get(d.delegator_id),
		"delegate_id": d.delegate_id,
		"delegate_name": names.get(d.delegate_id),
		"valid_from": d.valid_from,
		"valid_to": d.valid_to,
		"note": d.note,
		"current": d.valid_from <= today and (d.valid_to is None or d.valid_to >= today),
	}


def create(session: Session, actor: access.Actor, values: dict[str, Any], today: str) -> ApprovalDelegation:
	delegator_id = (values.get("delegator_id") if actor.is_admin else None) or actor.employee_id
	if not delegator_id:
		raise ValidationError(_("Your user is not linked to an employee"))
	delegate_id = int(values["delegate_id"])
	for employee_id in (delegator_id, delegate_id):
		if session.get(Employee, employee_id) is None:
			raise NotFound(_("Employee not found"))
	if delegate_id == delegator_id:
		raise ValidationError(_("You cannot delegate to yourself"))
	if not access.subordinate_ids(session, delegator_id, today):
		raise ValidationError(_("Only someone with people below them can delegate their approvals"))
	valid_from = normalize_jdate(values.get("valid_from") or today)
	valid_to = normalize_jdate(values["valid_to"]) if values.get("valid_to") else None
	if valid_to and valid_to < valid_from:
		raise ValidationError(_("The end date is before the start date"))
	row = ApprovalDelegation(
		delegator_id=delegator_id,
		delegate_id=delegate_id,
		valid_from=valid_from,
		valid_to=valid_to,
		note=(values.get("note") or None),
	)
	session.add(row)
	session.flush()
	audit.log(
		session, "approval_delegation", row.id, "insert", actor.user_id, row.note, after=audit.snapshot(row)
	)
	return row


def remove(session: Session, actor: access.Actor, delegation_id: int) -> None:
	row = session.get(ApprovalDelegation, delegation_id)
	if row is None:
		raise NotFound(_("Not found"))
	if not (actor.is_admin or row.delegator_id == actor.employee_id):
		raise PermissionDenied(_("Not permitted"))
	audit.log(
		session, "approval_delegation", row.id, "delete", actor.user_id, None, before=audit.snapshot(row)
	)
	session.delete(row)
	session.flush()
