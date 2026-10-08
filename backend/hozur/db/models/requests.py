"""Requests ("forms") and their approval ("processes").

Every request kind shares one `request` row (class-table inheritance): one numbering, one
status machine, one approval chain, one inbox. Kind-specific columns live in a 1:1 detail
table; a correction's lines live in `correction_item`.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
	BigInteger,
	Boolean,
	CheckConstraint,
	Computed,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.models.calendar import jyear_of
from hozur.db.types import JDate, enum_check

LEAVE, MISSION, OVERTIME, CORRECTION = "leave", "mission", "overtime", "correction"
KINDS = (LEAVE, MISSION, OVERTIME, CORRECTION)
DAILY_LEAVE, HOURLY_LEAVE, MISSION_TYPE, OVERTIME_TYPE, CORRECTION_TYPE = (
	"daily_leave",
	"hourly_leave",
	"mission",
	"overtime",
	"attendance_correction",
)
REQUEST_TYPES = (DAILY_LEAVE, HOURLY_LEAVE, MISSION_TYPE, OVERTIME_TYPE, CORRECTION_TYPE)
# The default process for requests an operator enters for someone else.
OPERATOR_ENTRY = "operator_entry"
PENDING, APPROVED, REJECTED, CANCELLED, SKIPPED = "pending", "approved", "rejected", "cancelled", "skipped"
REQUEST_STATUSES = (PENDING, APPROVED, REJECTED, CANCELLED)
STEP_STATUSES = (PENDING, APPROVED, REJECTED, SKIPPED)
DIRECT_MANAGER, PARENT_DEPARTMENT_MANAGER, CEO, SPECIFIC_PERSON, EMPLOYEE_ACCEPTANCE = (
	"direct_manager",
	"parent_department_manager",
	"ceo",
	"specific_person",
	"employee_acceptance",
)
PROCESS_APPROVER_TYPES = (DIRECT_MANAGER, PARENT_DEPARTMENT_MANAGER, CEO, SPECIFIC_PERSON)
DAILY, HOURLY = "daily", "hourly"
OVERTIME_KINDS = ("normal", "exceptional", "emergency")
ADD_PUNCH, IGNORE_PUNCH = "add_punch", "ignore_punch"


class ApprovalProcess(IdMixin, TimestampMixin, Base):
	__tablename__ = "approval_process"

	name: Mapped[str] = mapped_column(String(150), unique=True)
	description: Mapped[str | None] = mapped_column(Text)
	is_standard: Mapped[bool] = mapped_column(Boolean, server_default=false())

	steps: Mapped[list[ApprovalProcessStep]] = relationship(
		cascade="all, delete-orphan", order_by="ApprovalProcessStep.position", lazy="selectin"
	)


class ApprovalProcessStep(IdMixin, Base):
	__tablename__ = "approval_process_step"
	__table_args__ = (
		enum_check("approver_type", PROCESS_APPROVER_TYPES),
		CheckConstraint(
			"(approver_type = 'specific_person') = (approver_id IS NOT NULL)", name="person_matches_type"
		),
		UniqueConstraint("process_id", "position"),
	)

	process_id: Mapped[int] = mapped_column(ForeignKey("approval_process.id", ondelete="CASCADE"))
	position: Mapped[int] = mapped_column(SmallInteger)
	approver_type: Mapped[str] = mapped_column(String(30))
	approver_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id"))


class ApprovalDefault(Base):
	"""The process used for a request type unless the employee has an override."""

	__tablename__ = "approval_default"
	__table_args__ = (enum_check("request_type", (*REQUEST_TYPES, OPERATOR_ENTRY)),)

	request_type: Mapped[str] = mapped_column(String(30), primary_key=True)
	process_id: Mapped[int] = mapped_column(ForeignKey("approval_process.id"))


class ApprovalOverride(IdMixin, TimestampMixin, Base):
	__tablename__ = "approval_override"
	__table_args__ = (
		enum_check("request_type", REQUEST_TYPES),
		UniqueConstraint("employee_id", "request_type"),
	)

	employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"))
	request_type: Mapped[str] = mapped_column(String(30))
	process_id: Mapped[int] = mapped_column(ForeignKey("approval_process.id"))


class Request(IdMixin, TimestampMixin, Base):
	__tablename__ = "request"
	__table_args__ = (
		enum_check("kind", KINDS),
		enum_check("request_type", REQUEST_TYPES),
		enum_check("status", REQUEST_STATUSES),
		CheckConstraint(
			"(kind = 'leave' AND request_type IN ('daily_leave', 'hourly_leave')) "
			"OR (kind = 'mission' AND request_type = 'mission') "
			"OR (kind = 'overtime' AND request_type = 'overtime') "
			"OR (kind = 'correction' AND request_type = 'attendance_correction')",
			name="type_matches_kind",
		),
		CheckConstraint("end_jdate >= start_jdate", name="date_range"),
		CheckConstraint(
			"(status = 'pending') OR pending_approver_user_id IS NULL", name="pending_only_when_pending"
		),
		Index("ix_request_employee_id_start_jdate", "employee_id", "start_jdate"),
		Index("ix_request_inbox", "pending_approver_user_id", postgresql_where=text("status = 'pending'")),
	)

	kind: Mapped[str] = mapped_column(String(20))
	request_type: Mapped[str] = mapped_column(String(30))
	employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employee.id"))
	status: Mapped[str] = mapped_column(String(20), server_default=PENDING)
	# The Jalali days the request covers (one day for hourly leave, overtime and corrections).
	start_jdate: Mapped[str] = mapped_column(JDate)
	end_jdate: Mapped[str] = mapped_column(JDate)
	jyear: Mapped[int] = mapped_column(SmallInteger, jyear_of("start_jdate"))
	reason: Mapped[str | None] = mapped_column(Text)
	approval_process_id: Mapped[int | None] = mapped_column(ForeignKey("approval_process.id"))
	entered_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	entered_by_operator: Mapped[bool] = mapped_column(Boolean, server_default=false())
	# Mirror of the current pending step, for a fast inbox.
	pending_approver_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id"))
	pending_approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
	decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	number: Mapped[str] = mapped_column(
		String(20),
		Computed(
			"CASE kind WHEN 'leave' THEN 'LV-' WHEN 'mission' THEN 'MS-' WHEN 'overtime' THEN 'OT-' "
			"ELSE 'COR-' END || lpad(id::text, 5, '0')",
			persisted=True,
		),
	)

	approvals: Mapped[list[RequestApproval]] = relationship(
		cascade="all, delete-orphan", order_by="RequestApproval.step", lazy="selectin"
	)
	leave: Mapped[LeaveRequest | None] = relationship(cascade="all, delete-orphan", lazy="selectin")
	mission: Mapped[MissionRequest | None] = relationship(cascade="all, delete-orphan", lazy="selectin")
	overtime: Mapped[OvertimeRequest | None] = relationship(cascade="all, delete-orphan", lazy="selectin")
	correction_items: Mapped[list[CorrectionItem]] = relationship(
		cascade="all, delete-orphan", order_by="CorrectionItem.position", lazy="selectin"
	)


class LeaveRequest(Base):
	__tablename__ = "leave_request"
	__table_args__ = (
		enum_check("unit", (DAILY, HOURLY)),
		CheckConstraint(
			"(unit = 'hourly') = (from_time IS NOT NULL AND to_time IS NOT NULL)", name="times_match_unit"
		),
		CheckConstraint("from_time IS NULL OR to_time > from_time", name="time_range"),
	)

	request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"), primary_key=True)
	leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_type.id"))
	unit: Mapped[str] = mapped_column(String(10))
	from_time: Mapped[time | None] = mapped_column(Time)
	to_time: Mapped[time | None] = mapped_column(Time)
	total_days: Mapped[Decimal] = mapped_column(Numeric(7, 4), server_default="0")  # working days covered
	total_minutes: Mapped[int] = mapped_column(Integer, server_default="0")  # hourly leave
	attachment_file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_file.id"))


class MissionRequest(Base):
	__tablename__ = "mission_request"
	__table_args__ = (
		enum_check("unit", (DAILY, HOURLY)),
		CheckConstraint(
			"(unit = 'hourly') = (from_time IS NOT NULL AND to_time IS NOT NULL)", name="times_match_unit"
		),
		CheckConstraint("from_time IS NULL OR to_time > from_time", name="time_range"),
	)

	request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"), primary_key=True)
	unit: Mapped[str] = mapped_column(String(10))
	destination: Mapped[str | None] = mapped_column(String(200))
	from_time: Mapped[time | None] = mapped_column(Time)
	to_time: Mapped[time | None] = mapped_column(Time)


class OvertimeRequest(Base):
	__tablename__ = "overtime_request"
	__table_args__ = (
		enum_check("overtime_kind", OVERTIME_KINDS),
		CheckConstraint("minutes > 0", name="minutes_positive"),
	)

	request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"), primary_key=True)
	overtime_kind: Mapped[str] = mapped_column(String(20), server_default="normal")
	minutes: Mapped[int] = mapped_column(Integer)
	from_time: Mapped[time | None] = mapped_column(Time)
	to_time: Mapped[time | None] = mapped_column(Time)
	# Assigned by a manager: the first approval step is the employee's acceptance (Article 59).
	assigned_by_manager: Mapped[bool] = mapped_column(Boolean, server_default=false())


class CorrectionItem(IdMixin, Base):
	"""A line of a manual entry: add a missed time, or ignore a wrong raw punch."""

	__tablename__ = "correction_item"
	__table_args__ = (
		enum_check("action", (ADD_PUNCH, IGNORE_PUNCH)),
		enum_check("direction", ("in", "out", "unknown")),
		CheckConstraint(
			"(action = 'add_punch' AND time IS NOT NULL AND raw_punch_id IS NULL) "
			"OR (action = 'ignore_punch' AND raw_punch_id IS NOT NULL)",
			name="action_fields",
		),
		UniqueConstraint("request_id", "position"),
	)

	request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"))
	position: Mapped[int] = mapped_column(SmallInteger)
	action: Mapped[str] = mapped_column(String(20))
	time: Mapped[time | None] = mapped_column(Time)
	direction: Mapped[str] = mapped_column(String(10), server_default="unknown")
	raw_punch_id: Mapped[int | None] = mapped_column(ForeignKey("raw_punch.id"))
	note: Mapped[str | None] = mapped_column(String(200))


class RequestApproval(IdMixin, Base):
	"""One step of a request's approval chain, copied from the process when submitted."""

	__tablename__ = "request_approval"
	__table_args__ = (
		enum_check("status", STEP_STATUSES),
		enum_check("approver_type", (*PROCESS_APPROVER_TYPES, EMPLOYEE_ACCEPTANCE)),
		UniqueConstraint("request_id", "step"),
	)

	request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"))
	step: Mapped[int] = mapped_column(SmallInteger)
	approver_type: Mapped[str] = mapped_column(String(30))
	approver_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id"))
	approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
	status: Mapped[str] = mapped_column(String(20), server_default=PENDING)
	acted_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
	acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	comment: Mapped[str | None] = mapped_column(Text)
