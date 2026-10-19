"""SMS: the provider accounts, the events that send messages, the templates (how an event is
sent through a provider), every message with its raw request and answer, opt-outs and short links.

The core never talks to a panel: it dispatches an event (services/sms_dispatch.py) and a
driver (chronicle/sms/) does the rest. Every message has a row, also one that was never sent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
	Boolean,
	CheckConstraint,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	Numeric,
	String,
	Text,
	UniqueConstraint,
	false,
	func,
	text,
	true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chronicle.db.base import Base, IdMixin, TimestampMixin
from chronicle.db.types import enum_check

TRANSACTIONAL, PROMOTIONAL = "transactional", "promotional"
CATEGORIES = (TRANSACTIONAL, PROMOTIONAL)
BULK, PATTERN = "bulk", "pattern"
MODES = (BULK, PATTERN)
QUEUED, SENDING, SENT, DELIVERED, FAILED, SKIPPED, UNKNOWN = (
	"queued",
	"sending",
	"sent",
	"delivered",
	"failed",
	"skipped",
	"unknown",
)
MESSAGE_STATUSES = (QUEUED, SENDING, SENT, DELIVERED, FAILED, SKIPPED, UNKNOWN)


class SmsProviderConfig(IdMixin, TimestampMixin, Base):
	"""One panel account. Secret fields of `config` are stored encrypted (``enc:v1:...``). At most
	one active panel is the primary and one the fallback, and none is both (checked here)."""

	__tablename__ = "sms_provider_config"
	__table_args__ = (
		CheckConstraint("NOT (is_primary AND is_fallback)", name="not_both_roles"),
		Index(
			"uq_sms_provider_config_one_primary",
			"is_primary",
			unique=True,
			postgresql_where=text("is_primary AND is_active"),
		),
		Index(
			"uq_sms_provider_config_one_fallback",
			"is_fallback",
			unique=True,
			postgresql_where=text("is_fallback AND is_active"),
		),
	)

	provider_code: Mapped[str] = mapped_column(String(30), unique=True)
	config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
	is_primary: Mapped[bool] = mapped_column(Boolean, server_default=false())
	is_fallback: Mapped[bool] = mapped_column(Boolean, server_default=false())
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class SmsEvent(IdMixin, Base):
	"""Something in the system that sends a message. The list is in code (chronicle/sms/events.py)
	and synced here on install; the system admin cannot add events, only templates for them."""

	__tablename__ = "sms_event"
	__table_args__ = (enum_check("category", CATEGORIES),)

	code: Mapped[str] = mapped_column(String(50), unique=True)
	label: Mapped[str] = mapped_column(String(150))
	variables: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default=text("'{}'"))
	category: Mapped[str] = mapped_column(String(20), server_default=TRANSACTIONAL)
	# Not held until the send window opens (a one-time code is useless by morning).
	bypasses_send_window: Mapped[bool] = mapped_column(Boolean, server_default=false())
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class SmsTemplate(IdMixin, TimestampMixin, Base):
	"""How one event is sent through one panel: a full text (`bulk`) or a panel pattern
	(`pattern`) with `param_map` saying which event variable fills which pattern variable."""

	__tablename__ = "sms_template"
	__table_args__ = (
		enum_check("mode", MODES),
		CheckConstraint(
			"(mode = 'bulk' AND body IS NOT NULL) OR (mode = 'pattern' AND pattern_code IS NOT NULL)",
			name="mode_fields",
		),
		Index(
			"uq_sms_template_one_active",
			"event_id",
			"provider_code",
			unique=True,
			postgresql_where=text("is_active"),
		),
	)

	event_id: Mapped[int] = mapped_column(ForeignKey("sms_event.id"), index=True)
	provider_code: Mapped[str] = mapped_column(String(30))
	mode: Mapped[str] = mapped_column(String(10))
	body: Mapped[str | None] = mapped_column(Text)
	pattern_code: Mapped[str | None] = mapped_column(String(100))
	line_number: Mapped[str | None] = mapped_column(String(30))
	# named panels: {"LINK": "link_path"}; positional panels: ["name", "date"]
	param_map: Mapped[Any | None] = mapped_column(JSONB)
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class SmsMessage(IdMixin, Base):
	__tablename__ = "sms_message"
	__table_args__ = (
		enum_check("status", MESSAGE_STATUSES),
		CheckConstraint("attempts >= 0", name="attempts_non_negative"),
		Index("ix_sms_message_status_send_after", "status", "send_after"),
		Index("ix_sms_message_to_number", "to_number"),
		# one message per event and entity (a leave decision, a birthday): the database says so
		Index(
			"uq_sms_message_once",
			"event_id",
			"entity_key",
			unique=True,
			postgresql_where=text("entity_key IS NOT NULL"),
		),
	)

	to_number: Mapped[str] = mapped_column(String(20))
	event_id: Mapped[int] = mapped_column(ForeignKey("sms_event.id"))
	provider_code: Mapped[str | None] = mapped_column(String(30))  # the panel that took it
	status: Mapped[str] = mapped_column(String(10), server_default=QUEUED)
	provider_message_id: Mapped[str | None] = mapped_column(String(100))
	attempts: Mapped[int] = mapped_column(Integer, server_default="0")
	context: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
	raw_request: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # secrets masked
	raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
	error: Mapped[str | None] = mapped_column(Text)
	cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
	entity_key: Mapped[str | None] = mapped_column(String(120))
	queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SmsOptOut(IdMixin, Base):
	"""A number that does not want a category of messages. Keyed by number, not person: the
	receiver may not be a person in the system."""

	__tablename__ = "sms_opt_out"
	__table_args__ = (enum_check("category", CATEGORIES), UniqueConstraint("mobile", "category"))

	mobile: Mapped[str] = mapped_column(String(20))
	category: Mapped[str] = mapped_column(String(20))
	reason: Mapped[str | None] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShortLink(IdMixin, Base):
	"""A short path for the SMS (``/l/<code>``): a pattern parameter is short, and the panel only
	accepts a fixed domain in the approved text. Only the path is kept, never a domain, so the
	link can never redirect off the site."""

	__tablename__ = "short_link"

	code: Mapped[str] = mapped_column(String(16), unique=True)
	target_path: Mapped[str] = mapped_column(String(500))
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
