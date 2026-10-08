"""Requests ("forms") and their life cycle ("processes").

One flow for every kind: validate the form, check who may file it, copy the approval
process onto it, then approve / reject step by step, or cancel. Approval and cancellation
have side effects: leave usage in the ledger and recalculation of the days involved.
Everything is audited; nothing inside a closed period changes (rule 9).
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from hozur.db.models import (
	CorrectionItem,
	Employee,
	LeaveRequest,
	LeaveType,
	MissionRequest,
	OvertimeRequest,
	Request,
)
from hozur.db.models.requests import (
	ADD_PUNCH,
	APPROVED,
	CANCELLED,
	CORRECTION,
	CORRECTION_TYPE,
	DAILY,
	DAILY_LEAVE,
	EMPLOYEE_ACCEPTANCE,
	HOURLY,
	HOURLY_LEAVE,
	IGNORE_PUNCH,
	LEAVE,
	MISSION,
	MISSION_TYPE,
	OVERTIME,
	OVERTIME_KINDS,
	OVERTIME_TYPE,
	PENDING,
	REJECTED,
	RequestApproval,
)
from hozur.i18n import _
from hozur.jalali.dates import InvalidJalaliDate, iter_days, normalize_jdate, normalize_time
from hozur.services import access, approvals, audit, jobs, leave, settings
from hozur.services.errors import NotFound, PermissionDenied, ValidationError
from hozur.services.periods import assert_open
from hozur.services.punches import employee_raw_punches
from hozur.services.rule_sets import rule_set_for

APPROVE, REJECT = "approve", "reject"


# input helpers --------------------------------------------------------------------------


def _jdate(value, label: str) -> str:
	try:
		return normalize_jdate(str(value or ""))
	except (InvalidJalaliDate, ValueError):
		raise ValidationError(_("{0}: {1} is not a valid Jalali date"), label, value)


def _time(value, label: str) -> time:
	if isinstance(value, time):
		return value.replace(second=0, microsecond=0)
	text = normalize_time(str(value or "")) if value else None
	if not text:
		raise ValidationError(_("{0}: enter the time as HH:MM"), label)
	hour, minute = (int(x) for x in text.split(":")[:2])
	return time(hour, minute)


def _minutes(t: time) -> int:
	return t.hour * 60 + t.minute


def _reason(values: dict, required: bool, label: str = "") -> str | None:
	reason = (values.get("reason") or "").strip() or None
	if required and not reason:
		raise ValidationError(label or _("Enter the reason"))
	return reason


# who may file it -------------------------------------------------------------------------


def _requester(
	session: Session, actor: access.Actor, values: dict, kind: str, today: str
) -> tuple[int, bool, bool]:
	"""(employee_id, entered_by_operator, assigned_by_manager). Employees file for themselves,
	operators for anyone, managers may assign overtime to their team (Article 59)."""
	employee_id = int(values.get("employee_id") or actor.employee_id or 0)
	if not employee_id:
		raise ValidationError(_("Your user is not linked to an employee"))
	if session.get(Employee, employee_id) is None:
		raise NotFound(_("Employee not found"))
	if employee_id == actor.employee_id:
		return employee_id, False, False
	if actor.is_operator:
		return employee_id, True, False
	if kind == OVERTIME and access.can_see(session, actor, employee_id, today):
		return employee_id, False, True
	if kind == OVERTIME:
		raise PermissionDenied(_("You can only assign overtime to your own team"))
	raise PermissionDenied(_("You can only submit requests for yourself"))


# the four forms ---------------------------------------------------------------------------


def _leave(session: Session, request: Request, values: dict) -> None:
	leave_type = session.get(LeaveType, int(values.get("leave_type_id") or 0))
	if leave_type is None:
		raise ValidationError(_("Choose the leave type"))
	unit = values.get("unit") or DAILY
	detail = LeaveRequest(leave_type_id=leave_type.id, unit=unit)
	if unit == HOURLY:
		if not leave_type.allow_hourly:
			raise ValidationError(_("{0} cannot be taken by the hour"), leave_type.name)
		day = _jdate(values.get("jdate"), _("Date"))
		start, end = (
			_time(values.get("from_time"), _("From Time")),
			_time(values.get("to_time"), _("To Time")),
		)
		if end <= start:
			raise ValidationError(_("The end time must be after the start time"))
		request.request_type, request.start_jdate, request.end_jdate = HOURLY_LEAVE, day, day
		detail.from_time, detail.to_time = start, end
		detail.total_minutes = _minutes(end) - _minutes(start)
		_row, rules = rule_set_for(session, day)
		# Article 70: hourly leave adds up to days of hourly_leave_minutes_per_day
		detail.total_days = Decimal(detail.total_minutes / rules.hourly_leave_minutes_per_day).quantize(
			Decimal("0.0001")
		)
	elif unit == DAILY:
		start_day, end_day = (
			_jdate(values.get("from_date"), _("From Date")),
			_jdate(values.get("to_date"), _("To Date")),
		)
		if end_day < start_day:
			raise ValidationError(_("The end date is before the start date"))
		request.request_type, request.start_jdate, request.end_jdate = DAILY_LEAVE, start_day, end_day
		days = leave.working_days(session, request.employee_id, start_day, end_day)
		if not days:
			raise ValidationError(_("There is no working day in this leave"))
		detail.total_days = Decimal(len(days))
	else:
		raise ValidationError(_("Unknown leave unit"))
	_leave_limits(session, request, leave_type)
	_no_overlap(session, request, detail)
	request.leave = detail


def _leave_limits(session: Session, request: Request, leave_type: LeaveType) -> None:
	_row, rules = rule_set_for(session, request.start_jdate)
	limit = rules.as_dict().get(leave_type.rule_limit) if leave_type.rule_limit else None
	if leave_type.max_days_per_request:
		cap = float(leave_type.max_days_per_request)
		limit = min(limit, cap) if limit else cap
	calendar_days = len(list(iter_days(request.start_jdate, request.end_jdate)))
	if limit and calendar_days > limit:
		raise ValidationError(_("{0} is at most {1} days"), leave_type.name, limit)
	if leave_type.once_in_service:
		taken = session.scalar(
			select(Request.id)
			.join(LeaveRequest, LeaveRequest.request_id == Request.id)
			.where(
				Request.employee_id == request.employee_id,
				LeaveRequest.leave_type_id == leave_type.id,
				Request.status.in_((PENDING, APPROVED)),
			)
		)
		if taken:
			raise ValidationError(_("{0} can be taken only once during employment"), leave_type.name)


def _no_overlap(session: Session, request: Request, detail: LeaveRequest) -> None:
	rows = session.execute(
		select(Request, LeaveRequest)
		.join(LeaveRequest, LeaveRequest.request_id == Request.id)
		.where(
			Request.employee_id == request.employee_id,
			Request.status.in_((PENDING, APPROVED)),
			Request.start_jdate <= request.end_jdate,
			Request.end_jdate >= request.start_jdate,
		)
	).all()
	for other, other_detail in rows:
		if detail.unit == HOURLY and other_detail.unit == HOURLY:
			if detail.to_time <= other_detail.from_time or other_detail.to_time <= detail.from_time:
				continue
		raise ValidationError(_("Overlaps leave request {0}"), other.number)


def _mission(session: Session, request: Request, values: dict) -> None:
	unit = values.get("unit") or DAILY
	detail = MissionRequest(unit=unit, destination=(values.get("destination") or "").strip() or None)
	if unit == HOURLY:
		day = _jdate(values.get("jdate"), _("Date"))
		start, end = (
			_time(values.get("from_time"), _("From Time")),
			_time(values.get("to_time"), _("To Time")),
		)
		if end <= start:
			raise ValidationError(_("The end time must be after the start time"))
		request.start_jdate = request.end_jdate = day
		detail.from_time, detail.to_time = start, end
	elif unit == DAILY:
		start_day, end_day = (
			_jdate(values.get("from_date"), _("From Date")),
			_jdate(values.get("to_date"), _("To Date")),
		)
		if end_day < start_day:
			raise ValidationError(_("The end date is before the start date"))
		request.start_jdate, request.end_jdate = start_day, end_day
	else:
		raise ValidationError(_("Unknown mission unit"))
	request.request_type = MISSION_TYPE
	request.reason = _reason(values, True, _("Enter the reason for the mission"))
	request.mission = detail


def _overtime(session: Session, request: Request, values: dict, assigned: bool) -> None:
	day = _jdate(values.get("jdate"), _("Date"))
	kind = values.get("overtime_kind") or "normal"
	if kind not in OVERTIME_KINDS:
		raise ValidationError(_("Unknown overtime kind"))
	detail = OvertimeRequest(overtime_kind=kind, assigned_by_manager=assigned)
	if values.get("from_time") and values.get("to_time"):
		start, end = _time(values["from_time"], _("From Time")), _time(values["to_time"], _("To Time"))
		detail.from_time, detail.to_time = start, end
		detail.minutes = (_minutes(end) - _minutes(start)) % 1440
	else:
		detail.minutes = int(values.get("minutes") or 0)
	if detail.minutes <= 0:
		raise ValidationError(_("Enter the overtime minutes"))
	request.reason = _reason(
		values, kind != "normal", _("Enter the reason for exceptional or emergency overtime")
	)
	request.request_type, request.start_jdate, request.end_jdate = OVERTIME_TYPE, day, day
	request.overtime = detail


def _correction(session: Session, request: Request, values: dict, today: str) -> None:
	"""Manual entry (ورود دستی ساعت): add missed times or ignore wrong raw punches for one
	person and one day. Raw punches stay untouched."""
	day = _jdate(values.get("jdate"), _("Date"))
	if day > today:
		raise ValidationError(_("A correction cannot be for a future day"))
	request.reason = _reason(values, True, _("Enter the reason for the correction"))
	request.request_type, request.start_jdate, request.end_jdate = CORRECTION_TYPE, day, day
	raw_items = values.get("items") or []
	if not raw_items:
		raise ValidationError(_("Add at least one time"))
	day_punches = None
	seen = set()
	items = []
	for i, raw in enumerate(raw_items, start=1):
		action = raw.get("action") or ADD_PUNCH
		if action == ADD_PUNCH:
			t = _time(raw.get("time"), _("Row {0}").format(i))
			direction = raw.get("direction") or "unknown"
			if direction not in ("in", "out", "unknown"):
				raise ValidationError(_("Row {0}: unknown direction"), i)
			item = CorrectionItem(
				position=i, action=ADD_PUNCH, time=t, direction=direction, note=raw.get("note")
			)
			key = ("add", t)
		elif action == IGNORE_PUNCH:
			if day_punches is None:
				day_punches = {p.id for p in employee_raw_punches(session, request.employee_id, day, day)}
			punch_id = int(raw.get("raw_punch_id") or 0)
			if punch_id not in day_punches:
				raise ValidationError(_("Row {0}: that punch is not a punch of this person on {1}"), i, day)
			item = CorrectionItem(
				position=i, action=IGNORE_PUNCH, raw_punch_id=punch_id, note=raw.get("note")
			)
			key = ("ignore", punch_id)
		else:
			raise ValidationError(_("Row {0}: unknown action"), i)
		if key in seen:
			raise ValidationError(_("Row {0} repeats an earlier row"), i)
		seen.add(key)
		items.append(item)
	request.correction_items = items


# submit, act, cancel ----------------------------------------------------------------------


def submit(session: Session, actor: access.Actor, kind: str, values: dict, today: str) -> Request:
	employee_id, by_operator, assigned = _requester(session, actor, values, kind, today)
	request = Request(
		kind=kind, employee_id=employee_id, entered_by_id=actor.user_id, entered_by_operator=by_operator
	)
	if kind == LEAVE:
		request.reason = _reason(values, False)
		_leave(session, request, values)
	elif kind == MISSION:
		_mission(session, request, values)
	elif kind == OVERTIME:
		_overtime(session, request, values, assigned)
	elif kind == CORRECTION:
		_correction(session, request, values, today)
	else:
		raise ValidationError(_("Unknown request type"))
	assert_open(session, [request.start_jdate, request.end_jdate])
	_check_balance(session, request)
	process = approvals.process_for(session, employee_id, request.request_type, by_operator)
	approvals.build_chain(session, request, process, today)
	if assigned:
		_assigned_overtime_chain(session, actor, request)
	session.add(request)
	session.flush()
	session.refresh(request, ["number"])
	audit.log(
		session, "request", request.id, "submit", actor.user_id, request.reason, after=_audit_view(request)
	)
	if request.status == APPROVED:
		_on_approved(session, actor, request)
	return request


def _check_balance(session: Session, request: Request) -> None:
	if request.kind != LEAVE:
		return
	leave_type = session.get(LeaveType, request.leave.leave_type_id)
	if not leave_type.deducts_from_balance or settings.get(session, "allow_negative_leave_balance"):
		return
	available = leave.balance(session, request.employee_id, leave_type.id)
	if available < request.leave.total_days:
		raise ValidationError(
			_("Not enough leave: {0} days available, {1} requested"),
			float(available),
			float(request.leave.total_days),
		)


def _assigned_overtime_chain(session: Session, actor: access.Actor, request: Request) -> None:
	"""Overtime assigned by a manager: the employee accepts first (Article 59); the assigning
	manager's own steps count as approved."""
	now = datetime.now(UTC)
	steps = [
		RequestApproval(
			step=0,
			approver_type=EMPLOYEE_ACCEPTANCE,
			approver_id=request.employee_id,
			approver_user_id=access.user_of(session, request.employee_id),
			status=PENDING,
		)
	]
	for a in request.approvals:
		if a.approver_user_id == actor.user_id and a.status == PENDING:
			a.status, a.acted_by_id, a.acted_at, a.comment = (
				APPROVED,
				actor.user_id,
				now,
				"assigned the overtime",
			)
		steps.append(a)
	if steps[0].approver_user_id is None:
		raise ValidationError(_("This person has no user account to accept the overtime"))
	request.approvals = steps
	request.status = PENDING
	approvals.advance(request)


def get(session: Session, actor: access.Actor, request_id: int, today: str) -> Request:
	request = session.get(Request, request_id)
	if request is None:
		raise NotFound(_("Request not found"))
	if not (access.can_see(session, actor, request.employee_id, today) or approvals.in_chain(actor, request)):
		raise PermissionDenied(_("Not permitted"))
	return request


def act(
	session: Session, actor: access.Actor, request_id: int, action: str, comment: str | None, today: str
) -> Request:
	request = session.get(Request, request_id)
	if request is None:
		raise NotFound(_("Request not found"))
	if action not in (APPROVE, REJECT):
		raise ValidationError(_("Unknown action"))
	if request.status != PENDING:
		raise ValidationError(_("This request is not waiting for approval"))
	if not approvals.can_act(actor, request):
		raise PermissionDenied(_("This request is waiting for someone else"))
	if action == REJECT and not (comment or "").strip():
		raise ValidationError(_("Enter the reason for rejecting"))
	assert_open(session, [request.start_jdate, request.end_jdate])
	step = approvals.current_step(request)
	step.status = APPROVED if action == APPROVE else REJECTED
	step.acted_by_id, step.acted_at, step.comment = actor.user_id, datetime.now(UTC), comment
	if action == REJECT:
		request.status = REJECTED
		request.pending_approver_id = request.pending_approver_user_id = None
		request.decided_at = datetime.now(UTC)
	else:
		approvals.advance(request)
	session.flush()
	audit.log(
		session,
		"request",
		request.id,
		action,
		actor.user_id,
		comment,
		after={"step": step.step, "status": request.status},
	)
	if request.status == APPROVED:
		_on_approved(session, actor, request)
	return request


def cancel(session: Session, actor: access.Actor, request_id: int, reason: str | None, today: str) -> Request:
	"""The employee may withdraw their own pending request; an operator may cancel any
	request, approved ones included, with a reason."""
	request = get(session, actor, request_id, today)
	if request.status not in (PENDING, APPROVED):
		raise ValidationError(_("This request cannot be cancelled"))
	own = request.employee_id == actor.employee_id and request.status == PENDING
	if not (own or actor.is_operator):
		raise PermissionDenied(_("Only an operator can cancel this request"))
	if not own and not (reason or "").strip():
		raise ValidationError(_("Enter the reason for cancelling"))
	assert_open(session, [request.start_jdate, request.end_jdate])
	previous = request.status
	request.status = CANCELLED
	request.pending_approver_id = request.pending_approver_user_id = None
	request.cancelled_at = datetime.now(UTC)
	session.flush()
	audit.log(
		session,
		"request",
		request.id,
		"cancel",
		actor.user_id,
		reason,
		before={"status": previous},
		after={"status": CANCELLED},
	)
	if previous == APPROVED:
		_on_cancelled(session, actor, request)
	return request


# side effects -------------------------------------------------------------------------------


def _recalculate(session: Session, request: Request, why: str) -> None:
	jobs.enqueue(
		session,
		jobs.RECALCULATE,
		{
			"employee_ids": [request.employee_id],
			"dates": list(iter_days(request.start_jdate, request.end_jdate)),
			"reason": f"{request.number} {why}",
		},
	)


def _on_approved(session: Session, actor: access.Actor, request: Request) -> None:
	if request.kind == LEAVE and session.get(LeaveType, request.leave.leave_type_id).deducts_from_balance:
		leave.add_entry(
			session,
			request.employee_id,
			request.leave.leave_type_id,
			leave.USAGE,
			request.start_jdate,
			-request.leave.total_days,
			request_id=request.id,
			user_id=actor.user_id,
		)
	_recalculate(session, request, "approved")


def _on_cancelled(session: Session, actor: access.Actor, request: Request) -> None:
	if request.kind == LEAVE and session.get(LeaveType, request.leave.leave_type_id).deducts_from_balance:
		leave.add_entry(
			session,
			request.employee_id,
			request.leave.leave_type_id,
			leave.REVERSAL,
			request.start_jdate,
			request.leave.total_days,
			request_id=request.id,
			user_id=actor.user_id,
		)
	_recalculate(session, request, "cancelled")


def _audit_view(request: Request) -> dict:
	view = audit.snapshot(request)
	for name in ("leave", "mission", "overtime"):
		detail = getattr(request, name)
		if detail is not None:
			view[name] = audit.snapshot(detail)
	if request.correction_items:
		view["items"] = [audit.snapshot(i) for i in request.correction_items]
	view["approvals"] = [audit.snapshot(a) for a in request.approvals]
	return view


# lists ----------------------------------------------------------------------------------------


def inbox(session: Session, actor: access.Actor) -> list[Request]:
	"""Requests waiting for this user."""
	if actor.user_id is None:
		return []
	return list(
		session.scalars(
			select(Request)
			.where(Request.status == PENDING, Request.pending_approver_user_id == actor.user_id)
			.order_by(Request.created_at)
		)
	)


def list_requests(
	session: Session,
	actor: access.Actor,
	today: str,
	employee_id: int | None = None,
	status: str | None = None,
	limit: int = 50,
) -> list[Request]:
	query = select(Request).order_by(Request.created_at.desc()).limit(min(limit, 500))
	if employee_id:
		access.assert_can_see(session, actor, employee_id, today)
		query = query.where(Request.employee_id == employee_id)
	else:
		visible = access.visible_employee_ids(session, actor, today)
		if visible is not None:
			query = query.where(
				or_(
					Request.employee_id.in_(visible or {0}),
					Request.id.in_(
						select(RequestApproval.request_id).where(
							RequestApproval.approver_user_id == actor.user_id
						)
					),
				)
			)
	if status:
		query = query.where(Request.status == status)
	return list(session.scalars(query))
