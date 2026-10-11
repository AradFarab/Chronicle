"""Shifts, work patterns, who follows which pattern, and one-day overrides."""

from __future__ import annotations

from datetime import time

from sqlalchemy import (
	BigInteger,
	CheckConstraint,
	ForeignKey,
	Integer,
	SmallInteger,
	String,
	Text,
	Time,
	UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.types import JDate, enum_check

FIXED, FLEXIBLE = "fixed", "flexible"
WEEKLY, ROTATING = "weekly", "rotating"
TARGET_EMPLOYEE, TARGET_DESIGNATION, TARGET_DEPARTMENT, TARGET_COMPANY = (
	"employee",
	"designation",
	"department",
	"company",
)
ASSIGNMENT_TARGETS = (TARGET_EMPLOYEE, TARGET_DESIGNATION, TARGET_DEPARTMENT, TARGET_COMPANY)
BREAK, OVERTIME_WINDOW = "break", "overtime"
SEGMENT_KINDS = (BREAK, OVERTIME_WINDOW)
TWO_DAYS = 2880  # segment minutes run from the shift day's 00:00 into the next day


class Shift(IdMixin, TimestampMixin, Base):
	__tablename__ = "shift"
	__table_args__ = (
		enum_check("shift_type", (FIXED, FLEXIBLE)),
		CheckConstraint(
			"grace_late_minutes >= 0 AND grace_early_minutes >= 0 AND overtime_after_minutes >= 0 "
			"AND break_minutes >= 0 AND (required_minutes IS NULL OR required_minutes > 0)",
			name="minutes_non_negative",
		),
		CheckConstraint(
			"shift_type = 'fixed' OR required_minutes IS NOT NULL", name="flexible_needs_required_minutes"
		),
	)

	name: Mapped[str] = mapped_column(String(100), unique=True)
	shift_type: Mapped[str] = mapped_column(String(20), server_default=FIXED)
	color: Mapped[str | None] = mapped_column(String(20))
	start_time: Mapped[time] = mapped_column(Time)  # flexible: earliest start
	end_time: Mapped[time] = mapped_column(Time)  # earlier than start = ends after midnight
	latest_start_time: Mapped[time | None] = mapped_column(Time)  # flexible only
	required_minutes: Mapped[int | None] = mapped_column(Integer)  # flexible only
	break_minutes: Mapped[int] = mapped_column(Integer, server_default="0")  # break without a window
	# Tolerances: up to this late / early is forgiven; beyond it the whole time counts.
	grace_late_minutes: Mapped[int] = mapped_column(Integer, server_default="0")
	grace_early_minutes: Mapped[int] = mapped_column(Integer, server_default="0")
	# Work after the end up to this long is ignored; beyond it the whole time is extra work.
	overtime_after_minutes: Mapped[int] = mapped_column(Integer, server_default="0")

	segments: Mapped[list[ShiftSegment]] = relationship(
		cascade="all, delete-orphan", order_by="ShiftSegment.start_minute", lazy="selectin"
	)

	@property
	def crosses_midnight(self) -> bool:
		return self.end_time <= self.start_time


class ShiftSegment(IdMixin, Base):
	"""A timed part of a shift drawn in the PWA: a break (lunch, prayer, tea; never working time,
	Article 51) or a window in which extra work may become overtime (still only with the
	employee's request and approval, Article 59). Minutes count from the shift day's 00:00, so
	02:00 the next morning is 1560."""

	__tablename__ = "shift_segment"
	__table_args__ = (
		enum_check("kind", SEGMENT_KINDS),
		CheckConstraint(
			f"start_minute >= 0 AND end_minute > start_minute AND end_minute <= {TWO_DAYS}",
			name="minute_range",
		),
	)

	shift_id: Mapped[int] = mapped_column(ForeignKey("shift.id", ondelete="CASCADE"), index=True)
	kind: Mapped[str] = mapped_column(String(20))
	start_minute: Mapped[int] = mapped_column(Integer)
	end_minute: Mapped[int] = mapped_column(Integer)


class WorkPattern(IdMixin, TimestampMixin, Base):
	__tablename__ = "work_pattern"
	__table_args__ = (
		enum_check("pattern_type", (WEEKLY, ROTATING)),
		CheckConstraint("weekly_rest_day BETWEEN 0 AND 6", name="weekly_rest_day_range"),
		CheckConstraint(
			"pattern_type = 'weekly' OR cycle_start_date IS NOT NULL", name="rotating_needs_start"
		),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	pattern_type: Mapped[str] = mapped_column(String(20), server_default=WEEKLY)
	weekly_rest_day: Mapped[int | None] = mapped_column(SmallInteger, server_default="6")  # 0 = Saturday
	cycle_start_date: Mapped[str | None] = mapped_column(JDate)  # rotating: the day that is cycle day 1
	description: Mapped[str | None] = mapped_column(Text)
	change_reason: Mapped[str | None] = mapped_column(Text)

	days: Mapped[list[WorkPatternDay]] = relationship(
		cascade="all, delete-orphan", order_by="WorkPatternDay.id", lazy="selectin"
	)


class WorkPatternDay(IdMixin, Base):
	__tablename__ = "work_pattern_day"
	__table_args__ = (
		CheckConstraint("(weekday IS NULL) <> (cycle_day IS NULL)", name="weekday_or_cycle_day"),
		CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
		CheckConstraint("cycle_day >= 1", name="cycle_day_positive"),
		UniqueConstraint("work_pattern_id", "weekday"),
		UniqueConstraint("work_pattern_id", "cycle_day"),
	)

	work_pattern_id: Mapped[int] = mapped_column(ForeignKey("work_pattern.id", ondelete="CASCADE"))
	weekday: Mapped[int | None] = mapped_column(SmallInteger)  # weekly patterns, 0 = Saturday
	cycle_day: Mapped[int | None] = mapped_column(SmallInteger)  # rotating patterns, 1..n
	shift_id: Mapped[int | None] = mapped_column(ForeignKey("shift.id"))  # NULL = rest day

	shift: Mapped[Shift | None] = relationship(lazy="joined")


class WorkPatternAssignment(IdMixin, TimestampMixin, Base):
	"""Resolution order: employee, designation, department, company. For a rotating pattern,
	`cycle_offset_days` shifts this group along the cycle, so two groups of guards can follow the
	same pattern half a cycle apart."""

	__tablename__ = "work_pattern_assignment"
	__table_args__ = (
		enum_check("target_type", ASSIGNMENT_TARGETS),
		CheckConstraint(
			"(target_type = 'employee') = (employee_id IS NOT NULL) "
			"AND (target_type = 'designation') = (designation_id IS NOT NULL) "
			"AND (target_type = 'department') = (department_id IS NOT NULL)",
			name="target_matches_type",
		),
		CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
		CheckConstraint("cycle_offset_days >= 0", name="cycle_offset_non_negative"),
	)

	target_type: Mapped[str] = mapped_column(String(20))
	employee_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"), index=True)
	designation_id: Mapped[int | None] = mapped_column(ForeignKey("designation.id", ondelete="CASCADE"))
	department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id", ondelete="CASCADE"))
	work_pattern_id: Mapped[int] = mapped_column(ForeignKey("work_pattern.id"))
	valid_from: Mapped[str] = mapped_column(JDate)
	valid_to: Mapped[str | None] = mapped_column(JDate)
	cycle_offset_days: Mapped[int] = mapped_column(Integer, server_default="0")
	note: Mapped[str | None] = mapped_column(Text)


class ShiftOverride(IdMixin, TimestampMixin, Base):
	"""A one-day change for one person; no shift = day off."""

	__tablename__ = "shift_override"
	__table_args__ = (UniqueConstraint("employee_id", "jdate"),)

	employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employee.id", ondelete="CASCADE"))
	jdate: Mapped[str] = mapped_column(JDate)
	shift_id: Mapped[int | None] = mapped_column(ForeignKey("shift.id"))
	reason: Mapped[str] = mapped_column(Text)
