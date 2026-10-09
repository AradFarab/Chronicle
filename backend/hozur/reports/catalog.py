"""The fields an operator can put in a report. The server accepts nothing else (design doc).
Pure Python: labels are English source strings, translated by the caller."""

from __future__ import annotations

from dataclasses import dataclass


def _(text: str) -> str:
	"""Marks a label for translation extraction; the caller translates it at runtime."""
	return text


DAILY, SUMMARY = "daily", "summary"
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
	_f("employee", _("Employee Code"), _("Identity"), TEXT),
	_f("employee_name", _("Full Name"), _("Identity"), TEXT),
	_f("national_id", _("National Code"), _("Identity"), TEXT, column=None),
	_f("work_location", _("Work location"), _("Identity"), TEXT),
	_f("department", _("Department"), _("Identity"), TEXT),
	_f("designation", _("Designation"), _("Identity"), TEXT),
	# the day (daily rows only)
	_f("jdate", _("Date"), _("Day"), DATE, (DAILY,)),
	_f("weekday_name", _("Weekday"), _("Day"), TEXT, (DAILY,)),
	_f("status", _("Status"), _("Day"), TEXT, (DAILY,)),
	_f("day_type", _("Day Type"), _("Day"), TEXT, (DAILY,)),
	_f("holiday_title", _("Holiday"), _("Day"), TEXT, (DAILY,)),
	_f("shift", _("Shift"), _("Day"), TEXT, (DAILY,)),
	_f("first_in", _("First In"), _("Day"), TEXT, (DAILY,)),
	_f("last_out", _("Last Out"), _("Day"), TEXT, (DAILY,)),
	_f("warnings", _("Warnings"), _("Day"), TEXT, (DAILY,)),
	# presence
	_f("required_minutes", _("Required"), _("Presence"), MINUTES),
	_f("worked_minutes", _("Worked"), _("Presence"), MINUTES),
	_f("credited_minutes", _("Credited Work"), _("Presence"), MINUTES),
	_f("late_minutes", _("Late"), _("Presence"), MINUTES),
	_f("early_leave_minutes", _("Early Leave"), _("Presence"), MINUTES),
	_f("absence_minutes", _("Absence (Hours)"), _("Presence"), MINUTES),
	_f("absent_days", _("Absence (Days)"), _("Presence"), COUNT, column="absent_day"),
	# extra work
	_f("overtime_normal_minutes", _("Overtime"), _("Extra Work"), MINUTES),
	_f("overtime_exceptional_minutes", _("Exceptional Overtime"), _("Extra Work"), MINUTES),
	_f("overtime_emergency_minutes", _("Emergency Overtime"), _("Extra Work"), MINUTES),
	_f("overtime_total_minutes", _("Total Overtime"), _("Extra Work"), MINUTES, column=None),
	_f("unapproved_extra_minutes", _("Unapproved Extra Work"), _("Extra Work"), MINUTES),
	_f("night_work_minutes", _("Night Work"), _("Extra Work"), MINUTES),
	_f("rest_day_work_minutes", _("Rest Day Work"), _("Extra Work"), MINUTES),
	_f("friday_premium_minutes", _("Friday Work"), _("Extra Work"), MINUTES),
	_f("holiday_work_minutes", _("Holiday Work"), _("Extra Work"), MINUTES),
	_f("company_holiday_work_minutes", _("Company Holiday Work"), _("Extra Work"), MINUTES),
	# leave and mission
	_f("leave_days", _("Leave (Days)"), _("Leave and Mission"), DAYS),
	_f("leave_minutes", _("Leave (Hours)"), _("Leave and Mission"), MINUTES),
	_f("mission_minutes", _("Mission (Hours)"), _("Leave and Mission"), MINUTES),
	_f("mission_days", _("Mission (Days)"), _("Leave and Mission"), COUNT, column=None),
	_f("nursing_minutes", _("Nursing Breaks"), _("Leave and Mission"), MINUTES),
	_f("leave_balance", _("Leave Balance (Days)"), _("Leave and Mission"), DAYS, (SUMMARY,), column=None),
	# day counts (one row per employee)
	_f("employed_days", _("Days Employed"), _("Days"), COUNT, (SUMMARY,), column=None),
	_f("present_days", _("Days Present"), _("Days"), COUNT, (SUMMARY,), column=None),
	_f("holiday_days", _("Holidays"), _("Days"), COUNT, (SUMMARY,), column=None),
	_f("rest_days", _("Rest Days"), _("Days"), COUNT, (SUMMARY,), column=None),
	_f("paid_days", _("Paid Days (Attendance)"), _("Days"), DAYS, (SUMMARY,), column=None),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}
LEAVE_PREFIX = "leave:"  # dynamic: one column per Leave Type, in days


def leave_field(leave_type: str) -> Field:
	return Field(LEAVE_PREFIX + leave_type, leave_type, _("Leave by Type"), DAYS, BOTH, None)


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
