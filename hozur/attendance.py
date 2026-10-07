"""Daily Attendance: gather one employee-day's inputs, run the engine, store the result.

Daily Attendance is never edited by hand; it is always rebuilt from punches, approved
requests, the schedule, the calendar and the rule set. A recalculation that changes a stored
day writes an Audit Entry. Days in closed periods are never touched.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from hozur import audit
from hozur.engine.daily import calculate_day
from hozur.engine.model import Absence, DailyResult, Day, EmployeeFlags, OvertimeApproval, Punch
from hozur.engine.periodic import absence_streaks
from hozur.jalali.calendar import resolve_day_type
from hozur.jalali.dates import add_days, iter_days, parse_jdate
from hozur.periods import is_locked
from hozur.punches import effective_punches
from hozur.rule_sets import get_rule_set
from hozur.schedule import Schedule, resolve, time_to_minutes
from hozur.utils import clear_request_cache, now_jalali, today_jalali

NEXT_DAY_BUFFER = 240  # minutes after an overnight shift whose punches still belong to it
INLINE_LIMIT = 40  # employee-days recalculated in the request; more go to a background job

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


def attendance_name(employee: str, jdate: str) -> str:
	return f"{employee}:{jdate}"


def _minute_label(minute: int | None) -> str | None:
	if minute is None:
		return None
	label = f"{minute % 1440 // 60:02d}:{minute % 60:02d}"
	return label + " (+1)" if minute >= 1440 else label


def _employed(emp, jdate: str) -> bool:
	return (
		emp.status != "Suspended"
		and bool(emp.start_date)
		and emp.start_date <= jdate
		and (not emp.end_date or jdate <= emp.end_date)
	)


def _age_on(birth_date: str, jdate: str) -> int:
	by, bm, bd = parse_jdate(birth_date)
	y, m, d = parse_jdate(jdate)
	return y - by - (1 if (m, d) < (bm, bd) else 0)


def _flags(emp, jdate: str, schedule: Schedule, rules) -> EmployeeFlags:
	hard = bool(emp.designation and frappe.db.get_value("Designation", emp.designation, "hard_harmful"))
	return EmployeeFlags(
		juvenile=bool(emp.birth_date) and _age_on(emp.birth_date, jdate) < rules.juvenile_max_age_years,
		hard_harmful=hard,
		nursing=bool(emp.nursing_until) and jdate <= emp.nursing_until,
		rotating=schedule.rotating,
		standing_overtime_consent=bool(emp.overtime_consent_on_file)
		and (not emp.overtime_consent_date or emp.overtime_consent_date <= jdate),
	)


def _punch_window(jdate: str, schedule: Schedule, previous: Schedule, following: Schedule) -> tuple[int, int]:
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


def _punches(employee: str, jdate: str, window: tuple[int, int]) -> list[Punch]:
	nxt = add_days(jdate, 1)
	out = []
	for p in effective_punches(employee, jdate, nxt if window[1] > 86400 else jdate):
		h, m, s = (int(x) for x in p["time"].split(":"))
		second = h * 3600 + m * 60 + s + (86400 if p["jdate"] == nxt else 0)
		if window[0] <= second < window[1]:
			out.append(Punch(second, p["direction"]))
	return out


def _absences(employee: str, jdate: str) -> list[Absence]:
	out = []
	approved = {"employee": employee, "docstatus": 1, "status": "Approved"}
	for doctype, kind in (("Leave Application", "Leave"), ("Mission", "Mission")):
		unit_field = "leave_unit" if kind == "Leave" else "mission_unit"
		fields = ["name", unit_field, "from_time", "to_time"] + (["leave_type"] if kind == "Leave" else [])
		rows = frappe.get_all(
			doctype,
			filters={**approved, "start_jdate": ["<=", jdate], "end_jdate": [">=", jdate]},
			fields=fields,
		)
		for r in rows:
			if kind == "Leave":
				type_name, paid = (
					r.leave_type,
					bool(frappe.get_cached_value("Leave Type", r.leave_type, "is_paid")),
				)
			else:
				type_name, paid = "Mission", True
			if r.get(unit_field) == "Hourly":
				out.append(
					Absence(kind, type_name, time_to_minutes(r.from_time), time_to_minutes(r.to_time), paid)
				)
			else:
				out.append(Absence(kind, type_name, paid=paid))
	return out


def _overtime(employee: str, jdate: str) -> list[OvertimeApproval]:
	rows = frappe.get_all(
		"Overtime Request",
		filters={"employee": employee, "jdate": jdate, "docstatus": 1, "status": "Approved"},
		fields=["minutes", "overtime_kind"],
	)
	return [OvertimeApproval(r.minutes, r.overtime_kind) for r in rows]


def _calendar_day(jdate: str):
	day = frappe.db.get_value("Calendar Day", jdate, ["weekday", "weekday_name", "day_type"], as_dict=True)
	if not day:
		from hozur.calendar_sync import generate_year

		generate_year(int(jdate[:4]))
		day = frappe.db.get_value(
			"Calendar Day", jdate, ["weekday", "weekday_name", "day_type"], as_dict=True
		)
	return day


def calculate(employee: str, jdate: str, reason: str | None = None) -> DailyResult | None:
	"""Calculate and store one employee-day. Returns None when the day is locked or the
	person was not employed that day."""
	if is_locked(jdate):
		return None
	emp = frappe.db.get_value(
		"Employee",
		employee,
		[
			"name",
			"full_name",
			"status",
			"start_date",
			"end_date",
			"branch",
			"department",
			"designation",
			"birth_date",
			"nursing_until",
			"overtime_consent_on_file",
			"overtime_consent_date",
		],
		as_dict=True,
	)
	name = attendance_name(employee, jdate)
	if not emp or not _employed(emp, jdate):
		if frappe.db.exists("Daily Attendance", name):
			frappe.delete_doc("Daily Attendance", name, ignore_permissions=True, force=True)
		return None

	calendar_day = _calendar_day(jdate)
	holidays = frappe.get_all(
		"Iran Holiday",
		filters={"jdate": jdate},
		fields=["title", "holiday_type", "status", "scope", "province", "branch", "closure_pay_mode"],
	)
	province = frappe.db.get_value("Branch", emp.branch, "province") if emp.branch else None
	day_info = resolve_day_type(calendar_day, holidays, emp.branch, province)
	schedule = resolve(employee, jdate)
	window = _punch_window(
		jdate, schedule, resolve(employee, add_days(jdate, -1)), resolve(employee, add_days(jdate, 1))
	)
	punches = _punches(employee, jdate, window)
	rule_name, rules = get_rule_set(jdate)
	result = calculate_day(
		Day(
			jdate=jdate,
			weekday=calendar_day.weekday,
			day_type=day_info["day_type"],
			rest_day=schedule.rest_day,
		),
		schedule.shift,
		punches,
		rules,
		_flags(emp, jdate, schedule, rules),
		_absences(employee, jdate),
		_overtime(employee, jdate),
	)
	year, month, _day = parse_jdate(jdate)
	values = {
		"employee": employee,
		"employee_name": emp.full_name,
		"jdate": jdate,
		"jyear": year,
		"jmonth": month,
		"weekday_name": calendar_day.weekday_name,
		"department": emp.department,
		"branch": emp.branch,
		"designation": emp.designation,
		"day_type": day_info["day_type"],
		"holiday_title": " / ".join(day_info["titles"]) or None,
		"work_pattern": schedule.pattern,
		"shift": schedule.shift_name,
		"rest_day": int(schedule.rest_day),
		"rule_set": rule_name,
		"first_in": _minute_label(result.first_in),
		"last_out": _minute_label(result.last_out),
		"punch_count": len(punches),
		**{
			f: int(getattr(result, f)) if isinstance(getattr(result, f), bool) else getattr(result, f)
			for f in RESULT_FIELDS
		},
		"leave_minutes": sum(result.leave_minutes.values()),
		"leave_days": round(sum(result.leave_days.values()), 4),
		"overtime_normal_minutes": result.overtime_minutes.get("Normal", 0),
		"overtime_exceptional_minutes": result.overtime_minutes.get("Exceptional", 0),
		"overtime_emergency_minutes": result.overtime_minutes.get("Emergency", 0),
		"warnings": ", ".join(result.warnings) or None,
	}
	leaves = [
		{"leave_type": t, "minutes": m, "days": result.leave_days.get(t, 0)}
		for t, m in sorted(result.leave_minutes.items())
	]
	_store(name, values, leaves, reason)
	return result


def _comparable(values: dict, leaves: list[dict]) -> dict:
	return {**{k: (v if v not in ("", None) else None) for k, v in values.items()}, "leaves": leaves}


def _store(name: str, values: dict, leaves: list[dict], reason: str | None) -> None:
	jdate, time = now_jalali()
	if frappe.db.exists("Daily Attendance", name):
		doc = frappe.get_doc("Daily Attendance", name)
		old_leaves = [{"leave_type": r.leave_type, "minutes": r.minutes, "days": r.days} for r in doc.leaves]
		before = _comparable({k: doc.get(k) for k in values}, old_leaves)
		after = _comparable(values, leaves)
		changed = sorted(k for k in after if before.get(k) != after.get(k))
		if not changed:
			return
		doc.update(values)
		doc.set("leaves", leaves)
		doc.calculated_at = f"{jdate} {time}"
		doc.flags.from_engine = True
		doc.save(ignore_permissions=True)
		audit.log(
			"Daily Attendance",
			name,
			"Update",
			reason or _("Recalculated"),
			before={k: before.get(k) for k in changed},
			after={k: after.get(k) for k in changed},
			changed=changed,
		)
		return
	doc = frappe.get_doc(
		{"doctype": "Daily Attendance", **values, "leaves": leaves, "calculated_at": f"{jdate} {time}"}
	)
	doc.flags.from_engine = True
	doc.insert(ignore_permissions=True, set_name=name)


# recalculation ------------------------------------------------------------------------


def recalculate(employee: str, start: str, end: str | None = None, reason: str | None = None) -> int:
	"""Recalculate employee-days from start to end (inclusive, never past today)."""
	end = min(end or start, today_jalali())
	count = 0
	for jdate in iter_days(start, end) if start <= end else []:
		calculate(employee, jdate, reason)
		count += 1
	return count


def recalculate_pairs(pairs: list[tuple[str, str]], reason: str | None = None) -> None:
	today = today_jalali()
	for employee, jdate in sorted(set(pairs)):
		if jdate <= today:
			calculate(employee, jdate, reason)


def schedule_recalculation(pairs, reason: str | None = None) -> None:
	"""Recalculate now when it is small, otherwise in a background job."""
	pairs = sorted(set(pairs))
	if not pairs:
		return
	clear_request_cache()  # the change that triggered this may have been made in this request
	if len(pairs) <= INLINE_LIMIT or frappe.flags.in_test:
		recalculate_pairs(pairs, reason)
	else:
		frappe.enqueue(
			"hozur.attendance.recalculate_pairs",
			queue="long",
			timeout=3600,
			pairs=pairs,
			reason=reason,
			enqueue_after_commit=True,
		)


def active_employees(jdate: str) -> list[str]:
	return [
		r.name
		for r in frappe.get_all(
			"Employee", filters={"status": ["!=", "Suspended"]}, fields=["name", "start_date", "end_date"]
		)
		if r.start_date and r.start_date <= jdate and (not r.end_date or jdate <= r.end_date)
	]


def recalculate_everyone(start: str, end: str, reason: str | None = None) -> None:
	end = min(end, today_jalali())
	if start > end:
		return
	pairs = [(e, d) for d in iter_days(start, end) for e in active_employees(d)]
	schedule_recalculation(pairs, reason)


def on_punches(device: str, keys: list[tuple[str, str]]) -> None:
	"""New raw punches (device user id, Jalali day): recalculate the mapped employees' days."""
	pairs = []
	for user_id, jdate in set(keys):
		for m in frappe.get_all(
			"Device User Map",
			filters={"device": device, "device_user_id": user_id, "employee": ["is", "set"]},
			fields=["employee", "valid_from", "valid_to"],
		):
			if (not m.valid_from or m.valid_from <= jdate) and (not m.valid_to or jdate <= m.valid_to):
				pairs += [(m.employee, jdate), (m.employee, add_days(jdate, -1))]  # overnight shifts
	schedule_recalculation(pairs, _("New punches from {0}").format(device))


# scheduler ------------------------------------------------------------------------------


def nightly() -> None:
	"""Daily job: yesterday and today for everyone, monthly leave accrual, year-end expiry,
	absence warnings."""
	today = today_jalali()
	yesterday = add_days(today, -1)
	recalculate_everyone(yesterday, today, _("Nightly calculation"))
	from hozur.leave import allocate_month, close_leave_year

	if today.endswith("/01"):
		allocate_month(yesterday[:7])
		if today[5:7] == "01":
			close_leave_year(int(yesterday[:4]))
	warn_absences(yesterday)


def warn_absences(jdate: str) -> None:
	"""Disciplinary warning only (Article 27 has no automatic dismissal): consecutive absent
	days ending on jdate reaching the threshold notify the operators."""
	threshold = frappe.db.get_single_value("Hozur Settings", "absence_warning_days") or 0
	if threshold <= 0:
		return
	start = add_days(jdate, -threshold + 1)
	operators = frappe.get_all(
		"Has Role", filters={"role": "Hozur Operator", "parenttype": "User"}, pluck="parent", distinct=True
	)
	for employee in active_employees(jdate):
		rows = frappe.get_all(
			"Daily Attendance",
			filters={"employee": employee, "jdate": ["between", [start, jdate]]},
			fields=["jdate", "absent_day", "status"],
			order_by="jdate",
		)
		streaks = absence_streaks([(r.jdate, bool(r.absent_day)) for r in rows], threshold)
		if not streaks or streaks[-1][1] != jdate:
			continue
		subject = _("{0} has been absent {1} days in a row (until {2})").format(
			employee, streaks[-1][2], jdate
		)
		for user in operators:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": subject,
					"document_type": "Employee",
					"document_name": employee,
				}
			).insert(ignore_permissions=True)


@frappe.whitelist()
def recalculate_range(employee: str, start: str, end: str) -> int:
	"""Operator button: recalculate one employee for a range of Jalali days."""
	from hozur.jalali.dates import normalize_jdate

	frappe.only_for(["System Manager", "Hozur Operator"])
	start, end = normalize_jdate(start), normalize_jdate(end)
	return recalculate(employee, start, end, _("Recalculated by {0}").format(frappe.session.user))


@frappe.whitelist()
def day_details(employee: str, jdate: str) -> dict:
	"""Everything that went into a day, for the PWA day view."""
	from hozur.permissions import visible_employees

	allowed = visible_employees()
	if allowed is not None and employee not in allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return {
		"attendance": frappe.db.get_value(
			"Daily Attendance", attendance_name(employee, jdate), "*", as_dict=True
		),
		"punches": effective_punches(employee, jdate),
		"schedule": json.loads(json.dumps(resolve(employee, jdate).__dict__, default=lambda o: o.__dict__)),
	}
