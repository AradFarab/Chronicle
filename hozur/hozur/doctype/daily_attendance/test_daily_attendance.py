# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

"""End to end: punches and requests in, Daily Attendance out."""

import frappe
from frappe.tests import IntegrationTestCase

from hozur.approvals import act_on_request
from hozur.attendance import attendance_name, calculate
from hozur.devices.service import ingest
from hozur.hozur.doctype.attendance_correction.test_attendance_correction import build_org
from hozur.hozur.doctype.attendance_device.test_attendance_device import make_device
from hozur.leave import add_entry, balance
from hozur.periods import PeriodLockedError
from hozur.setup.data import NO_APPROVAL
from hozur.utils import clear_request_cache

SUNDAY, MONDAY = "1405/07/12", "1405/07/13"  # 1405/07/14 is a Tuesday
EARNED = "استحقاقی"


def setup_schedule():
	if not frappe.db.exists("Shift", "T-Office"):
		frappe.get_doc(
			{
				"doctype": "Shift",
				"shift_name": "T-Office",
				"start_time": "08:00:00",
				"end_time": "16:30:00",
				"break_start_time": "12:30:00",
				"break_end_time": "13:10:00",
				"grace_late_minutes": 5,
				"grace_early_minutes": 5,
			}
		).insert()
	if not frappe.db.exists("Work Pattern", "T-Week"):
		days = [
			{"weekday": d, "shift": "T-Office"}
			for d in ("Saturday", "Sunday", "Monday", "Tuesday", "Wednesday")
		]
		days += [{"weekday": "Thursday"}, {"weekday": "Friday"}]
		frappe.get_doc(
			{"doctype": "Work Pattern", "pattern_name": "T-Week", "weekly_rest_day": "Friday", "days": days}
		).insert()
	frappe.get_doc(
		{
			"doctype": "Work Pattern Assignment",
			"assign_to": "Company",
			"work_pattern": "T-Week",
			"valid_from": "1405/07/10",
		}
	).insert()


def day(employee, jdate):
	return frappe.get_doc("Daily Attendance", attendance_name(employee, jdate))


class TestDailyAttendance(IntegrationTestCase):
	def setUp(self):
		clear_request_cache()
		frappe.db.set_single_value("Hozur Settings", "operator_entry_process", NO_APPROVAL)
		self.org = build_org()
		setup_schedule()
		self.employee = self.org.employee.name
		self.device = make_device("T-DA-Device")
		frappe.get_doc(
			{
				"doctype": "Device User Map",
				"device": self.device.name,
				"device_user_id": "77",
				"employee": self.employee,
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		clear_request_cache()

	def punch(self, jdate, *times):
		ingest(self.device, [{"device_user_id": "77", "jdate": jdate, "time": t} for t in times], "Device")
		clear_request_cache()

	def test_punches_become_a_present_day(self):
		self.punch(SUNDAY, "07:58:30", "16:31:00")
		d = day(self.employee, SUNDAY)
		self.assertEqual((d.status, d.shift, d.work_pattern), ("Present", "T-Office", "T-Week"))
		# 07:58:30-16:31 minus the break: 473 minutes worked, 3 of them outside the shift
		self.assertEqual(
			(d.required_minutes, d.worked_minutes, d.late_minutes, d.absence_minutes), (470, 473, 0, 0)
		)
		self.assertEqual((d.credited_minutes, d.extra_minutes), (470, 3))
		self.assertEqual((d.first_in, d.last_out), ("07:58", "16:31"))
		self.assertEqual(d.department, self.org.employee.department)

	def test_no_punches_is_absent_and_a_correction_fixes_it(self):
		calculate(self.employee, MONDAY)
		self.assertEqual(day(self.employee, MONDAY).status, "Absent")
		frappe.get_doc(
			{
				"doctype": "Attendance Correction",
				"employee": self.employee,
				"jdate": MONDAY,
				"reason": "دستگاه خاموش بود",
				"items": [
					{"action": "Add Punch", "time": "08:00"},
					{"action": "Add Punch", "time": "16:30", "direction": "Out"},
				],
			}
		).insert().submit()
		d = day(self.employee, MONDAY)
		self.assertEqual((d.status, d.absence_minutes, d.worked_minutes), ("Present", 0, 470))
		entry = frappe.get_last_doc(
			"Audit Entry", filters={"reference_doctype": "Daily Attendance", "reference_name": d.name}
		)
		self.assertIn("status", entry.changed_fields)

	def test_daily_leave_uses_the_ledger_and_checks_the_balance(self):
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": EARNED,
				"from_date": MONDAY,
				"to_date": "1405/07/14",
			}
		).insert()
		self.assertEqual(leave.total_days, 2)
		with self.assertRaises(frappe.ValidationError):
			leave.submit()  # no balance yet
		add_entry(self.employee, EARNED, "Adjustment", "1405/07/01", 10, note="opening balance")
		leave.reload()
		leave.submit()  # operator entry, no approval process
		self.assertEqual(leave.status, "Approved")
		self.assertEqual(balance(self.employee, EARNED), 8)
		d = day(self.employee, MONDAY)
		self.assertEqual((d.status, d.leave_days, d.absence_minutes), ("Leave", 1, 0))
		leave.cancel()
		self.assertEqual(balance(self.employee, EARNED), 10)
		self.assertEqual(day(self.employee, MONDAY).status, "Absent")

	def test_hourly_leave_is_counted_in_days_of_seven_hours_twenty(self):
		add_entry(self.employee, EARNED, "Adjustment", "1405/07/01", 5, note="opening balance")
		self.punch(SUNDAY, "10:00", "16:30")
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": EARNED,
				"leave_unit": "Hourly",
				"jdate": SUNDAY,
				"from_time": "08:00:00",
				"to_time": "10:00:00",
			}
		).insert().submit()
		d = day(self.employee, SUNDAY)
		self.assertEqual((d.late_minutes, d.absence_minutes, d.leave_minutes), (0, 0, 120))
		self.assertAlmostEqual(d.leave_days, round(120 / 440, 4))
		self.assertAlmostEqual(balance(self.employee, EARNED), round(5 - 120 / 440, 4))

	def test_overtime_assigned_by_a_manager_needs_the_employees_acceptance(self):
		self.punch(SUNDAY, "08:00", "17:30")
		self.assertEqual(day(self.employee, SUNDAY).unapproved_extra_minutes, 60)
		frappe.set_user(self.org.mgr_user)
		ot = frappe.get_doc(
			{"doctype": "Overtime Request", "employee": self.employee, "jdate": SUNDAY, "minutes": 60}
		).insert()
		ot.submit()
		self.assertTrue(ot.assigned_by_manager)
		self.assertEqual((ot.status, ot.pending_approver), ("Pending", self.employee))
		frappe.set_user(self.org.emp_user)
		act_on_request("Overtime Request", ot.name, "Approve", "قبول دارم")
		frappe.set_user("Administrator")
		ot.reload()
		self.assertEqual(ot.status, "Approved")
		d = day(self.employee, SUNDAY)
		self.assertEqual((d.overtime_normal_minutes, d.unapproved_extra_minutes), (60, 0))

	def test_company_holiday_recalculates_the_day(self):
		self.punch(SUNDAY, "08:00", "12:00")
		self.assertEqual(day(self.employee, SUNDAY).status, "Present")
		frappe.get_doc(
			{
				"doctype": "Iran Holiday",
				"jdate": SUNDAY,
				"title": "تعطیلی شرکت",
				"holiday_type": "Company Internal",
				"scope": "Company",
			}
		).insert()
		d = day(self.employee, SUNDAY)
		self.assertEqual((d.status, d.company_holiday_work_minutes, d.required_minutes), ("Holiday", 240, 0))

	def test_shift_override_day_off(self):
		frappe.get_doc(
			{"doctype": "Shift Override", "employee": self.employee, "jdate": MONDAY, "reason": "جابه‌جایی"}
		).insert()
		d = day(self.employee, MONDAY)
		self.assertEqual((d.status, d.required_minutes), ("Not Scheduled", 0))

	def test_closed_period_cannot_change(self):
		self.punch(SUNDAY, "08:00", "16:30")
		period = frappe.get_doc({"doctype": "Attendance Period", "period": "1405/07"}).insert()
		period.close()
		clear_request_cache()
		with self.assertRaises(PeriodLockedError):
			frappe.get_doc(
				{
					"doctype": "Attendance Correction",
					"employee": self.employee,
					"jdate": MONDAY,
					"reason": "x",
					"items": [{"action": "Add Punch", "time": "08:00"}],
				}
			).insert().submit()
		# a late punch is still stored as evidence but the closed day does not change
		self.punch(SUNDAY, "18:00", "19:00")
		self.assertEqual(day(self.employee, SUNDAY).extra_minutes, 0)
		period.reload()
		period.reopen("اصلاح دیرهنگام")
		clear_request_cache()
		calculate(self.employee, SUNDAY)
		self.assertEqual(day(self.employee, SUNDAY).extra_minutes, 60)

	def test_rule_set_cannot_be_worse_than_the_law(self):
		base = frappe.get_doc("Labor Rule Set", {"is_legal_baseline": 1})
		worse = frappe.copy_doc(base)
		worse.update(
			{
				"rule_set_name": "T-Worse",
				"is_legal_baseline": 0,
				"effective_from": "1405/07/01",
				"annual_leave_days": 20,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			worse.insert()
		better = frappe.copy_doc(base)
		better.update(
			{
				"rule_set_name": "T-Better",
				"is_legal_baseline": 0,
				"effective_from": "1405/07/01",
				"hourly_leave_minutes_per_day": 480,
			}
		)
		better.insert()
		with self.assertRaises(frappe.ValidationError):
			base.max_daily_minutes = 450
			base.save()

	def test_daily_attendance_cannot_be_edited_by_hand(self):
		self.punch(SUNDAY, "08:00", "16:30")
		d = day(self.employee, SUNDAY)
		d.worked_minutes = 999
		with self.assertRaises(frappe.ValidationError):
			d.save()
