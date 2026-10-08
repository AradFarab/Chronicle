"""Leave types and the leave ledger. A balance is always the sum of ledger rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
	BigInteger,
	Boolean,
	DateTime,
	ForeignKey,
	Index,
	Numeric,
	SmallInteger,
	String,
	Text,
	false,
	func,
)
from sqlalchemy.orm import Mapped, mapped_column

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.models.calendar import jyear_of
from hozur.db.types import JDate, enum_check

LEAVE_CATEGORIES = (
	"earned",
	"sick",
	"unpaid",
	"marriage_bereavement",
	"hajj",
	"maternity",
	"paternity",
	"other",
)
ENTRY_TYPES = ("allocation", "usage", "reversal", "carry_over", "expiry", "adjustment")


class LeaveType(IdMixin, TimestampMixin, Base):
	__tablename__ = "leave_type"
	__table_args__ = (enum_check("category", LEAVE_CATEGORIES),)

	name: Mapped[str] = mapped_column(String(100), unique=True)
	category: Mapped[str] = mapped_column(String(30))
	is_paid: Mapped[bool] = mapped_column(Boolean, server_default=false())
	deducts_from_balance: Mapped[bool] = mapped_column(Boolean, server_default=false())
	allow_hourly: Mapped[bool] = mapped_column(Boolean, server_default=false())
	# Rule-set parameter that limits this leave (e.g. hajj_leave_days); limits are law, not code.
	rule_limit: Mapped[str | None] = mapped_column(String(60))
	max_days_per_request: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
	once_in_service: Mapped[bool] = mapped_column(Boolean, server_default=false())
	is_standard: Mapped[bool] = mapped_column(Boolean, server_default=false())
	description: Mapped[str | None] = mapped_column(Text)


class LeaveLedgerEntry(Base):
	"""Append-only (trigger). Usage is negative, allocation positive; a cancelled request
	adds a reversal instead of deleting its usage."""

	__tablename__ = "leave_ledger_entry"
	__table_args__ = (
		enum_check("entry_type", ENTRY_TYPES),
		Index("ix_leave_ledger_entry_balance", "employee_id", "leave_type_id", "jdate"),
	)

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"))
	leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_type.id"))
	entry_type: Mapped[str] = mapped_column(String(20))
	jdate: Mapped[str] = mapped_column(JDate)
	jyear: Mapped[int] = mapped_column(SmallInteger, jyear_of("jdate"))
	days: Mapped[Decimal] = mapped_column(Numeric(9, 4))
	request_id: Mapped[int | None] = mapped_column(ForeignKey("request.id"))
	note: Mapped[str | None] = mapped_column(Text)
	created_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
