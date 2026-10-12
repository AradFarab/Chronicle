"""Holidays and the yearly calendar refresh. Weekdays come from jdatetime, not a table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
	BigInteger,
	Boolean,
	CheckConstraint,
	Computed,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	SmallInteger,
	String,
	Text,
	false,
	text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronicle.db.base import Base, IdMixin, TimestampMixin
from chronicle.db.types import JDate, enum_check

OFFICIAL_SOLAR, OFFICIAL_LUNAR, OFFICIAL_OCCASIONAL, OFFICE_CLOSURE, COMPANY_INTERNAL = (
	"official_solar",
	"official_lunar",
	"official_occasional",
	"office_closure",
	"company_internal",
)
HOLIDAY_TYPES = (OFFICIAL_SOLAR, OFFICIAL_LUNAR, OFFICIAL_OCCASIONAL, OFFICE_CLOSURE, COMPANY_INTERNAL)
CONFIRMED, PREDICTED = "confirmed", "predicted"
HOLIDAY_STATUSES = (CONFIRMED, PREDICTED)
COUNTRY, PROVINCE, WORK_LOCATION, COMPANY = "country", "province", "work_location", "company"
HOLIDAY_SCOPES = (COUNTRY, PROVINCE, WORK_LOCATION, COMPANY)
BUNDLED, TIME_IR, FILE, MANUAL = "bundled", "time_ir", "file", "manual"
HOLIDAY_SOURCES = (BUNDLED, TIME_IR, FILE, MANUAL)
# How an office closure is paid (only for office_closure).
CLOSURE_PAY_MODES = ("paid_holiday", "employer_paid", "workday")


def jyear_of(column: str) -> Computed:
	return Computed(f"(substr({column}, 1, 4))::smallint", persisted=True)


def jmonth_of(column: str) -> Computed:
	return Computed(f"(substr({column}, 6, 2))::smallint", persisted=True)


class Holiday(IdMixin, TimestampMixin, Base):
	__tablename__ = "holiday"
	__table_args__ = (
		enum_check("holiday_type", HOLIDAY_TYPES),
		enum_check("status", HOLIDAY_STATUSES),
		enum_check("scope", HOLIDAY_SCOPES),
		enum_check("source", HOLIDAY_SOURCES),
		CheckConstraint("(scope = 'province') = (province_id IS NOT NULL)", name="province_scope"),
		CheckConstraint(
			"(scope = 'work_location') = (work_location_id IS NOT NULL)", name="work_location_scope"
		),
		CheckConstraint(
			"closure_pay_mode IS NULL OR (holiday_type = 'office_closure' AND closure_pay_mode IN "
			"('paid_holiday', 'employer_paid', 'workday'))",
			name="closure_pay_mode_valid",
		),
		Index("ix_holiday_jdate", "jdate"),
		Index("ix_holiday_jyear", "jyear"),
		# One title per day and scope.
		Index(
			"uq_holiday_day_title_scope",
			"jdate",
			"title",
			"scope",
			text("coalesce(province_id, 0)"),
			text("coalesce(work_location_id, 0)"),
			unique=True,
		),
	)

	jdate: Mapped[str] = mapped_column(JDate)
	jyear: Mapped[int] = mapped_column(SmallInteger, jyear_of("jdate"))
	jmonth: Mapped[int] = mapped_column(SmallInteger, jmonth_of("jdate"))
	title: Mapped[str] = mapped_column(String(200))
	holiday_type: Mapped[str] = mapped_column(String(30))
	status: Mapped[str] = mapped_column(String(20), server_default=CONFIRMED)
	scope: Mapped[str] = mapped_column(String(20), server_default=COUNTRY)
	province_id: Mapped[int | None] = mapped_column(ForeignKey("province.id"))
	work_location_id: Mapped[int | None] = mapped_column(ForeignKey("work_location.id"))
	closure_pay_mode: Mapped[str | None] = mapped_column(String(20))
	source: Mapped[str] = mapped_column(String(20), server_default=MANUAL)
	# Stable key from the source (seed key, time.ir event) so a refresh can match rows.
	source_key: Mapped[str | None] = mapped_column(String(100))
	note: Mapped[str | None] = mapped_column(Text)
	change_reason: Mapped[str | None] = mapped_column(Text)
	# The operator changed a row that came from a source; a refresh will not overwrite it.
	edited_by_admin: Mapped[bool] = mapped_column(Boolean, server_default=false())


class CalendarYear(Base):
	"""Where the holidays of a Jalali year came from and when they were last refreshed."""

	__tablename__ = "calendar_year"
	__table_args__ = (
		enum_check("status", HOLIDAY_STATUSES),
		enum_check("source", HOLIDAY_SOURCES),
		CheckConstraint("jyear BETWEEN 1300 AND 1499", name="jyear_range"),
	)

	jyear: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
	status: Mapped[str] = mapped_column(String(20), server_default=PREDICTED)
	source: Mapped[str] = mapped_column(String(20), server_default=BUNDLED)
	refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	refreshed_by_id: Mapped[int | None] = mapped_column(
		BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
	)
	holiday_count: Mapped[int] = mapped_column(Integer, server_default="0")
	note: Mapped[str | None] = mapped_column(Text)
