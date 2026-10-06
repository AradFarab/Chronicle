"""Frappe side of attendance devices: ingestion into Raw Punch, polling, operator actions.

Raw punches are append-only evidence (CLAUDE.md rule 4): the same punch is never stored
twice (dedup key = device + device user + Jalali day + time, so a USB export of a device
that is also polled over the network does not double anything), and punches of one person
closer than the duplicate window are stored but flagged is_duplicate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import frappe
from frappe import _

from hozur.devices import base
from hozur.jalali.dates import normalize_time, to_gregorian, to_jalali
from hozur.utils import now_jalali

SYNC_OVERLAP = timedelta(minutes=10)  # re-read a little before the last punch; dedup absorbs it
DIRECTION_MODES = {"Always In": base.IN, "Always Out": base.OUT, "Ignore (Pair by Order)": base.UNKNOWN}


def load_adapters() -> None:
	"""Import adapters contributed by other apps through the `hozur_device_adapters` hook."""
	for path in frappe.get_hooks("hozur_device_adapters") or []:
		frappe.get_module(path)


def adapter_for(device) -> base.DeviceAdapter:
	load_adapters()
	cls = base.get_adapter_class(device.adapter_type)
	config = base.DeviceConfig(
		host=(device.host or "").strip() or None,
		port=device.port,
		comm_key=device.get_password("comm_key", raise_exception=False) if device.comm_key else None,
		timeout=device.timeout_seconds or 10,
		use_udp=bool(device.use_udp),
	)
	return cls(config)


def _dedup_key(device: str, user: str, jdate: str, time: str) -> str:
	return hashlib.sha1(f"{device}|{user}|{jdate} {time}".encode()).hexdigest()


def _moment(jdate: str, time: str) -> datetime:
	h, m, s = (int(x) for x in time.split(":"))
	return datetime.combine(to_gregorian(jdate), datetime.min.time()).replace(hour=h, minute=m, second=s)


def _previous_punch(device: str, user: str, jdate: str, time: str) -> tuple[str, str] | None:
	row = frappe.db.sql(
		"""select jdate, time from `tabRaw Punch`
		where device=%s and device_user_id=%s and (jdate < %s or (jdate = %s and time < %s))
		order by jdate desc, time desc limit 1""",
		(device, user, jdate, jdate, time),
	)
	return (row[0][0], row[0][1]) if row else None


def ingest(device, items: list[dict], source: str, punch_import: str | None = None) -> dict:
	"""Store punches for a device. Each item: device_user_id, jdate, time, and optionally
	device_timestamp, reported_direction, verify_type, raw. Returns counts."""
	window = frappe.db.get_single_value("Hozur Settings", "dedup_window_seconds")
	window = 30 if window is None else int(window)
	stats = {"created": 0, "existing": 0, "duplicates": 0}
	for item in items:
		time = normalize_time(item["time"])
		if not time:
			raise base.DeviceError(f"Invalid punch time {item['time']!r}")
		item["time"] = time
	items = sorted(items, key=lambda i: (i["device_user_id"], i["jdate"], i["time"]))
	keys = {_dedup_key(device.name, i["device_user_id"], i["jdate"], i["time"]): i for i in items}
	existing = set()
	key_list = list(keys)
	for start in range(0, len(key_list), 500):
		existing.update(
			frappe.get_all(
				"Raw Punch", filters={"dedup_key": ["in", key_list[start : start + 500]]}, pluck="dedup_key"
			)
		)
	last_by_user: dict[str, tuple[str, str] | None] = {}
	new_days: set[tuple[str, str]] = set()
	for key, item in keys.items():
		user = item["device_user_id"]
		if key in existing:
			stats["existing"] += 1
			last_by_user[user] = (item["jdate"], item["time"])
			continue
		if user not in last_by_user:
			last_by_user[user] = _previous_punch(device.name, user, item["jdate"], item["time"])
		previous = last_by_user[user]
		is_duplicate = bool(
			previous
			and window > 0
			and (_moment(item["jdate"], item["time"]) - _moment(*previous)).total_seconds() < window
		)
		reported = item.get("reported_direction") or base.UNKNOWN
		direction = DIRECTION_MODES.get(device.direction_mode, reported)
		year, month = int(item["jdate"][:4]), int(item["jdate"][5:7])
		doc = frappe.get_doc(
			{
				"doctype": "Raw Punch",
				"device": device.name,
				"device_user_id": user,
				"jdate": item["jdate"],
				"time": item["time"],
				"jyear": year,
				"jmonth": month,
				"direction": direction,
				"reported_direction": reported,
				"verify_type": item.get("verify_type"),
				"device_timestamp": item.get("device_timestamp"),
				"source": source,
				"punch_import": punch_import,
				"is_duplicate": int(is_duplicate),
				"dedup_key": key,
				"raw_data": json.dumps(item.get("raw") or {}, ensure_ascii=False, default=str),
			}
		)
		doc.insert(ignore_permissions=True)
		stats["created"] += 1
		stats["duplicates"] += int(is_duplicate)
		last_by_user[user] = (item["jdate"], item["time"])
		new_days.add((user, item["jdate"]))
	if new_days:
		from hozur.attendance import on_punches

		on_punches(device.name, sorted(new_days))
	return stats


def _punch_items(punches: list[base.DevicePunch]) -> list[dict]:
	items = []
	for p in punches:
		jdate, time = to_jalali(p.timestamp)
		items.append(
			{
				"device_user_id": p.device_user_id,
				"jdate": jdate,
				"time": time,
				"device_timestamp": p.timestamp,
				"reported_direction": p.direction,
				"verify_type": p.verify_type,
				"raw": p.raw,
			}
		)
	return items


def _now_label() -> str:
	jdate, time = now_jalali()
	return f"{jdate} {time}"


def _record_health(device, health: base.DeviceHealth) -> None:
	drift = None
	if health.device_time:
		drift = int((health.device_time - frappe.utils.now_datetime()).total_seconds())
	device.db_set(
		{
			"model": health.model,
			"serial_number": health.serial_number,
			"firmware": health.firmware,
			"user_count": health.user_count or 0,
			"record_count": health.record_count or 0,
			"record_capacity": health.record_capacity or 0,
			"clock_drift_seconds": drift or 0,
			"last_health_check": _now_label(),
		},
		update_modified=False,
	)


def sync_device(device_name: str, since: datetime | None = None, use_watermark: bool = True) -> dict:
	"""Read new punches from a network device and store them. Safe to run repeatedly."""
	device = frappe.get_doc("Attendance Device", device_name)
	adapter = adapter_for(device)
	if not adapter.network:
		frappe.throw(_("Device {0} receives punches by file import").format(device.name))
	if since is None and use_watermark and device.last_punch_timestamp:
		since = frappe.utils.get_datetime(device.last_punch_timestamp) - SYNC_OVERLAP
	try:
		_record_health(device, adapter.health())
		punches = adapter.fetch_since(since)
		stats = ingest(device, _punch_items(punches), source="Device")
	except base.DeviceError as e:
		device.db_set(
			{"last_sync": _now_label(), "last_sync_status": "Error", "last_error": str(e)},
			update_modified=False,
		)
		frappe.db.commit()
		raise
	latest = max((p.timestamp for p in punches), default=None)
	values = {
		"last_sync": _now_label(),
		"last_sync_status": "OK",
		"last_error": None,
		"punches_last_sync": stats["created"],
	}
	if latest and (
		not device.last_punch_timestamp or latest > frappe.utils.get_datetime(device.last_punch_timestamp)
	):
		values["last_punch_timestamp"] = latest
	device.db_set(values, update_modified=False)
	return stats


def _poll_key(name: str) -> str:
	return f"hozur:device-last-poll:{name}"


def poll_devices() -> None:
	"""Scheduler (every minute): enqueue a sync for each enabled network device that is due."""
	load_adapters()
	now = frappe.utils.now_datetime().timestamp()
	for d in frappe.get_all(
		"Attendance Device",
		filters={"enabled": 1},
		fields=["name", "adapter_type", "polling_interval_minutes"],
	):
		cls = base.REGISTRY.get(d.adapter_type)
		if not cls or not cls.network:
			continue
		last = frappe.cache.get_value(_poll_key(d.name))
		if last and now - float(last) < max(1, d.polling_interval_minutes or 5) * 60:
			continue
		frappe.cache.set_value(_poll_key(d.name), now)
		frappe.enqueue(
			"hozur.devices.service.sync_device_job",
			queue="long",
			job_id=f"hozur-device-sync::{d.name}",
			deduplicate=True,
			device_name=d.name,
		)


def sync_device_job(device_name: str) -> None:
	try:
		sync_device(device_name)
	except base.DeviceError:
		pass  # already recorded on the device (last_sync_status / last_error)


# Operator actions (buttons on the Attendance Device form and the PWA)


def _device(name: str):
	frappe.only_for(["System Manager", "Hozur Operator"])
	device = frappe.get_doc("Attendance Device", name)
	device.check_permission("write")
	return device


def _run(fn):
	try:
		return fn()
	except base.DeviceError as e:
		frappe.throw(str(e), title=_("Device Error"))


@frappe.whitelist()
def test_connection(device: str) -> dict:
	"""Model, serial number, users, log records and clock drift."""
	doc = _device(device)
	health = _run(lambda: adapter_for(doc).health())
	_record_health(doc, health)
	doc.reload()
	return {
		"model": health.model,
		"serial_number": health.serial_number,
		"firmware": health.firmware,
		"user_count": health.user_count,
		"record_count": health.record_count,
		"record_capacity": health.record_capacity,
		"device_time": to_jalali(health.device_time) if health.device_time else None,
		"clock_drift_seconds": doc.clock_drift_seconds,
	}


@frappe.whitelist()
def read_device_users(device: str) -> dict:
	"""Create Device User Map rows for device users; map automatically when the device user
	id equals an employee code."""
	doc = _device(device)
	users = _run(lambda: adapter_for(doc).list_users())
	created = auto_mapped = 0
	for u in users:
		existing = frappe.db.get_value(
			"Device User Map",
			{"device": doc.name, "device_user_id": u.device_user_id},
			["name", "employee"],
			as_dict=True,
		)
		if existing:
			frappe.db.set_value(
				"Device User Map",
				existing.name,
				{"device_user_name": u.name, "card": u.card},
				update_modified=False,
			)
			continue
		employee = frappe.db.get_value("Employee", {"employee_code": u.device_user_id}, "name")
		frappe.get_doc(
			{
				"doctype": "Device User Map",
				"device": doc.name,
				"device_user_id": u.device_user_id,
				"device_user_name": u.name,
				"card": u.card,
				"employee": employee,
			}
		).insert()
		created += 1
		auto_mapped += bool(employee)
	return {"users": len(users), "created": created, "auto_mapped": auto_mapped}


@frappe.whitelist()
def sync_now(device: str) -> dict:
	doc = _device(device)
	return _run(lambda: sync_device(doc.name))


@frappe.whitelist()
def resync_from(device: str, jdate: str) -> dict:
	"""Read the device again from a Jalali day (punches already stored are skipped)."""
	from hozur.jalali.dates import normalize_jdate

	doc = _device(device)
	since = datetime.combine(to_gregorian(normalize_jdate(jdate)), datetime.min.time())
	return _run(lambda: sync_device(doc.name, since=since, use_watermark=False))


@frappe.whitelist()
def set_device_clock(device: str) -> dict:
	"""Set the device clock to the server time (Asia/Tehran)."""
	doc = _device(device)
	now = frappe.utils.now_datetime()
	_run(lambda: adapter_for(doc).sync_time(now))
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Attendance Device",
			"reference_name": doc.name,
			"content": _("Device clock set to {0} {1}").format(*to_jalali(now)),
		}
	).insert(ignore_permissions=True)
	return {"set_to": to_jalali(now)}


@frappe.whitelist()
def unmapped_device_users() -> list[dict]:
	"""Device users that have punches but no employee mapping (the 'unknown punches' queue)."""
	frappe.only_for(["System Manager", "Hozur Operator"])
	return frappe.db.sql(
		"""select p.device, p.device_user_id, count(*) as punches, min(p.jdate) as first_day, max(p.jdate) as last_day
		from `tabRaw Punch` p
		left join `tabDevice User Map` m
			on m.device = p.device and m.device_user_id = p.device_user_id and ifnull(m.employee, '') != ''
		where m.name is null
		group by p.device, p.device_user_id
		order by punches desc""",
		as_dict=True,
	)


def employee_punches(employee: str, start: str, end: str) -> list[dict]:
	"""Raw punches of an employee between two Jalali days (inclusive), through Device User Map
	with its validity dates. Ordered by day and time."""
	maps = frappe.get_all(
		"Device User Map",
		filters={"employee": employee},
		fields=["device", "device_user_id", "valid_from", "valid_to"],
	)
	punches = []
	for m in maps:
		lo = max(start, m.valid_from) if m.valid_from else start
		hi = min(end, m.valid_to) if m.valid_to else end
		if lo > hi:
			continue
		punches += frappe.get_all(
			"Raw Punch",
			filters={"device": m.device, "device_user_id": m.device_user_id, "jdate": ["between", [lo, hi]]},
			fields=["name", "device", "jdate", "time", "direction", "is_duplicate", "verify_type", "source"],
		)
	punches.sort(key=lambda p: (p.jdate, p.time))
	return punches
