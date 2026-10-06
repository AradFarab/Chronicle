# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

DAY = "1405/07/14"  # a Tuesday workday


def make_holiday(**kw):
	doc = frappe.get_doc(
		{
			"doctype": "Iran Holiday",
			"jdate": DAY,
			"title": "آلودگی هوا",
			"holiday_type": "Office Closure",
			"closure_pay_mode": "Paid Holiday",
			"scope": "Country",
			**kw,
		}
	)
	return doc.insert()


class TestIranHoliday(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_nationwide_closure_updates_calendar_day_and_back(self):
		self.assertEqual(frappe.db.get_value("Calendar Day", DAY, "day_type"), "Workday")
		doc = make_holiday()
		self.assertEqual(frappe.db.get_value("Calendar Day", DAY, "day_type"), "Official Holiday")
		doc.delete()
		self.assertEqual(frappe.db.get_value("Calendar Day", DAY, "day_type"), "Workday")

	def test_employer_paid_closure_does_not_change_the_national_day(self):
		make_holiday(closure_pay_mode="Employer Paid")
		self.assertEqual(frappe.db.get_value("Calendar Day", DAY, "day_type"), "Workday")

	def test_update_requires_reason_and_is_audited(self):
		doc = make_holiday()
		doc.title = "تعطیلی آلودگی هوا"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.title = "تعطیلی آلودگی هوا"
		doc.change_reason = "اعلام استانداری"
		doc.save()
		entry = frappe.get_last_doc(
			"Audit Entry", filters={"reference_doctype": "Iran Holiday", "reference_name": doc.name}
		)
		self.assertEqual(entry.action, "Update")
		self.assertEqual(entry.reason, "اعلام استانداری")
		self.assertIn("title", entry.changed_fields)
		self.assertIn("آلودگی هوا", entry.before)
		doc.reload()
		self.assertFalse(doc.change_reason)
		self.assertTrue(doc.edited_by_operator)

	def test_date_is_normalized_from_persian_digits(self):
		doc = make_holiday(jdate="۱۴۰۵/۰۷/۱۴")
		self.assertEqual(doc.jdate, DAY)
		self.assertEqual((doc.jyear, doc.jmonth), (1405, 7))

	def test_invalid_date_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_holiday(jdate="1405/07/31")

	def test_scope_rules(self):
		with self.assertRaises(frappe.ValidationError):
			make_holiday(holiday_type="Company Internal", closure_pay_mode=None, scope="Country")
		with self.assertRaises(frappe.ValidationError):
			make_holiday(
				holiday_type="Official Lunar", closure_pay_mode=None, scope="Province", province="تهران"
			)

	def test_seeded_1405_holiday_is_on_the_calendar(self):
		self.assertEqual(frappe.db.get_value("Calendar Day", "1405/04/04", "day_type"), "Official Holiday")
		self.assertTrue(frappe.db.exists("Iran Holiday", {"seed_key": "1405/04/04:ashura"}))
