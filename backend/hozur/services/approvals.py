"""Data-driven approval (CLAUDE.md rule 6).

An approval process is an ordered list of steps; each step is resolved to a person when the
request is submitted (direct manager, manager of the parent department, the CEO or a
specific person) and copied onto the request, so changing a process only affects new
requests. A process with no steps approves on submit. Every request type has a default
process, any employee can have a per-type override, and requests an operator enters for
someone else can have their own default. There are no numeric conditions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from hozur.db.models import ApprovalDefault, ApprovalOverride, ApprovalProcess, Request, RequestApproval
from hozur.db.models.requests import (
	APPROVED,
	CEO,
	DIRECT_MANAGER,
	OPERATOR_ENTRY,
	PARENT_DEPARTMENT_MANAGER,
	PENDING,
	SKIPPED,
	SPECIFIC_PERSON,
)
from hozur.i18n import _
from hozur.services import access
from hozur.services.errors import ValidationError


def process_for(
	session: Session, employee_id: int, request_type: str, entered_by_operator: bool
) -> ApprovalProcess:
	override = session.scalar(
		select(ApprovalOverride.process_id).where(
			ApprovalOverride.employee_id == employee_id, ApprovalOverride.request_type == request_type
		)
	)
	process_id = override
	if process_id is None and entered_by_operator:
		process_id = session.scalar(
			select(ApprovalDefault.process_id).where(ApprovalDefault.request_type == OPERATOR_ENTRY)
		)
	if process_id is None:
		process_id = session.scalar(
			select(ApprovalDefault.process_id).where(ApprovalDefault.request_type == request_type)
		)
	if process_id is None:
		raise ValidationError(_("No approval process is set for {0}"), request_type)
	return session.get(ApprovalProcess, process_id)


def resolve_approver(
	session: Session, approver_type: str, approver_id: int | None, employee_id: int, today: str
) -> int | None:
	if approver_type == DIRECT_MANAGER:
		return access.direct_manager(session, employee_id, today)
	if approver_type == PARENT_DEPARTMENT_MANAGER:
		return access.parent_department_manager(session, employee_id, today)
	if approver_type == CEO:
		return access.ceo_id(session)
	if approver_type == SPECIFIC_PERSON:
		return approver_id
	raise ValidationError(_("Unknown approver type {0}"), approver_type)


def build_chain(session: Session, request: Request, process: ApprovalProcess, today: str) -> None:
	"""Copy the process onto the request, resolving every step to a person. Nobody approves
	their own request: such steps are skipped."""
	employee_user = access.user_of(session, request.employee_id)
	request.approval_process_id = process.id
	request.approvals = []
	for step in process.steps:
		approver = resolve_approver(session, step.approver_type, step.approver_id, request.employee_id, today)
		if approver is None:
			raise ValidationError(
				_("No approver found for step {0} ({1}). Set the manager of the department or the CEO."),
				step.position,
				step.approver_type,
			)
		user = access.user_of(session, approver)
		if approver != request.employee_id and not user:
			raise ValidationError(_("The approver of step {0} has no user account"), step.position)
		own = approver == request.employee_id or (user is not None and user == employee_user)
		request.approvals.append(
			RequestApproval(
				step=step.position,
				approver_type=step.approver_type,
				approver_id=approver,
				approver_user_id=user,
				status=SKIPPED if own else PENDING,
			)
		)
	request.status = PENDING
	advance(request)


def current_step(request: Request) -> RequestApproval | None:
	return next((a for a in request.approvals if a.status == PENDING), None)


def advance(request: Request) -> None:
	"""Mirror the next pending step on the request, or approve it when none is left."""
	step = current_step(request)
	if step:
		request.pending_approver_id, request.pending_approver_user_id = (
			step.approver_id,
			step.approver_user_id,
		)
	else:
		request.pending_approver_id = request.pending_approver_user_id = None
		request.status = APPROVED
		request.decided_at = datetime.now(UTC)


def can_act(actor: access.Actor, request: Request) -> bool:
	"""The approver of the current step. An admin can act for an unavailable approver; the
	audit entry records who really acted."""
	step = current_step(request)
	return (
		bool(step)
		and request.status == PENDING
		and (step.approver_user_id == actor.user_id or actor.is_admin)
	)


def in_chain(actor: access.Actor, request: Request) -> bool:
	return actor.user_id is not None and any(a.approver_user_id == actor.user_id for a in request.approvals)
