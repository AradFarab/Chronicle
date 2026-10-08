"""Device ingestion: dedup, duplicate window, direction modes, sync, file import, mapping."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import pytest
from sqlalchemy import func, select

from hozur.db.models import AuditEntry, DeviceUserMap, Job, PunchImportTemplate, RawPunch
from hozur.devices import base
from hozur.services import devices
from hozur.services.errors import Conflict, ValidationError


@base.register
class FakeAdapter(base.DeviceAdapter):
	code = "test_fake"
	label = "Fake device"
	punches: ClassVar[list[base.DevicePunch]] = []
	users: ClassVar[list[base.DeviceUser]] = []
	fail: str | None = None
	since_seen: ClassVar[list] = []

	def _check(self):
		if FakeAdapter.fail:
			raise base.DeviceError(FakeAdapter.fail)

	def fetch_since(self, since):
		self._check()
		FakeAdapter.since_seen.append(since)
		return [p for p in FakeAdapter.punches if since is None or p.timestamp >= since]

	def list_users(self):
		self._check()
		return FakeAdapter.users

	def sync_time(self, now):
		self._check()

	def health(self):
		self._check()
		return base.DeviceHealth(ok=True, model="F1", serial_number="SN1", user_count=2, device_time=None)


@pytest.fixture
def fake(org):
	FakeAdapter.punches, FakeAdapter.users, FakeAdapter.fail, FakeAdapter.since_seen = [], [], None, []
	return devices.save_device(
		org.db, {"name": "Fake", "adapter_type": "test_fake", "host": "10.0.0.9"}, None
	)


def item(clock, user="77", jdate="1405/07/12", **kw):
	return {"device_user_id": user, "jdate": jdate, "time": clock, **kw}


def count(db, model=RawPunch):
	return db.scalar(select(func.count()).select_from(model))


def test_same_punch_is_stored_once_and_near_punches_are_flagged(org):
	stats = devices.ingest(org.db, org.device, [item("08:00:00"), item("08:00:10"), item("12:00")], "device")
	assert stats.as_dict() == {"created": 3, "existing": 0, "duplicates": 1}
	again = devices.ingest(org.db, org.device, [item("08:00"), item("8:00:10")], "file_import")
	assert again.as_dict() == {"created": 0, "existing": 2, "duplicates": 0}
	flags = org.db.scalars(select(RawPunch.is_duplicate).order_by(RawPunch.time)).all()
	assert flags == [False, True, False]


def test_new_punches_queue_a_recalculation_of_the_mapped_person(org):
	devices.ingest(org.db, org.device, [item("08:00"), item("09:00", user="999")], "device")
	job = org.db.scalar(select(Job).where(Job.kind == "recalculate"))
	assert job.payload["pairs"] == [[org.employee.id, "1405/07/11"], [org.employee.id, "1405/07/12"]]


def test_direction_mode_overrides_the_reported_direction(org):
	org.device.direction_mode = "always_in"
	devices.ingest(org.db, org.device, [item("08:00", reported_direction="out")], "device")
	p = org.db.scalar(select(RawPunch))
	assert (p.direction, p.reported_direction) == ("in", "out")


def test_bad_time_is_rejected(org):
	with pytest.raises(ValidationError):
		devices.ingest(org.db, org.device, [item("25:00")], "device")


def test_sync_stores_punches_health_and_watermark(org, fake):
	FakeAdapter.punches = [
		base.DevicePunch("77", datetime(2026, 10, 4, 8, 1), "in"),
		base.DevicePunch("77", datetime(2026, 10, 4, 16, 40), "out"),
	]
	result = devices.sync_device(org.db, fake)
	assert result.ok and result.stats["created"] == 2
	assert (fake.model, fake.serial_number, fake.last_sync_status) == ("F1", "SN1", "ok")
	assert fake.last_punch_timestamp == datetime(2026, 10, 4, 16, 40)
	p = org.db.scalar(select(RawPunch).where(RawPunch.device_id == fake.id).order_by(RawPunch.time))
	assert (p.jdate, str(p.time), p.device_timestamp) == (
		"1405/07/12",
		"08:01:00",
		datetime(2026, 10, 4, 8, 1),
	)
	devices.sync_device(org.db, fake)
	assert FakeAdapter.since_seen[-1] == datetime(2026, 10, 4, 16, 30)  # watermark minus the overlap


def test_sync_failure_is_recorded_not_raised(org, fake):
	FakeAdapter.fail = "Cannot connect to the device"
	result = devices.sync_device(org.db, fake)
	assert not result.ok
	assert fake.last_sync_status == "error" and fake.last_error


def test_operator_actions_raise_translatable_device_errors(org, fake):
	FakeAdapter.fail = "Device busy"
	with pytest.raises(devices.DeviceFailure):
		devices.test_connection(org.db, fake)


def test_reading_users_maps_matching_employee_codes(org, fake):
	FakeAdapter.users = [base.DeviceUser("T-OTHER", "دیگری"), base.DeviceUser("5", "ناشناس")]
	assert devices.read_device_users(org.db, fake, None) == {"users": 2, "created": 2, "auto_mapped": 1}
	assert devices.read_device_users(org.db, fake, None)["created"] == 0
	mapped = org.db.scalar(select(DeviceUserMap).where(DeviceUserMap.device_user_id == "T-OTHER"))
	assert mapped.employee_id == org.other.id


def test_comm_key_is_encrypted_and_kept_out_of_the_audit(org):
	d = devices.save_device(
		org.db, {"name": "D2", "adapter_type": "zkteco", "host": "10.0.0.2", "comm_key": "1234"}, None
	)
	assert d.comm_key_encrypted and "1234" not in d.comm_key_encrypted
	assert devices.adapter_for(d).config.comm_key == "1234"
	devices.save_device(org.db, {"polling_interval_minutes": 10}, None, d.id)
	assert devices.adapter_for(d).config.comm_key == "1234"  # empty keeps the stored key
	for entry in org.db.scalars(select(AuditEntry).where(AuditEntry.entity == "attendance_device")):
		assert "comm_key_encrypted" not in (entry.after or {})


def test_network_device_needs_a_host(org):
	with pytest.raises(ValidationError):
		devices.save_device(org.db, {"name": "NoHost", "adapter_type": "zkteco"}, None)


def test_csv_import_with_a_template(org, tmp_path, monkeypatch):
	monkeypatch.setenv("HOZUR_DATA_DIR", str(tmp_path))
	from hozur.config import get_settings

	get_settings.cache_clear()
	try:
		template = devices.save_template(
			org.db,
			{
				"name": "CSV test",
				"file_format": "csv",
				"has_header": True,
				"user_id_column": "code",
				"date_column": "date",
				"time_column": "time",
				"date_calendar": "jalali",
			},
			None,
		)
		content = b"code,date,time\n77,1405/07/12,08:00\n77,1405/07/12,16:30\n77,bad,09:00\n"
		record = devices.import_file(org.db, org.device, template, content, "p.csv", "text/csv", None)
		assert (record.status, record.created_count, record.error_count, record.total_rows) == (
			"imported",
			2,
			1,
			3,
		)
		assert (tmp_path / "files").is_dir()
		broken = devices.import_file(org.db, org.device, template, b"\x00\x01", "x.csv", None, None)
		assert broken.status in ("imported", "failed")
	finally:
		get_settings.cache_clear()


def test_unmapped_device_users_are_listed(org):
	devices.ingest(
		org.db, org.device, [item("08:00", user="501"), item("09:00", user="501"), item("08:00")], "device"
	)
	rows = devices.unmapped_device_users(org.db)
	assert [(r["device_user_id"], r["punches"]) for r in rows] == [("501", 2)]


def test_device_with_punches_cannot_be_deleted(org):
	devices.ingest(org.db, org.device, [item("08:00")], "device")
	with pytest.raises(Conflict):
		devices.delete_device(org.db, org.device, None)


def test_seeded_usb_template_exists(org):
	assert org.db.scalar(select(PunchImportTemplate.file_format)) == "zkteco_usb"
	assert count(org.db) == 0
