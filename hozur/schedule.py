"""Which shift an employee works on a Jalali day.

Priority (design doc): one-day Shift Override, then an assignment to the employee, to their
designation, to their department (or the nearest parent department), then the company.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import frappe
from frappe.utils.caching import request_cache

from hozur.engine.model import Shift
from hozur.jalali.dates import WEEKDAY_NAMES, days_between, weekday

WEEKDAYS = ("Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
assert len(WEEKDAYS) == len(WEEKDAY_NAMES)


@dataclass(frozen=True)
class Schedule:
	shift: Shift | None
	shift_name: str | None
	rest_day: bool
	pattern: str | None
	rotating: bool
	source: str  # Override / Employee / Designation / Department / Company / None


def time_to_minutes(value) -> int | None:
	if value in (None, ""):
		return None
	if isinstance(value, timedelta):
		return int(value.total_seconds() // 60)
	parts = str(value).split(":")
	return int(parts[0]) * 60 + int(parts[1])


@request_cache
def shift_spec(name: str) -> Shift:
	s = frappe.get_cached_doc("Shift", name)
	start = time_to_minutes(s.start_time)
	end = time_to_minutes(s.end_time)
	if end <= start:
		end += 1440
	b_start, b_end = time_to_minutes(s.break_start_time), time_to_minutes(s.break_end_time)
	if b_start is not None and b_end is not None:
		if b_start < start:
			b_start += 1440
		if b_end <= b_start:
			b_end += 1440
	flexible = s.shift_type == "Flexible"
	return Shift(
		name=s.name,
		start=start,
		end=end,
		break_start=b_start,
		break_end=b_end,
		break_minutes=s.break_minutes or 0,
		grace_late=s.grace_late_minutes or 0,
		grace_early=s.grace_early_minutes or 0,
		overtime_after=s.overtime_after_minutes or 0,
		flexible=flexible,
		latest_start=time_to_minutes(s.latest_start_time) if flexible else None,
		required_minutes=s.required_minutes if flexible else None,
	)


def _assignment(field: str | None, value: str | None, jdate: str) -> str | None:
	filters = {"valid_from": ["<=", jdate]}
	if field:
		if not value:
			return None
		filters[field] = value
		filters["assign_to"] = field.title()
	else:
		filters["assign_to"] = "Company"
	for row in frappe.get_all(
		"Work Pattern Assignment",
		filters=filters,
		fields=["work_pattern", "valid_to"],
		order_by="valid_from desc",
	):
		if not row.valid_to or jdate <= row.valid_to:
			return row.work_pattern
	return None


@request_cache
def pattern_for(employee: str, jdate: str) -> tuple[str | None, str]:
	emp = frappe.db.get_value("Employee", employee, ["designation", "department"], as_dict=True)
	pattern = _assignment("employee", employee, jdate)
	if pattern:
		return pattern, "Employee"
	pattern = _assignment("designation", emp.designation, jdate)
	if pattern:
		return pattern, "Designation"
	department = emp.department
	while department:
		pattern = _assignment("department", department, jdate)
		if pattern:
			return pattern, "Department"
		department = frappe.db.get_value("Department", department, "parent_department")
	pattern = _assignment(None, None, jdate)
	return (pattern, "Company") if pattern else (None, "None")


def _pattern_day(pattern_name: str, jdate: str) -> tuple[str | None, bool, bool]:
	"""(shift name or None, weekly rest day?, rotating?) for a day of a pattern."""
	p = frappe.get_cached_doc("Work Pattern", pattern_name)
	if p.pattern_type == "Rotating":
		length = len(p.days)
		index = days_between(p.cycle_start_date, jdate) % length + 1
		row = next((d for d in p.days if d.cycle_day == index), None)
		shift = row.shift if row else None
		return shift, shift is None, True
	name = WEEKDAYS[weekday(jdate)]
	row = next((d for d in p.days if d.weekday == name), None)
	return (row.shift if row else None), name == p.weekly_rest_day, False


@request_cache
def resolve(employee: str, jdate: str) -> Schedule:
	override = frappe.db.get_value(
		"Shift Override", {"employee": employee, "jdate": jdate}, ["shift"], as_dict=True
	)
	pattern, source = pattern_for(employee, jdate)
	rotating = bool(pattern) and frappe.get_cached_doc("Work Pattern", pattern).pattern_type == "Rotating"
	if override:
		shift_name = override.shift or None
		return Schedule(
			shift_spec(shift_name) if shift_name else None, shift_name, False, pattern, rotating, "Override"
		)
	if not pattern:
		return Schedule(None, None, False, None, False, "None")
	shift_name, rest_day, rotating = _pattern_day(pattern, jdate)
	return Schedule(
		shift_spec(shift_name) if shift_name else None, shift_name, rest_day, pattern, rotating, source
	)
