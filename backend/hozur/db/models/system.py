"""Files, settings, the audit trail, background jobs and report templates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
	BigInteger,
	Boolean,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
	false,
	func,
	text,
	true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.types import enum_check

AUDIT_ACTIONS = (
	"insert",
	"update",
	"delete",
	"submit",
	"cancel",
	"approve",
	"reject",
	"lock",
	"reopen",
	"refresh",
)
JOB_STATUSES = ("queued", "running", "done", "failed")


class StoredFile(IdMixin, Base):
	"""An uploaded file; the bytes live under HOZUR_DATA_DIR/files/<storage_path>."""

	__tablename__ = "stored_file"

	filename: Mapped[str] = mapped_column(String(255))
	content_type: Mapped[str | None] = mapped_column(String(150))
	size: Mapped[int] = mapped_column(BigInteger)
	sha256: Mapped[str] = mapped_column(String(64))
	storage_path: Mapped[str] = mapped_column(String(255), unique=True)
	is_private: Mapped[bool] = mapped_column(Boolean, server_default=true())
	created_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
	__tablename__ = "app_setting"

	key: Mapped[str] = mapped_column(String(100), primary_key=True)
	value: Mapped[Any] = mapped_column(JSONB)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)
	updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))


class AuditEntry(Base):
	"""Who changed what, when and why. Append-only (trigger)."""

	__tablename__ = "audit_entry"
	__table_args__ = (
		enum_check("action", AUDIT_ACTIONS),
		Index("ix_audit_entry_entity", "entity", "entity_id"),
	)

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	entity: Mapped[str] = mapped_column(String(60))  # table name
	entity_id: Mapped[str] = mapped_column(String(60))
	action: Mapped[str] = mapped_column(String(20))
	user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	reason: Mapped[str | None] = mapped_column(Text)
	changed_fields: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default=text("'{}'"))
	before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
	after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Job(IdMixin, Base):
	"""Background work, taken by the worker with FOR UPDATE SKIP LOCKED."""

	__tablename__ = "job"
	__table_args__ = (
		enum_check("status", JOB_STATUSES),
		Index("ix_job_queue", "run_after", postgresql_where=text("status = 'queued'")),
		# The same work (e.g. recalculate one person-day) is queued at most once.
		Index(
			"uq_job_dedup_key_queued", "dedup_key", unique=True, postgresql_where=text("status = 'queued'")
		),
	)

	kind: Mapped[str] = mapped_column(String(60))
	payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
	dedup_key: Mapped[str | None] = mapped_column(String(200))
	status: Mapped[str] = mapped_column(String(10), server_default="queued")
	run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	attempts: Mapped[int] = mapped_column(Integer, server_default="0")
	max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
	last_error: Mapped[str | None] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportTemplate(IdMixin, TimestampMixin, Base):
	__tablename__ = "report_template"
	__table_args__ = (
		enum_check("source", ("summary", "daily")),
		enum_check("time_unit", ("hours_minutes", "decimal_hours", "days")),
		enum_check("default_range", ("current_month", "previous_month", "today", "custom")),
		enum_check("export_format", ("excel", "csv", "text", "pdf")),
		enum_check("text_delimiter", ("comma", "tab", "pipe", "semicolon", "fixed_width")),
		enum_check("text_encoding", ("utf-8", "utf-8-sig", "windows-1256")),
		enum_check("group_by", ("employee", "department", "day")),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	source: Mapped[str] = mapped_column(String(20), server_default="summary")
	group_by: Mapped[str | None] = mapped_column(String(20))
	time_unit: Mapped[str] = mapped_column(String(20), server_default="hours_minutes")
	default_range: Mapped[str] = mapped_column(String(20), server_default="current_month")
	export_format: Mapped[str] = mapped_column(String(10), server_default="excel")
	text_delimiter: Mapped[str] = mapped_column(String(20), server_default="comma")
	text_encoding: Mapped[str] = mapped_column(String(20), server_default="utf-8")
	is_standard: Mapped[bool] = mapped_column(Boolean, server_default=false())
	description: Mapped[str | None] = mapped_column(Text)
	# [{"field": catalog key, "label": optional, "width": optional}], validated against the catalog
	columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
	shared_roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), server_default=text("'{}'"))
