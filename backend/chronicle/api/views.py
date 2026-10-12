"""JSON shapes the PWA receives. Codes stay codes; the PWA translates labels."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from chronicle.config import get_settings
from chronicle.db.models import Employee, Holiday, Request
from chronicle.jalali.dates import to_jalali
from chronicle.services import access, approvals


def jalali_moment(value: datetime | None) -> str | None:
	"""A system instant shown to people: '1405/07/14 10:22' in the company's timezone."""
	if value is None:
		return None
	local = value.astimezone(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)
	jdate, clock = to_jalali(local)
	return f"{jdate} {clock[:5]}"


def hm(value) -> str | None:
	return value.strftime("%H:%M") if value is not None else None


def employee_name(session: Session, employee_id: int | None) -> str | None:
	if not employee_id:
		return None
	e = session.get(Employee, employee_id)
	return e.full_name if e else None


def request_view(session: Session, r: Request, actor: access.Actor | None = None, today: str = "") -> dict:
	view = {
		"id": r.id,
		"number": r.number,
		"kind": r.kind,
		"request_type": r.request_type,
		"status": r.status,
		"employee_id": r.employee_id,
		"employee_name": employee_name(session, r.employee_id),
		"start_jdate": r.start_jdate,
		"end_jdate": r.end_jdate,
		"reason": r.reason,
		"entered_by_admin": r.entered_by_admin,
		"created_at": jalali_moment(r.created_at),
		"waiting_for": [employee_name(session, e) for e in approvals.waiting_for(r)],
		"approvals": [
			{
				"step": a.step,
				"approver_type": a.approver_type,
				"approver_names": [employee_name(session, p.employee_id) for p in a.approvers],
				"status": a.status,
				"acted_at": jalali_moment(a.acted_at),
				"comment": a.comment,
			}
			for a in r.approvals
		],
	}
	if r.leave:
		view["leave"] = {
			"leave_type_id": r.leave.leave_type_id,
			"unit": r.leave.unit,
			"from_time": hm(r.leave.from_time),
			"to_time": hm(r.leave.to_time),
			"total_days": float(r.leave.total_days),
			"total_minutes": r.leave.total_minutes,
		}
	if r.mission:
		view["mission"] = {
			"unit": r.mission.unit,
			"destination": r.mission.destination,
			"from_time": hm(r.mission.from_time),
			"to_time": hm(r.mission.to_time),
		}
	if r.overtime:
		view["overtime"] = {
			"overtime_kind": r.overtime.overtime_kind,
			"minutes": r.overtime.minutes,
			"from_time": hm(r.overtime.from_time),
			"to_time": hm(r.overtime.to_time),
			"assigned_by_manager": r.overtime.assigned_by_manager,
		}
	if r.correction_items:
		view["items"] = [
			{
				"action": i.action,
				"time": hm(i.time),
				"direction": i.direction,
				"raw_punch_id": i.raw_punch_id,
				"note": i.note,
			}
			for i in r.correction_items
		]
	if actor is not None:
		step = approvals.current_step(r)
		view["can_act"] = approvals.can_act(session, actor, r, today)
		view["is_acceptance"] = bool(step and step.approver_type == "employee_acceptance")
	return view


def holiday_view(h: Holiday) -> dict:
	return {
		"id": h.id,
		"jdate": h.jdate,
		"title": h.title,
		"holiday_type": h.holiday_type,
		"status": h.status,
		"scope": h.scope,
		"province_id": h.province_id,
		"work_location_id": h.work_location_id,
		"closure_pay_mode": h.closure_pay_mode,
		"source": h.source,
		"note": h.note,
		"edited_by_admin": h.edited_by_admin,
	}
