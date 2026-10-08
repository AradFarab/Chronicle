"""Devices, device users, raw punches (append-only) and punch-file imports."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import (
	BigInteger,
	Boolean,
	CheckConstraint,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	SmallInteger,
	String,
	Text,
	Time,
	UniqueConstraint,
	false,
	func,
	true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.models.calendar import jmonth_of, jyear_of
from hozur.db.types import JDate, enum_check

IN, OUT, UNKNOWN = "in", "out", "unknown"
DIRECTIONS = (IN, OUT, UNKNOWN)
DIRECTION_MODES = ("from_device", "always_in", "always_out", "pair_by_order")
SOURCE_DEVICE, SOURCE_FILE = "device", "file_import"


class AttendanceDevice(IdMixin, TimestampMixin, Base):
	"""A configured device (CLAUDE.md rule 5): everything here is edited in the PWA."""

	__tablename__ = "attendance_device"
	__table_args__ = (
		enum_check("direction_mode", DIRECTION_MODES),
		CheckConstraint("last_sync_status IN ('ok', 'error')", name="last_sync_status_valid"),
		CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
		CheckConstraint("polling_interval_minutes >= 1 AND timeout_seconds >= 1", name="intervals_positive"),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	adapter_type: Mapped[str] = mapped_column(String(50))  # a code registered in hozur.devices
	branch_id: Mapped[int | None] = mapped_column(ForeignKey("branch.id"))
	enabled: Mapped[bool] = mapped_column(Boolean, server_default=true())
	direction_mode: Mapped[str] = mapped_column(String(20), server_default="from_device")
	host: Mapped[str | None] = mapped_column(String(255))
	port: Mapped[int] = mapped_column(Integer, server_default="4370")
	comm_key_encrypted: Mapped[str | None] = mapped_column(Text)  # Fernet, key derived from the app secret
	polling_interval_minutes: Mapped[int] = mapped_column(Integer, server_default="5")
	timeout_seconds: Mapped[int] = mapped_column(Integer, server_default="10")
	use_udp: Mapped[bool] = mapped_column(Boolean, server_default=false())
	# status, written by the app
	last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_sync_status: Mapped[str | None] = mapped_column(String(10))
	punches_last_sync: Mapped[int] = mapped_column(Integer, server_default="0")
	last_punch_timestamp: Mapped[datetime | None] = mapped_column(DateTime)  # device clock, naive
	last_error: Mapped[str | None] = mapped_column(Text)
	model: Mapped[str | None] = mapped_column(String(100))
	serial_number: Mapped[str | None] = mapped_column(String(100))
	firmware: Mapped[str | None] = mapped_column(String(100))
	last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	user_count: Mapped[int | None] = mapped_column(Integer)
	record_count: Mapped[int | None] = mapped_column(Integer)
	record_capacity: Mapped[int | None] = mapped_column(Integer)
	clock_drift_seconds: Mapped[int | None] = mapped_column(Integer)


class DeviceUserMap(IdMixin, TimestampMixin, Base):
	"""Device user id → employee, with Jalali validity (ids get reused)."""

	__tablename__ = "device_user_map"
	__table_args__ = (
		UniqueConstraint("device_id", "device_user_id", "valid_from", postgresql_nulls_not_distinct=True),
		CheckConstraint(
			"valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="valid_range"
		),
		Index("ix_device_user_map_employee_id", "employee_id"),
	)

	device_id: Mapped[int] = mapped_column(ForeignKey("attendance_device.id", ondelete="CASCADE"))
	device_user_id: Mapped[str] = mapped_column(String(50))
	device_user_name: Mapped[str | None] = mapped_column(String(150))
	card: Mapped[str | None] = mapped_column(String(50))
	employee_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id", ondelete="SET NULL"))
	valid_from: Mapped[str | None] = mapped_column(JDate)
	valid_to: Mapped[str | None] = mapped_column(JDate)


class RawPunch(Base):
	"""A punch exactly as received. Append-only: a trigger rejects UPDATE and DELETE."""

	__tablename__ = "raw_punch"
	__table_args__ = (
		enum_check("direction", DIRECTIONS),
		enum_check("reported_direction", DIRECTIONS),
		enum_check("source", (SOURCE_DEVICE, SOURCE_FILE)),
		Index("ix_raw_punch_device_user_day", "device_id", "device_user_id", "jdate"),
		Index("ix_raw_punch_jdate", "jdate"),
	)

	id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
	device_id: Mapped[int] = mapped_column(ForeignKey("attendance_device.id"))
	device_user_id: Mapped[str] = mapped_column(String(50))
	jdate: Mapped[str] = mapped_column(JDate)
	jyear: Mapped[int] = mapped_column(SmallInteger, jyear_of("jdate"))
	jmonth: Mapped[int] = mapped_column(SmallInteger, jmonth_of("jdate"))
	time: Mapped[time] = mapped_column(Time)
	direction: Mapped[str] = mapped_column(String(10))  # after the device's direction mode
	reported_direction: Mapped[str] = mapped_column(String(10))  # what the device said
	is_duplicate: Mapped[bool] = mapped_column(Boolean, server_default=false())
	source: Mapped[str] = mapped_column(String(20))
	punch_import_id: Mapped[int | None] = mapped_column(ForeignKey("punch_import.id"))
	verify_type: Mapped[str | None] = mapped_column(String(30))
	device_timestamp: Mapped[datetime | None] = mapped_column(DateTime)  # raw device clock, evidence
	dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
	raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PunchImportTemplate(IdMixin, TimestampMixin, Base):
	"""How to read a USB export, Excel or CSV file from a device or another program."""

	__tablename__ = "punch_import_template"
	__table_args__ = (
		enum_check("file_format", ("csv", "excel", "zkteco_usb")),
		enum_check("delimiter", ("comma", "tab", "semicolon", "pipe")),
		enum_check("encoding", ("utf-8", "windows-1256")),
		enum_check("date_calendar", ("jalali", "gregorian")),
		enum_check("date_format", ("YYYY/MM/DD", "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY")),
		CheckConstraint("skip_rows >= 0", name="skip_rows_non_negative"),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	file_format: Mapped[str] = mapped_column(String(20), server_default="excel")
	delimiter: Mapped[str] = mapped_column(String(20), server_default="comma")
	encoding: Mapped[str] = mapped_column(String(20), server_default="utf-8")
	has_header: Mapped[bool] = mapped_column(Boolean, server_default=true())
	skip_rows: Mapped[int] = mapped_column(Integer, server_default="0")
	user_id_column: Mapped[str | None] = mapped_column(String(100))
	datetime_column: Mapped[str | None] = mapped_column(String(100))
	date_column: Mapped[str | None] = mapped_column(String(100))
	time_column: Mapped[str | None] = mapped_column(String(100))
	date_calendar: Mapped[str] = mapped_column(String(20), server_default="jalali")
	date_format: Mapped[str] = mapped_column(String(20), server_default="YYYY/MM/DD")
	direction_column: Mapped[str | None] = mapped_column(String(100))
	in_values: Mapped[str | None] = mapped_column(String(200))
	out_values: Mapped[str | None] = mapped_column(String(200))
	description: Mapped[str | None] = mapped_column(Text)


class PunchImport(IdMixin, Base):
	__tablename__ = "punch_import"
	__table_args__ = (enum_check("status", ("pending", "imported", "failed")),)

	device_id: Mapped[int] = mapped_column(ForeignKey("attendance_device.id"))
	template_id: Mapped[int] = mapped_column(ForeignKey("punch_import_template.id"))
	file_id: Mapped[int] = mapped_column(ForeignKey("stored_file.id"))
	status: Mapped[str] = mapped_column(String(20), server_default="pending")
	imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	total_rows: Mapped[int] = mapped_column(Integer, server_default="0")
	created_count: Mapped[int] = mapped_column(Integer, server_default="0")
	existing_count: Mapped[int] = mapped_column(Integer, server_default="0")
	duplicate_count: Mapped[int] = mapped_column(Integer, server_default="0")
	error_count: Mapped[int] = mapped_column(Integer, server_default="0")
	error_log: Mapped[str | None] = mapped_column(Text)
	created_by_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
