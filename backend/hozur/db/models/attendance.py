"""Engine output (one row per person and Jalali day) and monthly period locks."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
	BigInteger,
	Boolean,
	CheckConstraint,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	Numeric,
	SmallInteger,
	String,
	Text,
	Time,
	UniqueConstraint,
	false,
	text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hozur.db.base import Base, IdMixin
from hozur.db.models.calendar import jmonth_of, jyear_of
from hozur.db.types import JDate, enum_check

# hozur.engine.model statuses
DAY_STATUSES = ("present", "absent", "incomplete", "leave", "mission", "holiday", "rest_day", "not_scheduled")
DAY_TYPES = ("workday", "friday", "official_holiday", "company_holiday")
OPEN, CLOSED = "open", "closed"


def _minutes() -> Mapped[int]:
	return mapped_column(Integer, server_default="0")


class DailyAttendance(IdMixin, Base):
	"""Always rebuilt from punches, approved requests and the rule set; never edited by hand."""

	__tablename__ = "daily_attendance"
	__table_args__ = (
		enum_check("status", DAY_STATUSES),
		enum_check("day_type", DAY_TYPES),
		UniqueConstraint("employee_id", "jdate"),
		Index("ix_daily_attendance_jdate", "jdate"),
		Index("ix_daily_attendance_department_id_jdate", "department_id", "jdate"),
	)

	employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employee.id"))
	jdate: Mapped[str] = mapped_column(JDate)
	jyear: Mapped[int] = mapped_column(SmallInteger, jyear_of("jdate"))
	jmonth: Mapped[int] = mapped_column(SmallInteger, jmonth_of("jdate"))
	weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Saturday
	status: Mapped[str] = mapped_column(String(20))
	day_type: Mapped[str] = mapped_column(String(20))
	holiday_title: Mapped[str | None] = mapped_column(Text)
	# what the calculation used (a snapshot: later org changes do not rewrite history)
	department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
	branch_id: Mapped[int | None] = mapped_column(ForeignKey("branch.id"))
	designation_id: Mapped[int | None] = mapped_column(ForeignKey("designation.id"))
	work_pattern_id: Mapped[int | None] = mapped_column(ForeignKey("work_pattern.id"))
	shift_id: Mapped[int | None] = mapped_column(ForeignKey("shift.id"))
	rest_day: Mapped[bool] = mapped_column(Boolean, server_default=false())
	rule_set_id: Mapped[int | None] = mapped_column(ForeignKey("labor_rule_set.id"))
	first_in: Mapped[time | None] = mapped_column(Time)
	last_out: Mapped[time | None] = mapped_column(Time)
	punch_count: Mapped[int] = _minutes()
	required_minutes: Mapped[int] = _minutes()
	worked_minutes: Mapped[int] = _minutes()
	credited_minutes: Mapped[int] = _minutes()
	late_minutes: Mapped[int] = _minutes()
	early_leave_minutes: Mapped[int] = _minutes()
	absence_minutes: Mapped[int] = _minutes()
	absent_day: Mapped[bool] = mapped_column(Boolean, server_default=false())
	leave_minutes: Mapped[int] = _minutes()
	leave_days: Mapped[Decimal] = mapped_column(Numeric(7, 4), server_default="0")
	mission_minutes: Mapped[int] = _minutes()
	nursing_minutes: Mapped[int] = _minutes()
	extra_minutes: Mapped[int] = _minutes()
	overtime_normal_minutes: Mapped[int] = _minutes()
	overtime_exceptional_minutes: Mapped[int] = _minutes()
	overtime_emergency_minutes: Mapped[int] = _minutes()
	unapproved_extra_minutes: Mapped[int] = _minutes()
	night_work_minutes: Mapped[int] = _minutes()
	rest_day_work_minutes: Mapped[int] = _minutes()
	friday_premium_minutes: Mapped[int] = _minutes()
	holiday_work_minutes: Mapped[int] = _minutes()
	company_holiday_work_minutes: Mapped[int] = _minutes()
	warnings: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default=text("'{}'"))
	calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

	leaves: Mapped[list[DailyAttendanceLeave]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class DailyAttendanceLeave(Base):
	__tablename__ = "daily_attendance_leave"

	attendance_id: Mapped[int] = mapped_column(
		ForeignKey("daily_attendance.id", ondelete="CASCADE"), primary_key=True
	)
	leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_type.id"), primary_key=True)
	minutes: Mapped[int] = mapped_column(Integer, server_default="0")
	days: Mapped[Decimal] = mapped_column(Numeric(7, 4), server_default="0")


class AttendancePeriod(IdMixin, Base):
	"""A Jalali month; once closed nothing inside it changes until reopened (rule 9)."""

	__tablename__ = "attendance_period"
	__table_args__ = (
		enum_check("status", (OPEN, CLOSED)),
		CheckConstraint("jmonth BETWEEN 1 AND 12", name="jmonth_range"),
		CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name="closed_has_time"),
		UniqueConstraint("jyear", "jmonth"),
	)

	jyear: Mapped[int] = mapped_column(SmallInteger)
	jmonth: Mapped[int] = mapped_column(SmallInteger)
	status: Mapped[str] = mapped_column(String(10), server_default=OPEN)
	closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	note: Mapped[str | None] = mapped_column(Text)

	@property
	def label(self) -> str:
		return f"{self.jyear}/{self.jmonth:02d}"
