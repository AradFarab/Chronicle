# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

"""The PWA endpoints: same permission rules as the desk, and device setup without code."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from hozur.api import pwa
from hozur.devices import service
from hozur.hozur.doctype.attendance_correction.test_attendance_correction import build_org
from hozur.hozur.doctype.attendance_device.test_attendance_device import FakeAdapter, make_file
from hozur.setup.data import IMPORT_TEMPLATES, NO_APPROVAL
from hozur.setup.install import ensure_import_templates
from hozur.utils import clear_request_cache

DAY = "1405/07/13"


class TestPWA(IntegrationTestCase):
	def setUp(self):
		clear_request_cache()
		self.org = build_org()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		clear_request_cache()

	def as_user(self, user):
		frappe.set_user(user)
		clear_request_cache()

	def test_boot_describes_the_user(self):
		self.as_user(self.org.emp_user)
		boot = pwa.boot()
		self.assertEqual(boot["employee"]["name"], self.org.employee.name)
		self.assertFalse(boot["is_operator"])
		self.assertFalse(boot["is_manager"])
		self.as_user(self.org.mgr_user)
		self.assertTrue(pwa.boot()["is_manager"])

	def test_employee_sees_only_their_own_month(self):
		self.as_user(self.org.emp_user)
		days = pwa.month(1405, 7)["days"]
		self.assertEqual(len(days), 30)
		self.assertEqual(days[0]["jdate"], "1405/07/01")
		with self.assertRaises(frappe.PermissionError):
			pwa.month(1405, 7, employee=self.org.manager.name)
		# the manager sees the employee of a child department
		self.as_user(self.org.mgr_user)
		self.assertEqual(
			pwa.month(1405, 7, employee=self.org.employee.name)["employee"], self.org.employee.name
		)

	def test_manual_entry_from_the_pwa_goes_through_approval(self):
		self.as_user(self.org.emp_user)
		result = pwa.submit_request(
			"correction",
			{
				"jdate": DAY,
				"reason": "دستگاه خاموش بود",
				"status": "Approved",  # ignored: the server decides the status
				"items": [{"action": "Add Punch", "time": "08:00", "direction": "In"}],
			},
		)
		self.assertEqual(result["status"], "Pending")
		self.assertEqual(pwa.my_requests()[0]["name"], result["name"])
		# the manager finds it in the inbox
		self.as_user(self.org.mgr_user)
		self.assertIn(result["name"], [r["name"] for r in pwa.inbox()])

	def test_employee_cannot_file_for_someone_else(self):
		self.as_user(self.org.emp_user)
		with self.assertRaises(frappe.PermissionError):
			pwa.submit_request(
				"leave", {"employee": self.org.manager.name, "leave_type": "استحقاقی", "from_date": DAY}
			)

	def test_devices_are_for_operators(self):
		self.as_user(self.org.emp_user)
		with self.assertRaises(frappe.PermissionError):
			pwa.devices()
		with self.assertRaises(frappe.PermissionError):
			pwa.save_device({"device_name": "T-PWA-Device", "host": "10.0.0.9"})

	def test_operator_sets_up_a_device_from_the_pwa(self):
		self.as_user(self.org.op_user)
		name = pwa.save_device(
			{
				"device_name": "T-PWA-Device",
				"adapter_type": "ZKTeco",
				"host": "10.0.0.9",
				"port": 4370,
				"comm_key": "1234",
				"direction_mode": "From Device",
				"doctype": "User",  # not a device field: dropped
			}
		)["name"]
		form = pwa.device(name)
		self.assertEqual((form["host"], form["port"]), ("10.0.0.9", 4370))
		self.assertEqual(form["comm_key"], "*****")  # the key never travels back
		# saving the masked form keeps the stored key; changing the IP is just data
		pwa.save_device({**form, "host": "10.0.0.10"})
		doc = frappe.get_doc("Attendance Device", name)
		self.assertEqual((doc.host, doc.get_password("comm_key")), ("10.0.0.10", "1234"))
		self.assertIn(name, [d["name"] for d in pwa.devices()])
		options = pwa.device_options()
		self.assertIn("ZKTeco", [o["value"] for o in options["adapter_types"]])
		# the device tools work on the saved device
		with patch.object(service, "adapter_for", lambda device: FakeAdapter(None)):
			self.assertEqual(service.test_connection(name)["model"], "VF600")
			service.read_device_users(name)
		users = pwa.device_users(name)
		self.assertEqual(len(users), 3)
		unmapped = next(u for u in users if u["device_user_id"] == "101")
		self.assertEqual(
			pwa.map_device_user(unmapped["name"], self.org.employee.name)["employee"], self.org.employee.name
		)

	def test_operator_imports_a_usb_file(self):
		ensure_import_templates()
		frappe.db.set_single_value("Hozur Settings", "operator_entry_process", NO_APPROVAL)
		self.as_user(self.org.op_user)
		name = pwa.save_device({"device_name": "T-PWA-USB", "adapter_type": "File Import"})["name"]
		attlog = b"   101\t2026-10-05 07:58:11\t15\t0\t1\t0\n   101\t2026-10-05 16:40:00\t15\t1\t1\t0\n"
		file_url = make_file("attlog.dat", attlog).file_url
		result = pwa.import_punches(name, IMPORT_TEMPLATES[0]["template_name"], file_url)
		self.assertEqual((result["total_rows"], result["created"], result["errors"]), (2, 2, 0))
		again = pwa.import_punches(name, IMPORT_TEMPLATES[0]["template_name"], file_url)
		self.assertEqual((again["created"], again["existing"]), (0, 2))
