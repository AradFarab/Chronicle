"""Payslips (فیش حقوقی): the pages of the finance software's PDF, one per employee and Jalali
month, and the private links sent to the employees by SMS.

The app never computes pay: a payslip is a PDF page that is stored and handed to its owner."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
	Boolean,
	CheckConstraint,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	SmallInteger,
	String,
	Text,
	UniqueConstraint,
	false,
	func,
	text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronicle.db.base import Base, IdMixin, TimestampMixin
from chronicle.db.types import enum_check

# The national id printed on the page compared with the employee's: match / mismatch / unknown
# (the page shows none). A mismatch blocks the link: nobody's slip may reach somebody else.
MATCH, MISMATCH, UNKNOWN = "match", "mismatch", "unknown"
NATIONAL_STATUSES = (MATCH, MISMATCH, UNKNOWN)
PENDING, SENT, FAILED = "pending", "sent", "failed"
SMS_STATUSES = (PENDING, SENT, FAILED)
VOIDED, TOO_MANY_ATTEMPTS = "voided", "failed_attempts"
LOCK_REASONS = (VOIDED, TOO_MANY_ATTEMPTS)


class Payslip(IdMixin, TimestampMixin, Base):
	__tablename__ = "payslip"
	__table_args__ = (
		enum_check("national_status", NATIONAL_STATUSES),
		CheckConstraint("jyear BETWEEN 1300 AND 1499", name="jyear_valid"),
		CheckConstraint("jmonth BETWEEN 1 AND 12", name="jmonth_valid"),
		UniqueConstraint("employee_id", "jyear", "jmonth"),
		Index("ix_payslip_jyear_jmonth", "jyear", "jmonth"),
	)

	employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"))
	jyear: Mapped[int] = mapped_column(SmallInteger)
	jmonth: Mapped[int] = mapped_column(SmallInteger)
	file_id: Mapped[int] = mapped_column(ForeignKey("stored_file.id"))  # the single-page PDF
	source_name: Mapped[str | None] = mapped_column(String(255))  # the uploaded file it came from
	source_page: Mapped[int | None] = mapped_column(Integer)
	national_status: Mapped[str] = mapped_column(String(10), server_default=UNKNOWN)
	uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))


class PayslipRejection(IdMixin, Base):
	"""A page of an uploaded PDF that could not become a payslip, with the reason. The page itself
	is not kept: the system admin fixes the file and uploads it again."""

	__tablename__ = "payslip_rejection"
	__table_args__ = (
		CheckConstraint("jmonth BETWEEN 1 AND 12", name="jmonth_valid"),
		Index("ix_payslip_rejection_jyear_jmonth", "jyear", "jmonth"),
	)

	jyear: Mapped[int] = mapped_column(SmallInteger)
	jmonth: Mapped[int] = mapped_column(SmallInteger)
	source_name: Mapped[str] = mapped_column(String(255))
	page_no: Mapped[int | None] = mapped_column(Integer)
	reason: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayslipLink(IdMixin, Base):
	"""The private link to one payslip. Only the SHA-256 of the token is kept for lookup; the
	token itself waits, encrypted, until the SMS has gone out and is then erased. At most one
	link per payslip is active (not locked): sending again voids the previous one."""

	__tablename__ = "payslip_link"
	__table_args__ = (
		enum_check("sms_status", SMS_STATUSES),
		CheckConstraint(
			"lock_reason IS NULL OR lock_reason IN ('voided', 'failed_attempts')", name="lock_reason_valid"
		),
		CheckConstraint("locked = (lock_reason IS NOT NULL)", name="lock_matches_reason"),
		CheckConstraint("view_count >= 0 AND failed_attempts >= 0", name="counters_non_negative"),
		Index("uq_payslip_link_one_active", "payslip_id", unique=True, postgresql_where=text("NOT locked")),
		Index("ix_payslip_link_sms_status", "sms_status", postgresql_where=text("sms_status = 'pending'")),
	)

	payslip_id: Mapped[int] = mapped_column(ForeignKey("payslip.id", ondelete="CASCADE"), index=True)
	token_hash: Mapped[str] = mapped_column(String(64), unique=True)
	token_encrypted: Mapped[str | None] = mapped_column(Text)
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	max_views: Mapped[int] = mapped_column(Integer)
	view_count: Mapped[int] = mapped_column(Integer, server_default="0")
	failed_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
	locked: Mapped[bool] = mapped_column(Boolean, server_default=false())
	lock_reason: Mapped[str | None] = mapped_column(String(20))
	sms_status: Mapped[str] = mapped_column(String(10), server_default=PENDING)
	sms_provider_id: Mapped[str | None] = mapped_column(String(100))
	sms_error: Mapped[str | None] = mapped_column(Text)
	sms_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	created_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayslipView(IdMixin, Base):
	"""One successful opening of a link."""

	__tablename__ = "payslip_view"

	link_id: Mapped[int] = mapped_column(ForeignKey("payslip_link.id", ondelete="CASCADE"), index=True)
	viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	ip: Mapped[str | None] = mapped_column(String(64))
