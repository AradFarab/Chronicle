"""Which shift an employee works on a Jalali day.

Priority (design doc): one-day shift override, then an assignment to the employee, to their
designation, to their department (or the nearest parent department), then the company.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from hozur.db.models import Employee, Shift, ShiftOverride, WorkPattern, WorkPatternAssignment
from hozur.db.models.schedules import (
	FLEXIBLE,
	ROTATING,
	TARGET_COMPANY,
	TARGET_DEPARTMENT,
	TARGET_DESIGNATION,
	TARGET_EMPLOYEE,
)
from hozur.engine import model as engine
from hozur.jalali.dates import days_between, weekday
from hozur.services.access import ancestors

OVERRIDE, NONE = "override", "none"


@dataclass(frozen=True)
class Schedule:
	shift: engine.Shift | None
	shift_id: int | None
	rest_day: bool  # the weekly rest day of the pattern (Article 62)
	pattern_id: int | None
	rotating: bool
	source: str  # override / employee / designation / department / company / none


def minutes(value: time | None) -> int | None:
	return None if value is None else value.hour * 60 + value.minute


def shift_spec(s: Shift) -> engine.Shift:
	"""Database shift -> engine shift (minutes from the start of the attendance day)."""
	start, end = minutes(s.start_time), minutes(s.end_time)
	if end <= start:
		end += 1440
	b_start, b_end = minutes(s.break_start_time), minutes(s.break_end_time)
	if b_start is not None and b_end is not None:
		if b_start < start:
			b_start += 1440
		if b_end <= b_start:
			b_end += 1440
	flexible = s.shift_type == FLEXIBLE
	return engine.Shift(
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
		latest_start=minutes(s.latest_start_time) if flexible else None,
		required_minutes=s.required_minutes if flexible else None,
	)


class ScheduleResolver:
	"""Resolves many (employee, day) pairs with one session; caches what it reads."""

	def __init__(self, session: Session):
		self.session = session
		self._shifts: dict[int, engine.Shift] = {}
		self._patterns: dict[int, WorkPattern] = {}
		self._assignments: list[WorkPatternAssignment] | None = None
		self._employees: dict[int, Employee] = {}
		self._ancestors: dict[int | None, list[int]] = {}

	def shift(self, shift_id: int) -> engine.Shift:
		if shift_id not in self._shifts:
			self._shifts[shift_id] = shift_spec(self.session.get(Shift, shift_id))
		return self._shifts[shift_id]

	def pattern(self, pattern_id: int) -> WorkPattern:
		if pattern_id not in self._patterns:
			self._patterns[pattern_id] = self.session.get(WorkPattern, pattern_id)
		return self._patterns[pattern_id]

	def _all_assignments(self) -> list[WorkPatternAssignment]:
		if self._assignments is None:
			self._assignments = list(
				self.session.scalars(
					select(WorkPatternAssignment).order_by(WorkPatternAssignment.valid_from.desc())
				)
			)
		return self._assignments

	def _employee(self, employee_id: int) -> Employee:
		if employee_id not in self._employees:
			self._employees[employee_id] = self.session.get(Employee, employee_id)
		return self._employees[employee_id]

	def _department_chain(self, department_id: int | None) -> list[int]:
		if department_id not in self._ancestors:
			self._ancestors[department_id] = ancestors(self.session, department_id)
		return self._ancestors[department_id]

	def _assignment(self, target: str, value: int | None, jdate: str) -> int | None:
		if target != TARGET_COMPANY and not value:
			return None
		field = {
			TARGET_EMPLOYEE: "employee_id",
			TARGET_DESIGNATION: "designation_id",
			TARGET_DEPARTMENT: "department_id",
		}
		for a in self._all_assignments():  # newest valid_from first
			if a.target_type != target or a.valid_from > jdate or (a.valid_to and jdate > a.valid_to):
				continue
			if target == TARGET_COMPANY or getattr(a, field[target]) == value:
				return a.work_pattern_id
		return None

	def pattern_for(self, employee_id: int, jdate: str) -> tuple[int | None, str]:
		emp = self._employee(employee_id)
		for target, value in ((TARGET_EMPLOYEE, employee_id), (TARGET_DESIGNATION, emp.designation_id)):
			pattern = self._assignment(target, value, jdate)
			if pattern:
				return pattern, target
		for department in self._department_chain(emp.department_id):
			pattern = self._assignment(TARGET_DEPARTMENT, department, jdate)
			if pattern:
				return pattern, TARGET_DEPARTMENT
		pattern = self._assignment(TARGET_COMPANY, None, jdate)
		return (pattern, TARGET_COMPANY) if pattern else (None, NONE)

	def _pattern_day(self, pattern: WorkPattern, jdate: str) -> tuple[int | None, bool, bool]:
		"""(shift id or None, weekly rest day?, rotating?) for a day of a pattern."""
		if pattern.pattern_type == ROTATING:
			length = len(pattern.days)
			if not length:
				return None, True, True
			index = days_between(pattern.cycle_start_date, jdate) % length + 1
			row = next((d for d in pattern.days if d.cycle_day == index), None)
			shift_id = row.shift_id if row else None
			return shift_id, shift_id is None, True
		wd = weekday(jdate)
		row = next((d for d in pattern.days if d.weekday == wd), None)
		return (row.shift_id if row else None), wd == pattern.weekly_rest_day, False

	def resolve(self, employee_id: int, jdate: str) -> Schedule:
		override = self.session.scalar(
			select(ShiftOverride).where(
				ShiftOverride.employee_id == employee_id, ShiftOverride.jdate == jdate
			)
		)
		pattern_id, source = self.pattern_for(employee_id, jdate)
		pattern = self.pattern(pattern_id) if pattern_id else None
		rotating = bool(pattern) and pattern.pattern_type == ROTATING
		if override:
			shift = self.shift(override.shift_id) if override.shift_id else None
			return Schedule(shift, override.shift_id, False, pattern_id, rotating, OVERRIDE)
		if not pattern:
			return Schedule(None, None, False, None, False, NONE)
		shift_id, rest_day, rotating = self._pattern_day(pattern, jdate)
		return Schedule(
			self.shift(shift_id) if shift_id else None, shift_id, rest_day, pattern_id, rotating, source
		)


def resolve(session: Session, employee_id: int, jdate: str) -> Schedule:
	return ScheduleResolver(session).resolve(employee_id, jdate)


def employees_following(session: Session, pattern_id: int) -> set[int] | None:
	"""Employees a change of this pattern can affect (None = possibly everyone)."""
	rows = session.scalars(
		select(WorkPatternAssignment).where(WorkPatternAssignment.work_pattern_id == pattern_id)
	).all()
	if any(a.target_type != TARGET_EMPLOYEE for a in rows):
		return None
	return {a.employee_id for a in rows}
