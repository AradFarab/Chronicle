"""Attendance devices: ingestion into raw_punch, polling, file imports, operator actions.

Raw punches are append-only evidence (CLAUDE.md rule 4): the same punch is never stored
twice (dedup key = device + device user + Jalali day + time, so a USB export of a device
that is also polled over the network doubles nothing), and punches of one person closer
than the duplicate window are stored but flagged is_duplicate. The app never clears a
device's logs (rule 5).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session

from hozur.clock import now
from hozur.db.models import (
	AttendanceDevice,
	DeviceUserMap,
	Employee,
	PunchImport,
	PunchImportTemplate,
	RawPunch,
)
from hozur.db.models.devices import IN, OUT, SOURCE_DEVICE, SOURCE_FILE, UNKNOWN
from hozur.devices import base, file_import
from hozur.i18n import DEFAULT_LANGUAGE, _, translate
from hozur.jalali.dates import add_days, normalize_jdate, normalize_time, to_gregorian, to_jalali
from hozur.secrets import decrypt, encrypt
from hozur.services import audit, files, jobs, settings
from hozur.services.errors import Conflict, NotFound, ValidationError
from hozur.services.resources import flush

SYNC_OVERLAP = timedelta(minutes=10)  # re-read a little before the last punch; dedup absorbs it
FORCED_DIRECTION = {"always_in": IN, "always_out": OUT, "pair_by_order": UNKNOWN}

DEVICE_FIELDS = (
	"name",
	"adapter_type",
	"work_location_id",
	"enabled",
	"direction_mode",
	"host",
	"port",
	"polling_interval_minutes",
	"timeout_seconds",
	"use_udp",
)
TEMPLATE_FIELDS = (
	"name",
	"file_format",
	"delimiter",
	"encoding",
	"has_header",
	"skip_rows",
	"user_id_column",
	"datetime_column",
	"date_column",
	"time_column",
	"date_calendar",
	"date_format",
	"direction_column",
	"in_values",
	"out_values",
	"description",
)


class DeviceFailure(ValidationError):
	"""A device could not be reached or answered wrongly; the message is for the operator."""

	status_code = 502

	@classmethod
	def wrap(cls, error: base.DeviceError) -> DeviceFailure:
		return cls(error.template, *error.params)


# configuration ----------------------------------------------------------------------------


def get_device(session: Session, device_id: int) -> AttendanceDevice:
	device = session.get(AttendanceDevice, device_id)
	if device is None:
		raise NotFound(_("Device not found"))
	return device


def _operator_text(error: base.DeviceError) -> str:
	"""Stored messages (last_error, error_log) are in the company language."""
	return error.translated(lambda text: translate(text, DEFAULT_LANGUAGE))


def adapter_for(device: AttendanceDevice) -> base.DeviceAdapter:
	try:
		cls = base.get_adapter_class(device.adapter_type)
	except base.DeviceError as e:
		raise DeviceFailure.wrap(e) from None
	return cls(
		base.DeviceConfig(
			host=(device.host or "").strip() or None,
			port=device.port,
			comm_key=decrypt(device.comm_key_encrypted),
			timeout=device.timeout_seconds or 10,
			use_udp=bool(device.use_udp),
		)
	)


def adapter_types() -> list[dict[str, Any]]:
	return [{"code": c.code, "label": c.label, "network": c.network} for c in base.REGISTRY.values()]


def save_device(
	session: Session, values: dict[str, Any], user_id: int | None, device_id: int | None = None
) -> AttendanceDevice:
	"""Create or change a device. `comm_key` is write-only: empty keeps the stored one,
	`clear_comm_key` removes it."""
	device = get_device(session, device_id) if device_id else AttendanceDevice()
	before = audit.snapshot(device) if device_id else None
	clean = {k: values[k] for k in DEVICE_FIELDS if k in values}
	if not device_id and not (clean.get("name") or "").strip():
		raise ValidationError(_("Enter a name"))
	if "name" in clean:
		clean["name"] = clean["name"].strip()
	adapter = clean.get("adapter_type", device.adapter_type)
	if adapter not in base.REGISTRY:
		raise ValidationError(_("No adapter registered for device type {0}"), adapter)
	if base.REGISTRY[adapter].network and not (clean.get("host", device.host) or "").strip():
		raise ValidationError(_("Enter the device IP address"))
	for key, value in clean.items():
		setattr(device, key, value)
	if values.get("comm_key"):
		device.comm_key_encrypted = encrypt(str(values["comm_key"]))
	elif values.get("clear_comm_key"):
		device.comm_key_encrypted = None
	if not device_id:
		session.add(device)
	flush(session)
	after = audit.snapshot(device)
	for snap in (before, after):
		if snap:
			snap.pop("comm_key_encrypted", None)  # never in the audit trail
	audit.log(
		session,
		"attendance_device",
		device.id,
		"update" if device_id else "insert",
		user_id,
		None,
		before,
		after,
	)
	return device


# ingestion ------------------------------------------------------------------------------------


def dedup_key(device_id: int, user: str, jdate: str, clock: str) -> str:
	return hashlib.sha256(f"{device_id}|{user}|{jdate} {clock}".encode()).hexdigest()


def _moment(jdate: str, clock: str | time) -> datetime:
	t = clock if isinstance(clock, time) else time.fromisoformat(clock)
	return datetime.combine(to_gregorian(jdate), t)


def _previous_punch(
	session: Session, device_id: int, user: str, jdate: str, clock: str
) -> tuple[str, time] | None:
	row = session.execute(
		select(RawPunch.jdate, RawPunch.time)
		.where(
			RawPunch.device_id == device_id,
			RawPunch.device_user_id == user,
			tuple_(RawPunch.jdate, RawPunch.time) < tuple_(jdate, time.fromisoformat(clock)),
		)
		.order_by(RawPunch.jdate.desc(), RawPunch.time.desc())
		.limit(1)
	).first()
	return (row[0], row[1]) if row else None


@dataclass
class IngestStats:
	created: int = 0
	existing: int = 0
	duplicates: int = 0
	days: set[tuple[str, str]] = field(default_factory=set)  # (device user id, jdate) with new punches

	def as_dict(self) -> dict[str, int]:
		return {"created": self.created, "existing": self.existing, "duplicates": self.duplicates}


def ingest(
	session: Session,
	device: AttendanceDevice,
	items: list[dict[str, Any]],
	source: str,
	punch_import_id: int | None = None,
) -> IngestStats:
	"""Store punches for a device. Each item: device_user_id, jdate, time, and optionally
	device_timestamp, reported_direction, verify_type, raw."""
	window = int(settings.get(session, "dedup_window_seconds") or 0)
	stats = IngestStats()
	clean = []
	for item in items:
		clock = normalize_time(item["time"])
		if not clock:
			raise ValidationError(_("Invalid punch time {0}"), item["time"])
		clean.append({**item, "jdate": normalize_jdate(item["jdate"]), "time": clock})
	clean.sort(key=lambda i: (i["device_user_id"], i["jdate"], i["time"]))
	keyed = {dedup_key(device.id, i["device_user_id"], i["jdate"], i["time"]): i for i in clean}
	existing: set[str] = set()
	keys = list(keyed)
	for start in range(0, len(keys), 1000):
		existing.update(
			session.scalars(
				select(RawPunch.dedup_key).where(RawPunch.dedup_key.in_(keys[start : start + 1000]))
			)
		)
	last_by_user: dict[str, tuple[str, str | time] | None] = {}
	forced = FORCED_DIRECTION.get(device.direction_mode)
	for key, item in keyed.items():
		user = item["device_user_id"]
		if key in existing:
			stats.existing += 1
			last_by_user[user] = (item["jdate"], item["time"])
			continue
		if user not in last_by_user:
			last_by_user[user] = _previous_punch(session, device.id, user, item["jdate"], item["time"])
		previous = last_by_user[user]
		is_duplicate = bool(
			previous
			and window > 0
			and (_moment(item["jdate"], item["time"]) - _moment(*previous)).total_seconds() < window
		)
		reported = item.get("reported_direction") or UNKNOWN
		session.add(
			RawPunch(
				device_id=device.id,
				device_user_id=user,
				jdate=item["jdate"],
				time=time.fromisoformat(item["time"]),
				direction=forced or reported,
				reported_direction=reported,
				is_duplicate=is_duplicate,
				source=source,
				punch_import_id=punch_import_id,
				verify_type=item.get("verify_type"),
				device_timestamp=item.get("device_timestamp"),
				dedup_key=key,
				raw_data=_jsonable(item.get("raw")),
			)
		)
		stats.created += 1
		stats.duplicates += int(is_duplicate)
		last_by_user[user] = (item["jdate"], item["time"])
		stats.days.add((user, item["jdate"]))
	session.flush()
	if stats.days:
		_recalculate_after_punches(session, device, stats.days)
	return stats


def _jsonable(value: Any) -> Any:
	if isinstance(value, dict):
		return {str(k): _jsonable(v) for k, v in value.items()}
	if isinstance(value, list | tuple):
		return [_jsonable(v) for v in value]
	if value is None or isinstance(value, str | int | float | bool):
		return value
	return str(value)


def _recalculate_after_punches(
	session: Session, device: AttendanceDevice, days: set[tuple[str, str]]
) -> None:
	"""Recalculate the mapped employees' days (and the day before, for overnight shifts)."""
	users = {u for u, _d in days}
	maps = session.scalars(
		select(DeviceUserMap).where(
			DeviceUserMap.device_id == device.id,
			DeviceUserMap.device_user_id.in_(users),
			DeviceUserMap.employee_id.is_not(None),
		)
	).all()
	pairs: set[tuple[int, str]] = set()
	for user, jdate in days:
		for m in maps:
			if m.device_user_id != user:
				continue
			if (not m.valid_from or m.valid_from <= jdate) and (not m.valid_to or jdate <= m.valid_to):
				pairs |= {(m.employee_id, jdate), (m.employee_id, add_days(jdate, -1))}
	if pairs:
		jobs.enqueue(
			session,
			jobs.RECALCULATE,
			{"pairs": sorted([e, d] for e, d in pairs), "reason": f"punches from {device.name}"},
		)


def punch_items(punches: list[base.DevicePunch]) -> list[dict[str, Any]]:
	items = []
	for p in punches:
		jdate, clock = to_jalali(p.timestamp)
		items.append(
			{
				"device_user_id": p.device_user_id,
				"jdate": jdate,
				"time": clock,
				"device_timestamp": p.timestamp,
				"reported_direction": p.direction,
				"verify_type": p.verify_type,
				"raw": p.raw,
			}
		)
	return items


# talking to devices ---------------------------------------------------------------------------


def _record_health(device: AttendanceDevice, health: base.DeviceHealth) -> None:
	device.model = health.model
	device.serial_number = health.serial_number
	device.firmware = health.firmware
	device.user_count = health.user_count
	device.record_count = health.record_count
	device.record_capacity = health.record_capacity
	device.last_health_check_at = now()
	device.clock_drift_seconds = (
		int((health.device_time - now().replace(tzinfo=None)).total_seconds()) if health.device_time else None
	)


@dataclass
class SyncResult:
	ok: bool
	stats: dict[str, int] = field(default_factory=dict)
	error: base.DeviceError | None = None


def sync_device(
	session: Session, device: AttendanceDevice, since: datetime | None = None, use_watermark: bool = True
) -> SyncResult:
	"""Read new punches from a network device and store them. Safe to run repeatedly. A
	device error is recorded on the device and returned, not raised, so the status persists."""
	adapter = adapter_for(device)
	if not adapter.network:
		raise ValidationError(_("Device {0} receives punches by file import"), device.name)
	if since is None and use_watermark and device.last_punch_timestamp:
		since = device.last_punch_timestamp - SYNC_OVERLAP
	device.last_sync_at = now()
	try:
		_record_health(device, adapter.health())
		punches = adapter.fetch_since(since)
	except base.DeviceError as e:
		device.last_sync_status, device.last_error = "error", _operator_text(e)
		return SyncResult(False, error=e)
	stats = ingest(session, device, punch_items(punches), SOURCE_DEVICE)
	device.last_sync_status, device.last_error = "ok", None
	device.punches_last_sync = stats.created
	latest = max((p.timestamp for p in punches), default=None)
	if latest and (not device.last_punch_timestamp or latest > device.last_punch_timestamp):
		device.last_punch_timestamp = latest
	return SyncResult(True, stats.as_dict())


def due_devices(session: Session) -> list[AttendanceDevice]:
	"""Enabled network devices whose polling interval has passed."""
	moment = now()
	out = []
	for device in session.scalars(
		select(AttendanceDevice).where(AttendanceDevice.enabled).order_by(AttendanceDevice.id)
	):
		cls = base.REGISTRY.get(device.adapter_type)
		if not cls or not cls.network:
			continue
		if device.last_sync_at and moment - device.last_sync_at < timedelta(
			minutes=device.polling_interval_minutes
		):
			continue
		out.append(device)
	return out


def _call(fn):
	try:
		return fn()
	except base.DeviceError as e:
		raise DeviceFailure.wrap(e) from None


def test_connection(session: Session, device: AttendanceDevice) -> dict[str, Any]:
	"""Model, serial number, users, log records and clock drift."""
	health = _call(lambda: adapter_for(device).health())
	_record_health(device, health)
	return {
		"model": health.model,
		"serial_number": health.serial_number,
		"firmware": health.firmware,
		"user_count": health.user_count,
		"record_count": health.record_count,
		"record_capacity": health.record_capacity,
		"device_time": list(to_jalali(health.device_time)) if health.device_time else None,
		"clock_drift_seconds": device.clock_drift_seconds,
	}


def read_device_users(session: Session, device: AttendanceDevice, user_id: int | None) -> dict[str, int]:
	"""Create device_user_map rows for device users; map automatically when the device user
	id equals an employee code."""
	device_users = _call(lambda: adapter_for(device).list_users())
	created = auto_mapped = 0
	for u in device_users:
		rows = session.scalars(
			select(DeviceUserMap).where(
				DeviceUserMap.device_id == device.id, DeviceUserMap.device_user_id == u.device_user_id
			)
		).all()
		if rows:
			for row in rows:
				row.device_user_name, row.card = u.name or row.device_user_name, u.card or row.card
			continue
		employee_id = session.scalar(select(Employee.id).where(Employee.code == u.device_user_id))
		session.add(
			DeviceUserMap(
				device_id=device.id,
				device_user_id=u.device_user_id,
				device_user_name=u.name or None,
				card=u.card,
				employee_id=employee_id,
			)
		)
		created += 1
		auto_mapped += bool(employee_id)
	session.flush()
	if created:
		audit.log(
			session,
			"attendance_device",
			device.id,
			"update",
			user_id,
			None,
			after={"users": len(device_users), "created": created, "auto_mapped": auto_mapped},
		)
	return {"users": len(device_users), "created": created, "auto_mapped": auto_mapped}


def resync_from(session: Session, device: AttendanceDevice, jdate: str) -> SyncResult:
	"""Read the device again from a Jalali day (punches already stored are skipped)."""
	since = datetime.combine(to_gregorian(normalize_jdate(jdate)), time())
	return sync_device(session, device, since=since, use_watermark=False)


def set_device_clock(session: Session, device: AttendanceDevice, user_id: int | None) -> list[str]:
	"""Set the device clock to the server time (only on an explicit operator action)."""
	moment = now().replace(tzinfo=None)
	_call(lambda: adapter_for(device).sync_time(moment))
	audit.log(
		session,
		"attendance_device",
		device.id,
		"update",
		user_id,
		None,
		after={"device_clock_set_to": moment.isoformat()},
	)
	return list(to_jalali(moment))


# device users ------------------------------------------------------------------------------


def save_mapping(
	session: Session, values: dict[str, Any], user_id: int | None, map_id: int | None = None
) -> DeviceUserMap:
	"""Link a device user id to an employee for a validity range."""
	row = session.get(DeviceUserMap, map_id) if map_id else DeviceUserMap()
	if row is None:
		raise NotFound(_("Not found"))
	before = audit.snapshot(row) if map_id else None
	for key in ("device_id", "device_user_id", "device_user_name", "card", "employee_id"):
		if key in values:
			setattr(row, key, values[key] or None if key != "device_user_id" else str(values[key]).strip())
	for key in ("valid_from", "valid_to"):
		if key in values:
			setattr(row, key, normalize_jdate(values[key]) if values[key] else None)
	if not row.device_id or not row.device_user_id:
		raise ValidationError(_("Choose the device and enter the device user id"))
	if row.valid_from and row.valid_to and row.valid_to < row.valid_from:
		raise ValidationError(_("The end date is before the start date"))
	if not map_id:
		session.add(row)
	flush(session)
	audit.log(
		session,
		"device_user_map",
		row.id,
		"update" if map_id else "insert",
		user_id,
		values.get("reason"),
		before,
		audit.snapshot(row),
	)
	# the person's punches through this mapping may now belong to someone else
	if row.employee_id or (before and before.get("employee_id")):
		_recalculate_mapping(session, row, before)
	return row


def _recalculate_mapping(session: Session, row: DeviceUserMap, before: dict | None) -> None:
	bounds = session.execute(
		select(func.min(RawPunch.jdate), func.max(RawPunch.jdate)).where(
			RawPunch.device_id == row.device_id, RawPunch.device_user_id == row.device_user_id
		)
	).first()
	if not bounds or not bounds[0]:
		return
	start = max(filter(None, (bounds[0], row.valid_from))) if row.valid_from else bounds[0]
	end = min(filter(None, (bounds[1], row.valid_to))) if row.valid_to else bounds[1]
	people = {row.employee_id, (before or {}).get("employee_id")} - {None}
	jobs.enqueue(
		session,
		jobs.RECALCULATE,
		{"range": [start, end], "employee_ids": sorted(people), "reason": "device user mapping changed"},
	)


def unmapped_device_users(session: Session) -> list[dict[str, Any]]:
	"""Device users that have punches but no employee mapping (the 'unknown punches' queue)."""
	mapped = (
		select(DeviceUserMap.id)
		.where(
			DeviceUserMap.device_id == RawPunch.device_id,
			DeviceUserMap.device_user_id == RawPunch.device_user_id,
			DeviceUserMap.employee_id.is_not(None),
			and_(
				(DeviceUserMap.valid_from.is_(None)) | (DeviceUserMap.valid_from <= RawPunch.jdate),
				(DeviceUserMap.valid_to.is_(None)) | (DeviceUserMap.valid_to >= RawPunch.jdate),
			),
		)
		.exists()
	)
	rows = session.execute(
		select(
			RawPunch.device_id,
			AttendanceDevice.name,
			RawPunch.device_user_id,
			func.count(),
			func.min(RawPunch.jdate),
			func.max(RawPunch.jdate),
		)
		.join(AttendanceDevice, AttendanceDevice.id == RawPunch.device_id)
		.where(~mapped)
		.group_by(RawPunch.device_id, AttendanceDevice.name, RawPunch.device_user_id)
		.order_by(func.count().desc())
	)
	return [
		{"device_id": d, "device": n, "device_user_id": u, "punches": c, "first_day": lo, "last_day": hi}
		for d, n, u, c, lo, hi in rows
	]


# file imports -----------------------------------------------------------------------------


def save_template(
	session: Session, values: dict[str, Any], user_id: int | None, template_id: int | None = None
) -> PunchImportTemplate:
	row = session.get(PunchImportTemplate, template_id) if template_id else PunchImportTemplate()
	if row is None:
		raise NotFound(_("Not found"))
	before = audit.snapshot(row) if template_id else None
	for key in TEMPLATE_FIELDS:
		if key in values:
			setattr(row, key, values[key])
	if not (row.name or "").strip():
		raise ValidationError(_("Enter a name"))
	if not template_id:
		session.add(row)
	flush(session)
	audit.log(
		session,
		"punch_import_template",
		row.id,
		"update" if template_id else "insert",
		user_id,
		None,
		before,
		audit.snapshot(row),
	)
	return row


def _template_dict(t: PunchImportTemplate) -> dict[str, Any]:
	return {k: getattr(t, k) for k in TEMPLATE_FIELDS}


def import_file(
	session: Session,
	device: AttendanceDevice,
	template: PunchImportTemplate,
	content: bytes,
	filename: str,
	content_type: str | None,
	user_id: int | None,
) -> PunchImport:
	"""Store the file, parse it with the template and ingest its punches. A file whose rows
	cannot be read at all is recorded as failed (and kept, as evidence); bad rows are listed
	and skipped."""
	stored = files.save(session, content, filename, content_type, user_id)
	record = PunchImport(
		device_id=device.id, template_id=template.id, file_id=stored.id, created_by_id=user_id
	)
	session.add(record)
	session.flush()
	try:
		rows = file_import.read_table(content, template.file_format, template.delimiter, template.encoding)
		parsed = file_import.parse_rows(rows, _template_dict(template))
	except base.DeviceError as e:
		record.status, record.error_log = "failed", _operator_text(e)
		return record
	except Exception as e:  # a corrupt or wrong-format file
		record.status = "failed"
		record.error_log = translate(_("The file could not be read: {0}"), DEFAULT_LANGUAGE).format(e)
		return record
	items = [
		{
			"device_user_id": p.device_user_id,
			"jdate": p.jdate,
			"time": p.time,
			"device_timestamp": p.device_timestamp,
			"reported_direction": p.direction,
			"raw": p.raw,
		}
		for p in parsed.punches
	]
	stats = ingest(session, device, items, SOURCE_FILE, record.id)
	record.status = "imported"
	record.imported_at = now()
	record.total_rows = len(parsed.punches) + len(parsed.errors)
	record.created_count = stats.created
	record.existing_count = stats.existing
	record.duplicate_count = stats.duplicates
	record.error_count = len(parsed.errors)
	record.error_log = "\n".join(parsed.errors) or None
	audit.log(
		session,
		"punch_import",
		record.id,
		"insert",
		user_id,
		None,
		after={"file": stored.filename, **stats.as_dict(), "errors": len(parsed.errors)},
	)
	return record


def delete_device(session: Session, device: AttendanceDevice, user_id: int | None) -> None:
	"""Only a device without punches can be deleted; otherwise disable it."""
	if session.scalar(select(RawPunch.id).where(RawPunch.device_id == device.id).limit(1)):
		raise Conflict(_("This device has punches; disable it instead of deleting it"))
	audit.log(session, "attendance_device", device.id, "delete", user_id, None, before=audit.snapshot(device))
	session.delete(device)
