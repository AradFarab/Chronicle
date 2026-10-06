"""The fields an operator can put in a report. The server accepts nothing else (design doc).
Pure Python: labels are English source strings, translated by the caller."""

from __future__ import annotations

from dataclasses import dataclass

DAILY, SUMMARY = "Daily", "Summary"
BOTH = (DAILY, SUMMARY)

# kinds decide formatting: minutes follow the report's time unit; days and counts are numbers
TEXT, DATE, MINUTES, DAYS, COUNT = "text", "date", "minutes", "days", "count"


@dataclass(frozen=True)
class Field:
	key: str
	label: str
	group: str
	kind: str
	sources: tuple[str, ...] = BOTH
	column: str | None = None  # Daily Attendance column it comes from


def _f(key, label, group, kind, sources=BOTH, column=None):
	return Field(key, label, group, kind, sources, column or key)


FIELDS: tuple[Field, ...] = (
	# identity
	_f("employee", "Employee Code", "Identity", TEXT),
	_f("employee_name", "Full Name", "Identity", TEXT),
	_f("national_id", "National Code", "Identity", TEXT, column=None),
	_f("branch", "Branch", "Identity", TEXT),
	_f("department", "Department", "Identity", TEXT),
	_f("designation", "Designation", "Identity", TEXT),
	# the day (daily rows only)
	_f("jdate", "Date", "Day", DATE, (DAILY,)),
	_f("weekday_name", "Weekday", "Day", TEXT, (DAILY,)),
	_f("status", "Status", "Day", TEXT, (DAILY,)),
	_f("day_type", "Day Type", "Day", TEXT, (DAILY,)),
	_f("holiday_title", "Holiday", "Day", TEXT, (DAILY,)),
	_f("shift", "Shift", "Day", TEXT, (DAILY,)),
	_f("first_in", "First In", "Day", TEXT, (DAILY,)),
	_f("last_out", "Last Out", "Day", TEXT, (DAILY,)),
	_f("warnings", "Warnings", "Day", TEXT, (DAILY,)),
	# presence
	_f("required_minutes", "Required", "Presence", MINUTES),
	_f("worked_minutes", "Worked", "Presence", MINUTES),
	_f("credited_minutes", "Credited Work", "Presence", MINUTES),
	_f("late_minutes", "Late", "Presence", MINUTES),
	_f("early_leave_minutes", "Early Leave", "Presence", MINUTES),
	_f("absence_minutes", "Absence (Hours)", "Presence", MINUTES),
	_f("absent_days", "Absence (Days)", "Presence", COUNT, column="absent_day"),
	# extra work
	_f("overtime_normal_minutes", "Overtime", "Extra Work", MINUTES),
	_f("overtime_exceptional_minutes", "Exceptional Overtime", "Extra Work", MINUTES),
	_f("overtime_emergency_minutes", "Emergency Overtime", "Extra Work", MINUTES),
	_f("overtime_total_minutes", "Total Overtime", "Extra Work", MINUTES, column=None),
	_f("unapproved_extra_minutes", "Unapproved Extra Work", "Extra Work", MINUTES),
	_f("night_work_minutes", "Night Work", "Extra Work", MINUTES),
	_f("rest_day_work_minutes", "Rest Day Work", "Extra Work", MINUTES),
	_f("friday_premium_minutes", "Friday Work", "Extra Work", MINUTES),
	_f("holiday_work_minutes", "Holiday Work", "Extra Work", MINUTES),
	_f("company_holiday_work_minutes", "Company Holiday Work", "Extra Work", MINUTES),
	# leave and mission
	_f("leave_days", "Leave (Days)", "Leave and Mission", DAYS),
	_f("leave_minutes", "Leave (Hours)", "Leave and Mission", MINUTES),
	_f("mission_minutes", "Mission (Hours)", "Leave and Mission", MINUTES),
	_f("mission_days", "Mission (Days)", "Leave and Mission", COUNT, column=None),
	_f("nursing_minutes", "Nursing Breaks", "Leave and Mission", MINUTES),
	_f("leave_balance", "Leave Balance (Days)", "Leave and Mission", DAYS, (SUMMARY,), column=None),
	# day counts (one row per employee)
	_f("employed_days", "Days Employed", "Days", COUNT, (SUMMARY,), column=None),
	_f("present_days", "Days Present", "Days", COUNT, (SUMMARY,), column=None),
	_f("holiday_days", "Holidays", "Days", COUNT, (SUMMARY,), column=None),
	_f("rest_days", "Rest Days", "Days", COUNT, (SUMMARY,), column=None),
	_f("paid_days", "Paid Days (Attendance)", "Days", DAYS, (SUMMARY,), column=None),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}
LEAVE_PREFIX = "leave:"  # dynamic: one column per Leave Type, in days


def leave_field(leave_type: str) -> Field:
	return Field(LEAVE_PREFIX + leave_type, leave_type, "Leave by Type", DAYS, BOTH, None)


def resolve(key: str, source: str, leave_types: set[str]) -> Field:
	"""The catalog field for a key, or ValueError: reports cannot ask for anything else."""
	if key.startswith(LEAVE_PREFIX):
		name = key[len(LEAVE_PREFIX) :]
		if name not in leave_types:
			raise ValueError(f"unknown leave type {name!r}")
		return leave_field(name)
	field = FIELD_BY_KEY.get(key)
	if not field:
		raise ValueError(f"unknown report field {key!r}")
	if source not in field.sources:
		raise ValueError(f"{key!r} is not available in {source} reports")
	return field
