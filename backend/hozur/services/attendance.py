"""Daily attendance: gather one person-day's inputs, run the engine, store the result.

A daily_attendance row is never edited by hand; it is always rebuilt from punches, approved
requests, the schedule, the calendar and the rule set. A recalculation that changes a stored
day writes an audit entry. Days in closed periods and days after today are never touched.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from hozur.calendar.service import holidays_by_date
from hozur.db.models import (
	DailyAttendance,
	DailyAttendanceLeave,
	Designation,
	Employee,
	LeaveRequest,
	LeaveType,
	MissionRequest,
	OvertimeRequest,
	Request,
	WorkLocation,
)
from hozur.db.models.org import SUSPENDED
from hozur.db.models.requests import APPROVED, HOURLY, LEAVE, MISSION, OVERTIME
from hozur.engine.daily import calculate_day
from hozur.engine.model import (
	HOLIDAY,
	OFF,
	REST,
	Absence,
	DailyResult,
	Day,
	EmployeeFlags,
	OvertimeApproval,
	Punch,
)
from hozur.engine.periodic import absence_streaks
from hozur.engine.rules import RuleSet
from hozur.jalali.calendar import resolve_day
from hozur.jalali.dates import add_days, iter_days, parse_jdate
from hozur.services import audit, settings
from hozur.services.access import designations_on
from hozur.services.periods import closed_months
from hozur.services.punches import effective_punches
from hozur.services.rule_sets import rule_set_for
from hozur.services.schedules import Schedule, ScheduleResolver, minutes

NEXT_DAY_BUFFER = 240  # minutes after an overnight shift whose punches still belong to it

# engine result field -> column (same name)
RESULT_FIELDS = (
	"status",
	"required_minutes",
	"worked_minutes",
	"credited_minutes",
	"late_minutes",
	"early_leave_minutes",
	"absence_minutes",
	"absent_day",
	"mission_minutes",
	"nursing_minutes",
	"extra_minutes",
	"unapproved_extra_minutes",
	"night_work_minutes",
	"rest_day_work_minutes",
	"friday_premium_minutes",
	"holiday_work_minutes",
	"company_holiday_work_minutes",
)


def employed_on(emp: Employee, jdate: str) -> bool:
	return (
		emp.status != SUSPENDED
		and bool(emp.start_date)
		and emp.start_date <= jdate
		and (not emp.end_date or jdate <= emp.end_date)
	)


def _age_on(birth_date: str, jdate: str) -> int:
	by, bm, bd = parse_jdate(birth_date)
	y, m, d = parse_jdate(jdate)
	return y - by - (1 if (m, d) < (bm, bd) else 0)


def _clock(minute: int | None) -> time | None:
	"""Engine minute (may pass midnight) -> time of day."""
	if minute is None:
		return None
	return time(minute % 1440 // 60, minute % 60)


def _punch_window(schedule: Schedule, previous: Schedule, following: Schedule) -> tuple[int, int]:
	"""Seconds (from this day's midnight) of the punches that belong to this day: an
	overnight shift keeps the early punches of the next day."""
	start = 0
	if previous.shift and previous.shift.end > 1440:
		start = (previous.shift.end - 1440 + NEXT_DAY_BUFFER) * 60
		if schedule.shift:
			start = min(start, schedule.shift.start * 60)
	end = 86400
	if schedule.shift and schedule.shift.end > 1440:
		end = 86400 + (schedule.shift.end - 1440 + NEXT_DAY_BUFFER) * 60
		if following.shift:
			end = min(end, 86400 + following.shift.start * 60)
	return start, end


@dataclass
class Outcome:
	created: int = 0
	updated: int = 0
	unchanged: int = 0
	removed: int = 0
	skipped: int = 0  # closed period, future day

	def as_dict(self) -> dict[str, int]:
		return dict(self.__dict__)


class Calculator:
	"""Calculates many person-days with one session; caches what it reads."""

	def __init__(self, session: Session, today: str, user_id: int | None = None):
		self.session = session
		self.today = today
		self.user_id = user_id
		self.schedules = ScheduleResolver(session)
		self._rules: dict[str, tuple[int, RuleSet]] = {}
		self._holidays: dict[str, list[dict]] = {}
		self._holiday_range: tuple[str, str] | None = None
		self._provinces: dict[int, int] = {}
		self._hard: dict[int, bool] = {}
		self._held: dict[tuple[int, str], list[int]] = {}
		self._leave_types: dict[int, LeaveType] = {}
		self._closed: dict[tuple[int, int], bool] = {}

	# cached reads ------------------------------------------------------------------------

	def _rule_set(self, jdate: str) -> tuple[int, RuleSet]:
		if jdate not in self._rules:
			row, rules = rule_set_for(self.session, jdate)
			self._rules[jdate] = (row.id, rules)
		return self._rules[jdate]

	def _holidays_on(self, jdate: str) -> list[dict]:
		lo, hi = self._holiday_range or ("", "")
		if not lo <= jdate <= hi:
			# read a month around the day at once
			self._holiday_range = (jdate[:8] + "01", add_days(jdate[:8] + "01", 40))
			self._holidays = holidays_by_date(self.session, *self._holiday_range)
		return self._holidays.get(jdate, [])

	def _province(self, work_location_id: int | None) -> int | None:
		if not work_location_id:
			return None
		if work_location_id not in self._provinces:
			self._provinces[work_location_id] = self.session.scalar(
				select(WorkLocation.province_id).where(WorkLocation.id == work_location_id)
			)
		return self._provinces[work_location_id]

	def _designations(self, employee_id: int, jdate: str) -> list[int]:
		key = (employee_id, jdate)
		if key not in self._held:
			self._held[key] = designations_on(self.session, employee_id, jdate)
		return self._held[key]

	def _hard_harmful(self, designation_id: int | None) -> bool:
		if not designation_id:
			return False
		if designation_id not in self._hard:
			self._hard[designation_id] = bool(
				self.session.scalar(
					select(Designation.hard_and_harmful).where(Designation.id == designation_id)
				)
			)
		return self._hard[designation_id]

	def _leave_type(self, leave_type_id: int) -> LeaveType:
		if leave_type_id not in self._leave_types:
			self._leave_types[leave_type_id] = self.session.get(LeaveType, leave_type_id)
		return self._leave_types[leave_type_id]

	def is_closed(self, jdate: str) -> bool:
		key = (int(jdate[:4]), int(jdate[5:7]))
		if key not in self._closed:
			self._closed[key] = bool(closed_months(self.session, [jdate]))
		return self._closed[key]

	# inputs ------------------------------------------------------------------------------

	def _flags(self, emp: Employee, jdate: str, schedule: Schedule, rules: RuleSet) -> EmployeeFlags:
		return EmployeeFlags(
			juvenile=bool(emp.birth_date) and _age_on(emp.birth_date, jdate) < rules.juvenile_max_age_years,
			hard_harmful=any(self._hard_harmful(d) for d in self._designations(emp.id, jdate)),
			nursing=bool(emp.nursing_until) and jdate <= emp.nursing_until,
			rotating=schedule.rotating,
			standing_overtime_consent=emp.overtime_consent_on_file
			and (not emp.overtime_consent_date or emp.overtime_consent_date <= jdate),
		)

	def _punches(self, employee_id: int, jdate: str, window: tuple[int, int]) -> list[Punch]:
		nxt = add_days(jdate, 1)
		out = []
		for p in effective_punches(self.session, employee_id, jdate, nxt if window[1] > 86400 else jdate):
			second = (
				p.time.hour * 3600 + p.time.minute * 60 + p.time.second + (86400 if p.jdate == nxt else 0)
			)
			if window[0] <= second < window[1]:
				out.append(Punch(second, p.direction))
		return out

	def _approved(self, detail, employee_id: int, jdate: str, kind: str):
		"""Details (leave_request / mission_request / overtime_request) of approved requests
		covering the day."""
		return self.session.scalars(
			select(detail)
			.join(Request, Request.id == detail.request_id)
			.where(
				Request.employee_id == employee_id,
				Request.kind == kind,
				Request.status == APPROVED,
				Request.start_jdate <= jdate,
				Request.end_jdate >= jdate,
			)
		)

	def _absences(self, employee_id: int, jdate: str) -> list[Absence]:
		out = []
		for lv in self._approved(LeaveRequest, employee_id, jdate, LEAVE):
			paid = self._leave_type(lv.leave_type_id).is_paid
			key = str(lv.leave_type_id)
			if lv.unit == HOURLY:
				out.append(Absence(LEAVE, key, minutes(lv.from_time), minutes(lv.to_time), paid))
			else:
				out.append(Absence(LEAVE, key, paid=paid))
		for ms in self._approved(MissionRequest, employee_id, jdate, MISSION):
			if ms.unit == HOURLY:
				out.append(Absence(MISSION, MISSION, minutes(ms.from_time), minutes(ms.to_time)))
			else:
				out.append(Absence(MISSION, MISSION))
		return out

	def _overtime(self, employee_id: int, jdate: str) -> list[OvertimeApproval]:
		return [
			OvertimeApproval(r.minutes, r.overtime_kind)
			for r in self._approved(OvertimeRequest, employee_id, jdate, OVERTIME)
		]

	# calculation -------------------------------------------------------------------------

	def run(self, emp: Employee, jdate: str) -> tuple[DailyResult, dict, dict[int, tuple[int, Decimal]]]:
		"""Engine result, the row values and the per-leave-type minutes/days of one day."""
		location_id = emp.work_location_id
		day = resolve_day(jdate, self._holidays_on(jdate), location_id, self._province(location_id))
		schedule = self.schedules.resolve(emp.id, jdate)
		window = _punch_window(
			schedule,
			self.schedules.resolve(emp.id, add_days(jdate, -1)),
			self.schedules.resolve(emp.id, add_days(jdate, 1)),
		)
		punches = self._punches(emp.id, jdate, window)
		rule_set_id, rules = self._rule_set(jdate)
		result = calculate_day(
			Day(jdate=jdate, weekday=day.weekday, day_type=day.day_type, rest_day=schedule.rest_day),
			schedule.shift,
			punches,
			rules,
			self._flags(emp, jdate, schedule, rules),
			self._absences(emp.id, jdate),
			self._overtime(emp.id, jdate),
		)
		values = {
			"weekday": day.weekday,
			"day_type": day.day_type,
			"holiday_title": day.title or None,
			"department_id": emp.department_id,
			"work_location_id": location_id,
			"designation_id": (self._designations(emp.id, jdate) or [None])[0],
			"work_pattern_id": schedule.pattern_id,
			"shift_id": schedule.shift_id,
			"rest_day": schedule.rest_day,
			"rule_set_id": rule_set_id,
			"first_in": _clock(result.first_in),
			"last_out": _clock(result.last_out),
			"punch_count": len(punches),
			**{f: getattr(result, f) for f in RESULT_FIELDS},
			"leave_minutes": sum(result.leave_minutes.values()),
			"leave_days": Decimal(str(round(sum(result.leave_days.values()), 4))),
			"overtime_normal_minutes": result.overtime_minutes.get("normal", 0),
			"overtime_exceptional_minutes": result.overtime_minutes.get("exceptional", 0),
			"overtime_emergency_minutes": result.overtime_minutes.get("emergency", 0),
			"warnings": list(result.warnings),
		}
		leaves = {
			int(t): (m, Decimal(str(round(result.leave_days.get(t, 0), 4))))
			for t, m in sorted(result.leave_minutes.items())
		}
		return result, values, leaves

	def calculate(self, employee_id: int, jdate: str, reason: str, outcome: Outcome | None = None) -> None:
		"""Calculate and store one person-day."""
		outcome = outcome if outcome is not None else Outcome()
		if jdate > self.today or self.is_closed(jdate):
			outcome.skipped += 1
			return
		emp = self.schedules._employee(employee_id)
		row = self.session.scalar(
			select(DailyAttendance).where(
				DailyAttendance.employee_id == employee_id, DailyAttendance.jdate == jdate
			)
		)
		if emp is None or not employed_on(emp, jdate):
			if row is not None:
				audit.log(
					self.session,
					"daily_attendance",
					row.id,
					"delete",
					self.user_id,
					reason,
					before=_view(row),
				)
				self.session.delete(row)
				outcome.removed += 1
			return
		_result, values, leaves = self.run(emp, jdate)
		if row is None:
			row = DailyAttendance(employee_id=employee_id, jdate=jdate, **values)
			row.leaves = [
				DailyAttendanceLeave(leave_type_id=t, minutes=m, days=d) for t, (m, d) in leaves.items()
			]
			self.session.add(row)
			outcome.created += 1
			return
		before = _view(row)
		after = {**{k: _plain(v) for k, v in values.items()}, "leaves": _leaves_view(leaves)}
		changed = [k for k in after if before.get(k) != after[k]]
		if not changed:
			outcome.unchanged += 1
			return
		for key, value in values.items():
			setattr(row, key, value)
		current = {lv.leave_type_id: lv for lv in row.leaves}
		for type_id in set(current) - set(leaves):
			row.leaves.remove(current[type_id])
		for type_id, (m, d) in leaves.items():
			if type_id in current:
				current[type_id].minutes, current[type_id].days = m, d
			else:
				row.leaves.append(DailyAttendanceLeave(leave_type_id=type_id, minutes=m, days=d))
		row.calculated_at = _now()
		audit.log(
			self.session,
			"daily_attendance",
			row.id,
			"update",
			self.user_id,
			reason,
			before={k: before.get(k) for k in changed},
			after={k: after[k] for k in changed},
		)
		outcome.updated += 1


def _now():
	from hozur.clock import now

	return now()


def _plain(value):
	if isinstance(value, time):
		return value.strftime("%H:%M")
	if isinstance(value, Decimal):
		return float(value)
	return value


def _leaves_view(leaves: dict[int, tuple[int, Decimal]]) -> dict[str, list]:
	return {str(t): [m, float(d)] for t, (m, d) in sorted(leaves.items())}


def _view(row: DailyAttendance) -> dict:
	view = {k: _plain(v) for k, v in audit.snapshot(row, exclude=("calculated_at",)).items()}
	view["leaves"] = _leaves_view({lv.leave_type_id: (lv.minutes, lv.days) for lv in row.leaves})
	return view


# who and which days ------------------------------------------------------------------------


def employees_on(session: Session, start: str, end: str) -> list[Employee]:
	"""Everyone employed at some point between two Jalali days."""
	return list(
		session.scalars(
			select(Employee)
			.where(
				Employee.status != SUSPENDED,
				Employee.start_date <= end,
				or_(Employee.end_date.is_(None), Employee.end_date >= start),
			)
			.order_by(Employee.id)
		)
	)


def recalculate(
	session: Session,
	dates: Iterable[str],
	today: str,
	reason: str,
	employee_ids: Iterable[int] | None = None,
	user_id: int | None = None,
) -> Outcome:
	"""Recalculate days for the given people (everyone employed on each day when None)."""
	days = sorted({d for d in dates if d <= today})
	outcome = Outcome()
	if not days:
		return outcome
	calc = Calculator(session, today, user_id)
	if employee_ids is None:
		ids = [e.id for e in employees_on(session, days[0], days[-1])]
	else:
		ids = sorted(set(employee_ids))
	for jdate in days:
		for employee_id in ids:
			calc.calculate(employee_id, jdate, reason, outcome)
	session.flush()
	return outcome


def recalculate_range(
	session: Session,
	start: str,
	end: str,
	today: str,
	reason: str,
	employee_ids: Iterable[int] | None = None,
	user_id: int | None = None,
) -> Outcome:
	return recalculate(
		session,
		iter_days(start, min(end, today)) if start <= today else [],
		today,
		reason,
		employee_ids,
		user_id,
	)


# disciplinary warnings (Article 27: never automatic dismissal) -------------------------------


def absence_warnings(session: Session, today: str, employee_ids: Iterable[int] | None = None) -> list[dict]:
	"""People whose consecutive absent days up to yesterday reach the configured threshold.
	A warning for the operator only; nothing else happens automatically."""
	threshold = int(settings.get(session, "absence_warning_days") or 0)
	if threshold <= 0:
		return []
	end = add_days(today, -1)
	start = add_days(end, -max(threshold * 3, 31))
	# days off do not break a streak: only scheduled days are looked at
	query = select(DailyAttendance.employee_id, DailyAttendance.jdate, DailyAttendance.absent_day).where(
		DailyAttendance.jdate.between(start, end),
		DailyAttendance.status.not_in((HOLIDAY, REST, OFF)),
	)
	if employee_ids is not None:
		query = query.where(DailyAttendance.employee_id.in_(list(employee_ids)))
	days: dict[int, list[tuple[str, bool]]] = {}
	for employee_id, jdate, absent in session.execute(query.order_by(DailyAttendance.jdate)):
		days.setdefault(employee_id, []).append((jdate, absent))
	out = []
	for employee_id, rows in days.items():
		streaks = absence_streaks(rows, threshold)
		if streaks and streaks[-1][1] == rows[-1][0]:  # still absent on the last scheduled day
			first, last, count = streaks[-1]
			out.append({"employee_id": employee_id, "from": first, "to": last, "days": count})
	return out
