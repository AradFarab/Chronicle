# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from hozur.devices import service
from hozur.devices.base import IN, OUT, UNKNOWN, DeviceAdapter, DeviceHealth, DevicePunch, DeviceUser

PUNCHES = [
	DevicePunch("101", datetime(2026, 10, 6, 7, 58, 11), IN, "Face"),
	DevicePunch("101", datetime(2026, 10, 6, 7, 58, 25), IN, "Face"),  # 14 s later: duplicate
	DevicePunch("101", datetime(2026, 10, 6, 16, 31, 2), OUT, "Face"),
	DevicePunch("999", datetime(2026, 10, 6, 9, 0, 0), UNKNOWN, "Card"),
]


class FakeAdapter(DeviceAdapter):
	code, network = "ZKTeco", True
	punches = PUNCHES

	def fetch_since(self, since):
		return [p for p in self.punches if since is None or p.timestamp >= since]

	def list_users(self):
		return [
			DeviceUser("101", "Arad"),
			DeviceUser("102", "Sara"),
			DeviceUser("T-DEV-EMP", "Mapped by code"),
		]

	def sync_time(self, now):
		pass

	def health(self):
		return DeviceHealth(
			ok=True,
			model="VF600",
			serial_number="SN1",
			user_count=3,
			record_count=4,
			device_time=frappe.utils.now_datetime(),
		)


def make_device(name="T-Device", **kw):
	if frappe.db.exists("Attendance Device", name):
		return frappe.get_doc("Attendance Device", name)
	return frappe.get_doc(
		{
			"doctype": "Attendance Device",
			"device_name": name,
			"adapter_type": "ZKTeco",
			"host": "10.0.0.1",
			"port": 4370,
			**kw,
		}
	).insert()


def make_file(name, content: bytes):
	return frappe.get_doc({"doctype": "File", "file_name": name, "content": content, "is_private": 1}).insert(
		ignore_permissions=True
	)


class TestAttendanceDevice(IntegrationTestCase):
	def setUp(self):
		patcher = patch.object(service, "adapter_for", lambda device: FakeAdapter(None))
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.db.rollback()

	def punches(self, device):
		return frappe.get_all(
			"Raw Punch",
			filters={"device": device},
			fields=["device_user_id", "jdate", "time", "direction", "is_duplicate", "device_timestamp"],
			order_by="device_user_id, jdate, time",
		)

	def test_sync_stores_jalali_day_time_and_flags_duplicates(self):
		device = make_device()
		stats = service.sync_device(device.name)
		self.assertEqual(stats, {"created": 4, "existing": 0, "duplicates": 1})
		rows = self.punches(device.name)
		self.assertEqual(
			[(r.device_user_id, r.jdate, r.time, r.direction, r.is_duplicate) for r in rows],
			[
				("101", "1405/07/14", "07:58:11", IN, 0),
				("101", "1405/07/14", "07:58:25", IN, 1),
				("101", "1405/07/14", "16:31:02", OUT, 0),
				("999", "1405/07/14", "09:00:00", UNKNOWN, 0),
			],
		)
		self.assertEqual(rows[0].device_timestamp, datetime(2026, 10, 6, 7, 58, 11))
		device.reload()
		self.assertEqual(device.last_sync_status, "OK")
		self.assertEqual(device.model, "VF600")
		self.assertEqual(
			frappe.utils.get_datetime(device.last_punch_timestamp), datetime(2026, 10, 6, 16, 31, 2)
		)

	def test_reading_again_never_doubles(self):
		device = make_device()
		service.sync_device(device.name)
		again = service.sync_device(device.name, since=None, use_watermark=False)
		self.assertEqual(again["created"], 0)
		self.assertEqual(again["existing"], 4)
		self.assertEqual(len(self.punches(device.name)), 4)

	def test_direction_mode_overrides_device_direction(self):
		device = make_device("T-Entry", direction_mode="Always In")
		service.sync_device(device.name)
		self.assertEqual({r.direction for r in self.punches(device.name)}, {IN})

	def test_raw_punch_is_append_only(self):
		device = make_device()
		service.sync_device(device.name)
		name = frappe.get_all("Raw Punch", filters={"device": device.name}, pluck="name")[0]
		doc = frappe.get_doc("Raw Punch", name)
		doc.time = "09:00:00"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Raw Punch", name)

	def test_read_users_maps_by_employee_code_and_unmapped_queue(self):
		from hozur.hozur.doctype.employee.test_employee import make_employee

		employee = make_employee("T-DEV-EMP")
		device = make_device()
		result = service.read_device_users(device.name)
		self.assertEqual(result, {"users": 3, "created": 3, "auto_mapped": 1})
		self.assertEqual(
			frappe.db.get_value(
				"Device User Map", {"device": device.name, "device_user_id": "T-DEV-EMP"}, "employee"
			),
			employee.name,
		)
		service.sync_device(device.name)
		unmapped = {(r.device, r.device_user_id) for r in service.unmapped_device_users()}
		self.assertIn((device.name, "101"), unmapped)
		self.assertIn((device.name, "999"), unmapped)

	def test_employee_punches_follow_map_validity(self):
		from hozur.hozur.doctype.employee.test_employee import make_employee

		device = make_device()
		service.sync_device(device.name)
		employee = make_employee("T-MAP-EMP")
		frappe.get_doc(
			{
				"doctype": "Device User Map",
				"device": device.name,
				"device_user_id": "101",
				"employee": employee.name,
				"valid_from": "1405/07/14",
			}
		).insert()
		punches = service.employee_punches(employee.name, "1405/07/01", "1405/07/30")
		self.assertEqual([p.time for p in punches], ["07:58:11", "07:58:25", "16:31:02"])
		self.assertEqual(service.employee_punches(employee.name, "1405/07/01", "1405/07/13"), [])
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Device User Map",
					"device": device.name,
					"device_user_id": "101",
					"valid_from": "1405/08/01",
				}
			).insert()

	def test_file_import_with_template_and_cross_source_dedup(self):
		device = make_device()
		service.sync_device(device.name)
		template = frappe.get_doc(
			{
				"doctype": "Punch Import Template",
				"template_name": "T-USB",
				"file_format": "ZKTeco USB (attlog.dat)",
			}
		).insert()
		attlog = b"   101\t2026-10-06 07:58:11\t15\t0\t1\t0\n   102\t2026-10-07 08:01:00\t1\t0\t1\t0\n"
		file_doc = make_file("attlog.dat", attlog)
		imp = frappe.get_doc(
			{
				"doctype": "Punch Import",
				"device": device.name,
				"template": template.name,
				"file": file_doc.file_url,
			}
		).insert()
		stats = imp.run_import()
		self.assertEqual(stats["created"], 1)  # 102's punch is new
		self.assertEqual(stats["existing"], 1)  # 101's punch was already read over the network
		imp.reload()
		self.assertEqual((imp.status, imp.created_count, imp.existing_count), ("Imported", 1, 1))
		self.assertEqual(imp.run_import()["created"], 0)

	def test_device_validation(self):
		with self.assertRaises(frappe.ValidationError):
			make_device("T-Bad-IP", host="not a host!")
		with self.assertRaises(frappe.ValidationError):
			make_device("T-Bad-Port", port=70000)
		file_device = make_device("T-File", adapter_type="File Import", host=None)
		self.assertTrue(file_device.name)
