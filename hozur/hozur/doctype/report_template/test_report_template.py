# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import io

import frappe
from frappe.tests import IntegrationTestCase
from openpyxl import load_workbook

from hozur.devices.service import ingest
from hozur.hozur.doctype.attendance_correction.test_attendance_correction import build_org
from hozur.hozur.doctype.attendance_device.test_attendance_device import make_device
from hozur.hozur.doctype.daily_attendance.test_daily_attendance import setup_schedule
from hozur.hozur.doctype.employee.test_employee import make_employee
from hozur.leave import add_entry
from hozur.reports import api, builder
from hozur.utils import clear_request_cache

FILTERS = {"from_date": "1405/07/12", "to_date": "1405/07/13"}
SPEC = {
	"title": "T",
	"source": "Summary",
	"columns": [
		{"field": "employee"},
		{"field": "worked_minutes"},
		{"field": "absent_days"},
		{"field": "paid_days"},
		{"field": "employed_days"},
		{"field": "leave_balance"},
		{"field": "leave:استحقاقی"},
	],
}


class TestReportTemplate(IntegrationTestCase):
	def setUp(self):
		clear_request_cache()
		self.org = build_org()
		setup_schedule()
		self.device = make_device("T-RP-Device")
		self.other = make_employee("T-OTHER", department=None)
		for emp, uid in ((self.org.employee.name, "81"), (self.other.name, "82")):
			frappe.get_doc(
				{
					"doctype": "Device User Map",
					"device": self.device.name,
					"device_user_id": uid,
					"employee": emp,
				}
			).insert()
		# employee 81 works Sunday and is absent Monday; 82 works both days
		ingest(
			self.device,
			[{"device_user_id": "81", "jdate": "1405/07/12", "time": t} for t in ("08:00:00", "16:30:00")],
			"Device",
		)
		ingest(
			self.device,
			[
				{"device_user_id": "82", "jdate": d, "time": t}
				for d in ("1405/07/12", "1405/07/13")
				for t in ("08:00:00", "16:30:00")
			],
			"Device",
		)
		from hozur.attendance import calculate

		calculate(self.org.employee.name, "1405/07/13")
		add_entry(self.org.employee.name, "استحقاقی", "Adjustment", "1405/07/01", 4.5, note="opening")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		clear_request_cache()

	def rows_by_employee(self, result):
		return {r["employee"]: r for r in result["rows"]}

	def test_summary_numbers(self):
		result = builder.build(SPEC, FILTERS)
		row = self.rows_by_employee(result)[self.org.employee.name]
		self.assertEqual(row["worked_minutes"], 470)
		self.assertEqual(row["absent_days"], 1)
		self.assertEqual(row["employed_days"], 2)
		self.assertEqual(row["paid_days"], 1)  # two days minus one unexcused absence
		self.assertEqual(row["leave_balance"], 4.5)
		other = self.rows_by_employee(result)[self.other.name]
		self.assertEqual((other["worked_minutes"], other["paid_days"]), (940, 2))

	def test_manager_sees_only_their_department(self):
		frappe.set_user(self.org.mgr_user)
		employees = set(self.rows_by_employee(builder.build(SPEC, FILTERS)))
		self.assertIn(self.org.employee.name, employees)
		self.assertNotIn(self.other.name, employees)
		with self.assertRaises(frappe.PermissionError):
			builder.build(SPEC, {**FILTERS, "employee": self.other.name})

	def test_unknown_fields_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			builder.build({"source": "Summary", "columns": [{"field": "salary"}]}, FILTERS)

	def test_daily_rows_and_grouping(self):
		spec = {
			"source": "Daily",
			"columns": [{"field": "jdate"}, {"field": "status"}, {"field": "worked_minutes"}],
		}
		result = builder.build(
			{**spec, "columns": [{"field": "employee"}, *spec["columns"]]},
			{**FILTERS, "employee": self.org.employee.name},
		)
		self.assertEqual(
			[(r["jdate"], r["status"]) for r in result["rows"]],
			[("1405/07/12", "Present"), ("1405/07/13", "Absent")],
		)
		by_day = builder.build({**spec, "group_by": "Day"}, FILTERS)
		self.assertEqual(
			{r["jdate"]: r["worked_minutes"] for r in by_day["rows"]}, {"1405/07/12": 940, "1405/07/13": 470}
		)

	def test_exports(self):
		name, content = api.render(SPEC, FILTERS, "Excel")
		self.assertTrue(name.endswith(".xlsx"))
		ws = load_workbook(io.BytesIO(content)).active
		self.assertTrue(ws.sheet_view.rightToLeft)
		name, content = api.render(
			{**SPEC, "text_delimiter": "Tab", "text_encoding": "Windows-1256"}, FILTERS, "Text"
		)
		self.assertIn("T-EMP", content.decode("cp1256"))
		name, content = api.render(SPEC, FILTERS, "PDF")
		self.assertTrue(content.startswith(b"%PDF"))

	def test_standard_templates_are_installed(self):
		for name in ("کارکرد ماهانه برای حقوق", "گزارش مرخصی", "گزارش اضافه‌کار", "حاضرین امروز"):
			self.assertTrue(frappe.db.get_value("Report Template", name, "is_standard"))
		result = api.preview("کارکرد ماهانه برای حقوق", filters=FILTERS)
		self.assertIn(self.org.employee.name, {r["employee"] for r in result["rows"]})
