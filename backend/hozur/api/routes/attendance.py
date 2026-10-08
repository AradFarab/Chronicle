"""Calculated days, punches, leave balances, warnings and period locks."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Operator, Today
from hozur.api.views import hm, jalali_moment
from hozur.db.models import DailyAttendance, Employee, LeaveType
from hozur.i18n import _
from hozur.jalali.dates import normalize_jdate
from hozur.services import access, attendance, audit, leave, periods
from hozur.services.errors import NotFound, PermissionDenied, ValidationError
from hozur.services.punches import effective_punches, employee_raw_punches
from hozur.services.schedules import resolve

router = APIRouter(prefix="/api", tags=["attendance"])


class Recalculation(BaseModel):
	from_date: str
	to_date: str
	employee_ids: list[int] | None = None


class PeriodAction(BaseModel):
	note: str | None = None


def _see(db, actor, employee_id: int, today: str) -> None:
	if db.get(Employee, employee_id) is None:
		raise NotFound(_("Employee not found"))
	if not access.can_see(db, actor, employee_id, today):
		raise PermissionDenied(_("Not permitted"))


def day_view(r: DailyAttendance) -> dict:
	view = audit.snapshot(r, exclude=("calculated_at",))
	view["first_in"], view["last_out"] = hm(r.first_in), hm(r.last_out)
	view["leave_days"] = float(r.leave_days)
	view["leaves"] = [
		{"leave_type_id": lv.leave_type_id, "minutes": lv.minutes, "days": float(lv.days)} for lv in r.leaves
	]
	view["calculated_at"] = jalali_moment(r.calculated_at)
	return view


@router.get("/attendance")
def days(
	actor: Actor,
	db: DB,
	today: Today,
	from_date: str,
	to_date: str,
	employee_id: int | None = None,
) -> list[dict]:
	"""Calculated days: one person (yourself by default) or everyone you may see."""
	start, end = normalize_jdate(from_date), normalize_jdate(to_date)
	if end < start:
		raise ValidationError(_("The end date is before the start date"))
	query = select(DailyAttendance).where(DailyAttendance.jdate.between(start, end))
	if employee_id is None and not actor.sees_all and actor.employee_id:
		employee_id = actor.employee_id
	if employee_id is not None:
		_see(db, actor, employee_id, today)
		query = query.where(DailyAttendance.employee_id == employee_id)
	else:
		visible = access.visible_employee_ids(db, actor, today)
		if visible is not None:
			query = query.where(DailyAttendance.employee_id.in_(visible or {0}))
	rows = db.scalars(query.order_by(DailyAttendance.employee_id, DailyAttendance.jdate))
	return [day_view(r) for r in rows]


@router.get("/attendance/day")
def day_details(employee_id: int, jdate: str, actor: Actor, db: DB, today: Today) -> dict:
	"""Everything that went into one day, for the day view."""
	_see(db, actor, employee_id, today)
	jdate = normalize_jdate(jdate)
	row = db.scalar(
		select(DailyAttendance).where(
			DailyAttendance.employee_id == employee_id, DailyAttendance.jdate == jdate
		)
	)
	schedule = resolve(db, employee_id, jdate)
	effective = {p.raw_punch_id for p in effective_punches(db, employee_id, jdate) if p.raw_punch_id}
	return {
		"attendance": day_view(row) if row else None,
		"punches": [
			{
				"id": p.id,
				"time": p.time.strftime("%H:%M:%S"),
				"direction": p.direction,
				"source": p.source,
				"device_id": p.device_id,
				"is_duplicate": p.is_duplicate,
				"ignored": not p.is_duplicate and p.id not in effective,
			}
			for p in employee_raw_punches(db, employee_id, jdate, jdate)
		],
		"manual_punches": [
			{"time": p.time.strftime("%H:%M:%S"), "direction": p.direction, "request_id": p.request_id}
			for p in effective_punches(db, employee_id, jdate)
			if p.request_id
		],
		"schedule": {
			"shift_id": schedule.shift_id,
			"shift": schedule.shift.name if schedule.shift else None,
			"work_pattern_id": schedule.pattern_id,
			"rest_day": schedule.rest_day,
			"source": schedule.source,
		},
		"period_closed": periods.is_closed(db, jdate),
	}


@router.post("/attendance/recalculate")
def recalculate(body: Recalculation, actor: Operator, db: DB, today: Today) -> dict:
	"""Recalculate now (operator button). Closed periods are skipped."""
	start, end = normalize_jdate(body.from_date), normalize_jdate(body.to_date)
	if end < start:
		raise ValidationError(_("The end date is before the start date"))
	reason = f"recalculated by user {actor.user_id}"
	outcome = attendance.recalculate_range(db, start, end, today, reason, body.employee_ids, actor.user_id)
	return outcome.as_dict()


@router.get("/attendance/absence-warnings")
def absence_warnings(actor: Actor, db: DB, today: Today) -> list[dict]:
	"""Disciplinary warnings only (Article 27): nothing happens automatically."""
	visible = access.visible_employee_ids(db, actor, today)
	if visible is not None and not access.is_manager(db, actor, today):
		raise PermissionDenied(_("Not permitted"))
	warnings = attendance.absence_warnings(db, today, visible)
	names = dict(db.execute(select(Employee.id, Employee.full_name)).all())
	return [{**w, "employee_name": names.get(w["employee_id"])} for w in warnings]


@router.get("/leave/balances")
def balances(actor: Actor, db: DB, today: Today, employee_id: int | None = None) -> list[dict]:
	employee_id = employee_id or actor.employee_id
	if not employee_id:
		raise NotFound(_("Employee not found"))
	_see(db, actor, employee_id, today)
	return [
		{
			"leave_type_id": t.id,
			"name": t.name,
			"balance": float(leave.balance(db, employee_id, t.id, upto=today)),
		}
		for t in db.scalars(select(LeaveType).where(LeaveType.deducts_from_balance).order_by(LeaveType.name))
	]


# periods -----------------------------------------------------------------------------------------


@router.get("/periods/{year}")
def list_periods(year: int, actor: Actor, db: DB) -> list[dict]:
	return [{**p, "closed_at": jalali_moment(p["closed_at"])} for p in periods.list_periods(db, year)]


@router.post("/periods/{year}/{month}/close")
def close_period(year: int, month: int, body: PeriodAction, actor: Operator, db: DB, today: Today) -> dict:
	row = periods.close(db, year, month, today, actor.user_id, body.note)
	return {"jyear": row.jyear, "jmonth": row.jmonth, "status": row.status}


@router.post("/periods/{year}/{month}/reopen")
def reopen_period(year: int, month: int, body: PeriodAction, actor: Operator, db: DB) -> dict:
	row = periods.reopen(db, year, month, actor.user_id, body.note or "")
	return {"jyear": row.jyear, "jmonth": row.jmonth, "status": row.status}
