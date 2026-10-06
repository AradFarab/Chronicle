# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from hozur.hozur.doctype.employee.employee import is_valid_national_code
from hozur.permissions import visible_employees


def national_code(prefix: str) -> str:
	"""Complete a 9-digit prefix with its check digit."""
	total = sum(int(prefix[i]) * (10 - i) for i in range(9)) % 11
	return prefix + str(total if total < 2 else 11 - total)


def make_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


def make_department(name, parent="همه واحدها", **kw):
	if frappe.db.exists("Department", name):
		return frappe.get_doc("Department", name)
	return frappe.get_doc(
		{"doctype": "Department", "department_name": name, "parent_department": parent, "is_group": 1, **kw}
	).insert()


def make_employee(code, department=None, user=None, **kw):
	if frappe.db.exists("Employee", code):
		return frappe.get_doc("Employee", code)
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"employee_code": code,
			"first_name": "کارمند",
			"last_name": code,
			"start_date": "1404/01/15",
			"department": department,
			"user": user,
			**kw,
		}
	).insert()


def clear_request_cache():
	if hasattr(frappe.local, "request_cache"):
		frappe.local.request_cache.clear()


class TestEmployee(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()
		clear_request_cache()

	def test_national_code_checksum(self):
		self.assertTrue(is_valid_national_code(national_code("001234567")))
		self.assertFalse(is_valid_national_code("1111111111"))
		self.assertFalse(is_valid_national_code("12345"))
		code = national_code("001234567")
		wrong = code[:9] + str((int(code[9]) + 1) % 10)
		self.assertFalse(is_valid_national_code(wrong))
		with self.assertRaises(frappe.ValidationError):
			make_employee("T-NC-1", national_id=wrong)

	def test_full_name_and_jalali_dates(self):
		emp = make_employee("T-FN-1", start_date="۱۴۰۴/۰۲/۰۱")
		self.assertEqual(emp.full_name, "کارمند T-FN-1")
		self.assertEqual(emp.start_date, "1404/02/01")
		emp.status = "Left"
		with self.assertRaises(frappe.ValidationError):
			emp.save()

	def test_manager_sees_department_subtree_only(self):
		manager_user = make_user("hozur-test-manager@example.com")
		staff_user = make_user("hozur-test-staff@example.com")
		furniture = make_department("T-مبلمان")
		sales = make_department("T-فروش مبلمان", parent=furniture.name, is_group=0)
		cafe = make_department("T-کافه")
		manager = make_employee("T-M-1", department=furniture.name, user=manager_user)
		furniture.reload()
		furniture.manager = manager.name
		furniture.save()
		seller = make_employee("T-S-1", department=sales.name, user=staff_user)
		barista = make_employee("T-B-1", department=cafe.name)
		clear_request_cache()

		visible = visible_employees(manager_user)
		self.assertIn(manager.name, visible)
		self.assertIn(seller.name, visible)
		self.assertNotIn(barista.name, visible)

		clear_request_cache()
		self.assertEqual(visible_employees(staff_user), [seller.name])
		self.assertIsNone(visible_employees("Administrator"))

	def test_direct_reports_are_visible(self):
		boss_user = make_user("hozur-test-boss@example.com")
		boss = make_employee("T-BOSS-1", user=boss_user)
		report = make_employee("T-R-1", reports_to=boss.name)
		clear_request_cache()
		self.assertIn(report.name, visible_employees(boss_user))

	def test_linking_user_grants_employee_role(self):
		user = make_user("hozur-test-role@example.com")
		make_employee("T-ROLE-1", user=user)
		self.assertIn("Hozur Employee", frappe.get_roles(user))
