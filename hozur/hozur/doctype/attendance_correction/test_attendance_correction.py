# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from hozur.approvals import act_on_request, direct_manager, my_approvals, parent_department_manager
from hozur.hozur.doctype.employee.test_employee import (
	clear_request_cache,
	make_department,
	make_employee,
	make_user,
)
from hozur.punches import effective_punches
from hozur.setup.data import MANAGER_THEN_CEO, NO_APPROVAL

DAY = "1405/07/12"


def build_org():
	"""root > T-Sales (manager M, reports to CEO) > T-Sales-Team (no manager): E works there."""
	ceo_user = make_user("hozur-ceo@example.com")
	mgr_user = make_user("hozur-mgr@example.com")
	emp_user = make_user("hozur-emp@example.com")
	op_user = make_user("hozur-op@example.com")
	frappe.get_doc("User", op_user).add_roles("Hozur Operator")
	ceo = make_employee("T-CEO", user=ceo_user)
	sales = make_department("T-Sales")
	team = make_department("T-Sales-Team", parent=sales.name, is_group=0)
	manager = make_employee("T-MGR", department=sales.name, user=mgr_user, reports_to=ceo.name)
	sales.reload()
	sales.manager = manager.name
	sales.save()
	employee = make_employee("T-EMP", department=team.name, user=emp_user)
	org = frappe.get_single("Organization")
	org.organization_name = org.organization_name or "شرکت آزمایشی"
	org.ceo = ceo.name
	org.save()
	return frappe._dict(
		ceo=ceo,
		manager=manager,
		employee=employee,
		ceo_user=ceo_user,
		mgr_user=mgr_user,
		emp_user=emp_user,
		op_user=op_user,
	)


def make_correction(employee, items, submit=True, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Correction",
			"employee": employee,
			"jdate": DAY,
			"reason": "فراموشی ثبت",
			"items": items,
			**kw,
		}
	).insert()
	if submit:
		doc.submit()
	return doc


class TestAttendanceCorrection(IntegrationTestCase):
	def setUp(self):
		self.org = build_org()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		clear_request_cache()

	def test_direct_manager_walks_up_the_tree(self):
		self.assertEqual(direct_manager(self.org.employee.name), self.org.manager.name)
		# a manager's direct manager is above them (here reports_to)
		self.assertEqual(direct_manager(self.org.manager.name), self.org.ceo.name)
		self.assertIsNone(parent_department_manager(self.org.employee.name))

	def test_employee_request_approved_by_manager_adds_manual_punch(self):
		frappe.set_user(self.org.emp_user)
		doc = make_correction(
			self.org.employee.name, [{"action": "Add Punch", "time": "۸:۰۵", "direction": "In"}]
		)
		self.assertEqual((doc.status, doc.pending_approver), ("Pending", self.org.manager.name))
		self.assertEqual(doc.items[0].time, "08:05:00")
		self.assertEqual(effective_punches(self.org.employee.name, DAY), [])

		frappe.set_user(self.org.mgr_user)
		self.assertIn(doc.name, [r.name for r in my_approvals()])
		result = act_on_request("Attendance Correction", doc.name, "Approve", "تأیید")
		self.assertEqual(result["status"], "Approved")
		frappe.set_user("Administrator")
		punches = effective_punches(self.org.employee.name, DAY)
		self.assertEqual(
			[(p["time"], p["direction"], p["source"]) for p in punches], [("08:05:00", "In", "Manual")]
		)
		actions = frappe.get_all("Audit Entry", filters={"reference_name": doc.name}, pluck="action")
		self.assertIn("Submit", actions)
		self.assertIn("Approve", actions)

	def test_only_the_current_approver_can_act(self):
		frappe.set_user(self.org.emp_user)
		doc = make_correction(self.org.employee.name, [{"action": "Add Punch", "time": "08:00"}])
		with self.assertRaises(frappe.PermissionError):
			act_on_request("Attendance Correction", doc.name, "Approve")
		frappe.set_user(self.org.ceo_user)
		with self.assertRaises(frappe.PermissionError):
			act_on_request("Attendance Correction", doc.name, "Approve")

	def test_employee_cannot_request_for_someone_else(self):
		frappe.set_user(self.org.emp_user)
		with self.assertRaises(frappe.PermissionError):
			make_correction(self.org.manager.name, [{"action": "Add Punch", "time": "08:00"}], submit=False)

	def test_two_step_override_and_rejection(self):
		frappe.get_doc(
			{
				"doctype": "Approval Override",
				"employee": self.org.employee.name,
				"request_type": "Attendance Correction",
				"approval_process": MANAGER_THEN_CEO,
			}
		).insert()
		frappe.set_user(self.org.emp_user)
		doc = make_correction(
			self.org.employee.name, [{"action": "Add Punch", "time": "17:00", "direction": "Out"}]
		)
		self.assertEqual([r.approver for r in doc.approvals], [self.org.manager.name, self.org.ceo.name])
		frappe.set_user(self.org.mgr_user)
		act_on_request("Attendance Correction", doc.name, "Approve")
		doc.reload()
		self.assertEqual((doc.status, doc.pending_approver), ("Pending", self.org.ceo.name))
		frappe.set_user(self.org.ceo_user)
		act_on_request("Attendance Correction", doc.name, "Reject", "ساعت خروج درست نیست")
		doc.reload()
		self.assertEqual(doc.status, "Rejected")
		frappe.set_user("Administrator")
		self.assertEqual(effective_punches(self.org.employee.name, DAY), [])

	def test_operator_entry_uses_operator_process(self):
		frappe.db.set_single_value("Hozur Settings", "operator_entry_process", NO_APPROVAL)
		frappe.set_user(self.org.op_user)
		doc = make_correction(
			self.org.employee.name,
			[
				{"action": "Add Punch", "time": "08:00"},
				{"action": "Add Punch", "time": "16:00", "direction": "Out"},
			],
		)
		self.assertEqual(doc.status, "Approved")
		self.assertTrue(doc.entered_by_operator)
		frappe.set_user("Administrator")
		self.assertEqual(
			[p["time"] for p in effective_punches(self.org.employee.name, DAY)], ["08:00:00", "16:00:00"]
		)

	def test_ignore_a_wrong_device_punch(self):
		from hozur.hozur.doctype.attendance_device.test_attendance_device import make_device

		device = make_device("T-Corr-Device")
		frappe.get_doc(
			{
				"doctype": "Device User Map",
				"device": device.name,
				"device_user_id": "55",
				"employee": self.org.employee.name,
			}
		).insert()
		from hozur.devices.service import ingest

		ingest(
			device,
			[{"device_user_id": "55", "jdate": DAY, "time": t} for t in ("07:59:00", "12:00:00", "16:30:00")],
			"Device",
		)
		wrong = frappe.get_value("Raw Punch", {"device": device.name, "time": "12:00:00"}, "name")
		frappe.db.set_single_value("Hozur Settings", "operator_entry_process", NO_APPROVAL)
		make_correction(self.org.employee.name, [{"action": "Ignore Punch", "raw_punch": wrong}])
		self.assertEqual(
			[p["time"] for p in effective_punches(self.org.employee.name, DAY)], ["07:59:00", "16:30:00"]
		)
		# the raw punch itself is untouched
		self.assertTrue(frappe.db.exists("Raw Punch", wrong))

	def test_validation(self):
		with self.assertRaises(frappe.ValidationError):
			make_correction(self.org.employee.name, [{"action": "Add Punch", "time": "25:00"}], submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_correction(
				self.org.employee.name,
				[{"action": "Add Punch", "time": "08:00"}],
				submit=False,
				jdate="1499/01/01",
			)
		with self.assertRaises(frappe.ValidationError):
			make_correction(
				self.org.employee.name, [{"action": "Ignore Punch", "raw_punch": "not-a-punch"}], submit=False
			)

	def test_cancel_withdraws_the_correction(self):
		frappe.db.set_single_value("Hozur Settings", "operator_entry_process", NO_APPROVAL)
		doc = make_correction(self.org.employee.name, [{"action": "Add Punch", "time": "08:00"}])
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Attendance Correction", doc.name, "status"), "Cancelled")
		self.assertEqual(effective_punches(self.org.employee.name, DAY), [])
