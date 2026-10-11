"""Suggested requests (درخواست پیشنهادی): what the day's punches and work pattern say the
employee probably needs to ask for.

- extra work inside the shift's overtime windows that is not approved yet -> overtime
- late arrival or early leave -> hourly leave
- a punch without its pair -> a punch correction

They are proposals only. The employee sends one as a real request (for overtime that is their
own consent, Article 59) or dismisses it; nothing is submitted for them. Every recalculation of
a day refreshes its open proposals; a dismissed or sent one is never proposed again.
"""

from __future__ import annotations

from datetime import time

from sqlalchemy import delete, select, true
from sqlalchemy.orm import Session

from hozur.db.models import Employee, RequestSuggestion
from hozur.db.models.requests import CORRECTION_TYPE, DISMISSED, HOURLY_LEAVE, OPEN, OVERTIME_TYPE, SENT
from hozur.engine import model as engine
from hozur.i18n import _
from hozur.services import access
from hozur.services.errors import NotFound, PermissionDenied, ValidationError

W_MISSING_PUNCH = "MISSING_PUNCH"


def proposals(
	result: engine.DailyResult, shift: engine.Shift | None, flags: engine.EmployeeFlags
) -> list[dict]:
	"""The day's proposals from the engine result (pure: no database)."""
	out: list[dict] = []
	unapproved_in_windows = result.unapproved_extra_minutes - result.outside_window_minutes
	if (
		result.overtime_intervals
		and unapproved_in_windows > 0
		and not (flags.hard_harmful or flags.juvenile)  # Articles 61 and 84: no overtime at all
	):
		start, end = result.overtime_intervals[0][0], result.overtime_intervals[-1][1]
		minutes = min(unapproved_in_windows, sum(b - a for a, b in result.overtime_intervals))
		out.append(_item(OVERTIME_TYPE, f"overtime:{start}-{end}", start, end, minutes))
	if shift is not None and result.status in (engine.PRESENT, engine.INCOMPLETE):
		if result.late_minutes and result.first_in is not None:
			anchor = shift.latest_start if shift.flexible and shift.latest_start is not None else shift.start
			start, end = anchor, max(result.first_in, anchor + result.late_minutes)
			out.append(_item(HOURLY_LEAVE, f"late:{start}-{end}", start, end, result.late_minutes))
		if result.early_leave_minutes and result.last_out is not None:
			end = shift.end
			start = min(result.last_out, end - result.early_leave_minutes)
			out.append(_item(HOURLY_LEAVE, f"early:{start}-{end}", start, end, result.early_leave_minutes))
	if W_MISSING_PUNCH in result.warnings:
		out.append(_item(CORRECTION_TYPE, "missing-punch", None, None, 0))
	return out


def _item(request_type: str, key: str, start: int | None, end: int | None, minutes: int) -> dict:
	return {
		"request_type": request_type,
		"key": key,
		"from_minute": start,
		"to_minute": end,
		"minutes": minutes,
	}


def refresh(session: Session, employee_id: int, jdate: str, items: list[dict]) -> None:
	"""Replace the day's open proposals; keep sent and dismissed ones as they are."""
	keys = {i["key"] for i in items}
	session.execute(
		delete(RequestSuggestion).where(
			RequestSuggestion.employee_id == employee_id,
			RequestSuggestion.jdate == jdate,
			RequestSuggestion.status == OPEN,
			RequestSuggestion.key.not_in(keys) if keys else true(),
		)
	)
	existing = {
		s.key: s
		for s in session.scalars(
			select(RequestSuggestion).where(
				RequestSuggestion.employee_id == employee_id, RequestSuggestion.jdate == jdate
			)
		)
	}
	for item in items:
		row = existing.get(item["key"])
		if row is None:
			session.add(RequestSuggestion(employee_id=employee_id, jdate=jdate, **item))
		elif row.status == OPEN:
			row.minutes, row.from_minute, row.to_minute = (
				item["minutes"],
				item["from_minute"],
				item["to_minute"],
			)


def clear(session: Session, employee_id: int, jdate: str) -> None:
	refresh(session, employee_id, jdate, [])


def _clock(minute: int | None) -> str | None:
	if minute is None:
		return None
	m = minute % 1440
	return time(m // 60, m % 60).strftime("%H:%M")


def view(s: RequestSuggestion) -> dict:
	return {
		"id": s.id,
		"employee_id": s.employee_id,
		"jdate": s.jdate,
		"request_type": s.request_type,
		"key": s.key,
		"from_time": _clock(s.from_minute),
		"to_time": _clock(s.to_minute),
		"minutes": s.minutes,
		"status": s.status,
		"request_id": s.request_id,
	}


def open_for(
	session: Session, actor: access.Actor, employee_id: int | None = None
) -> list[RequestSuggestion]:
	"""The open proposals of the actor (or, for an admin, of one employee), newest day first."""
	target = employee_id or actor.employee_id
	if target is None:
		return []
	if target != actor.employee_id and not actor.is_admin:
		raise PermissionDenied(_("Not permitted"))
	return list(
		session.scalars(
			select(RequestSuggestion)
			.join(Employee, Employee.id == RequestSuggestion.employee_id)
			.where(RequestSuggestion.employee_id == target, RequestSuggestion.status == OPEN)
			.order_by(RequestSuggestion.jdate.desc(), RequestSuggestion.id)
		)
	)


def _own(session: Session, actor: access.Actor, suggestion_id: int) -> RequestSuggestion:
	s = session.get(RequestSuggestion, suggestion_id)
	if s is None:
		raise NotFound(_("Not found"))
	if s.employee_id != actor.employee_id and not actor.is_admin:
		raise PermissionDenied(_("Not permitted"))
	return s


def dismiss(session: Session, actor: access.Actor, suggestion_id: int) -> RequestSuggestion:
	s = _own(session, actor, suggestion_id)
	if s.status != OPEN:
		raise ValidationError(_("This suggestion was already handled"))
	s.status = DISMISSED
	session.flush()
	return s


def mark_sent(session: Session, actor: access.Actor, suggestion_id: int, request) -> None:
	"""The request made from a suggestion: the suggestion is done."""
	s = _own(session, actor, suggestion_id)
	if s.employee_id != request.employee_id:
		raise ValidationError(_("This suggestion is for someone else"))
	if s.status == OPEN:
		s.status, s.request_id = SENT, request.id
		session.flush()
