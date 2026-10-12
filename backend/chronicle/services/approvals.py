"""Data-driven approval (CLAUDE.md rule 6).

An approval process is an ordered list of steps. Each step is resolved to people when the
request is submitted and copied onto the request, so changing a process only affects new
requests:

- ``parent``: whoever holds the nearest filled designation above the requester;
- ``ceo``: whoever holds the CEO designation;
- ``specific_person``: a named person (custom processes).

Any one person of a step (or someone they delegated to) can decide it. Nobody approves their
own request, and a step whose people already had their turn is skipped, so "parent, then CEO"
is a single approval by the CEO when the CEO is the requester's parent. The CEO has no parent:
their own requests need no approval. A process with no steps approves on submit. There are no
numeric conditions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronicle.db.models import (
	ApprovalDefault,
	ApprovalOverride,
	ApprovalProcess,
	Employee,
	Request,
	RequestApproval,
	RequestApprovalApprover,
)
from chronicle.db.models.requests import (
	ADMIN_ENTRY,
	APPROVED,
	CEO,
	PARENT,
	PENDING,
	SKIPPED,
	SPECIFIC_PERSON,
)
from chronicle.i18n import _
from chronicle.services import access
from chronicle.services.errors import ValidationError


def process_for(
	session: Session, employee_id: int, request_type: str, entered_by_admin: bool
) -> ApprovalProcess:
	override = session.scalar(
		select(ApprovalOverride.process_id).where(
			ApprovalOverride.employee_id == employee_id, ApprovalOverride.request_type == request_type
		)
	)
	process_id = override
	if process_id is None and entered_by_admin:
		process_id = session.scalar(
			select(ApprovalDefault.process_id).where(ApprovalDefault.request_type == ADMIN_ENTRY)
		)
	if process_id is None:
		process_id = session.scalar(
			select(ApprovalDefault.process_id).where(ApprovalDefault.request_type == request_type)
		)
	if process_id is None:
		raise ValidationError(_("No approval process is set for {0}"), request_type)
	return session.get(ApprovalProcess, process_id)


def resolve_step(
	session: Session, approver_type: str, approver_id: int | None, employee_id: int, today: str
) -> list[int]:
	"""The people a step resolves to for this requester (the requester removed)."""
	if approver_type == PARENT:
		people = access.parent_approvers(session, employee_id, today)
	elif approver_type == CEO:
		people = access.ceo_ids(session, today)
	elif approver_type == SPECIFIC_PERSON:
		people = [approver_id] if approver_id else []
	else:
		raise ValidationError(_("Unknown approver type {0}"), approver_type)
	return [p for p in people if p != employee_id]


def _approvers(session: Session, people: list[int]) -> list[RequestApprovalApprover]:
	users = dict(session.execute(select(Employee.id, Employee.user_id).where(Employee.id.in_(people))).all())
	return [RequestApprovalApprover(employee_id=e, user_id=users[e]) for e in people]


def build_chain(session: Session, request: Request, process: ApprovalProcess, today: str) -> None:
	"""Copy the process onto the request, resolving every step to people."""
	requester_is_ceo = request.employee_id in access.ceo_ids(session, today)
	request.approval_process_id = process.id
	request.approvals = []
	covered: set[int] = set()
	for step in process.steps:
		people = resolve_step(session, step.approver_type, step.approver_id, request.employee_id, today)
		if not people and not requester_is_ceo and step.approver_type != SPECIFIC_PERSON:
			raise ValidationError(
				_(
					"No approver found for step {0}. Hang the employee under a designation that someone holds."
				),
				step.position,
			)
		already = bool(people) and set(people) <= covered
		skipped = not people or already
		request.approvals.append(
			RequestApproval(
				step=step.position,
				approver_type=step.approver_type,
				approvers=[] if skipped and not people else _approvers(session, people),
				status=SKIPPED if skipped else PENDING,
			)
		)
		covered.update(people)
	request.status = PENDING
	advance(request)


def current_step(request: Request) -> RequestApproval | None:
	return next((a for a in request.approvals if a.status == PENDING), None)


def advance(request: Request) -> None:
	"""Approve the request when no step is left pending."""
	if current_step(request) is None:
		request.status = APPROVED
		request.decided_at = datetime.now(UTC)


def can_act_on_step(session: Session, actor: access.Actor, step: RequestApproval | None, today: str) -> bool:
	"""One of the step's approvers, someone they delegated to, or the system admin (the audit
	entry records who really acted)."""
	if step is None or step.status != PENDING:
		return False
	if actor.is_admin:
		return True
	acting = access.acting_employee_ids(session, actor.employee_id, today)
	return any(a.employee_id in acting for a in step.approvers)


def can_act(session: Session, actor: access.Actor, request: Request, today: str) -> bool:
	return request.status == PENDING and can_act_on_step(session, actor, current_step(request), today)


def in_chain(session: Session, actor: access.Actor, request: Request, today: str) -> bool:
	acting = access.acting_employee_ids(session, actor.employee_id, today)
	return any(p.employee_id in acting for a in request.approvals for p in a.approvers)


def waiting_for(request: Request) -> list[int]:
	"""The people the current step waits for."""
	step = current_step(request)
	return [a.employee_id for a in step.approvers] if step else []
