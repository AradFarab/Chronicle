# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate, validate_date_order


def is_valid_national_code(code: str) -> bool:
	"""Iranian national code (کد ملی): 10 digits, last one is a mod-11 check digit."""
	if len(code) != 10 or not code.isdigit() or len(set(code)) == 1:
		return False
	total = sum(int(code[i]) * (10 - i) for i in range(9)) % 11
	check = int(code[9])
	return check == total if total < 2 else check == 11 - total


class Employee(Document):
	def validate(self):
		from hozur.jalali.dates import to_ascii_digits

		self.first_name = (self.first_name or "").strip()
		self.last_name = (self.last_name or "").strip()
		self.full_name = f"{self.first_name} {self.last_name}".strip()
		self.employee_code = to_ascii_digits((self.employee_code or "").strip())
		if self.national_id:
			self.national_id = to_ascii_digits(self.national_id.strip())
			if not is_valid_national_code(self.national_id):
				frappe.throw(_("National code {0} is not valid").format(self.national_id))
			duplicate = frappe.db.get_value(
				"Employee", {"national_id": self.national_id, "name": ["!=", self.name]}, "name"
			)
			if duplicate:
				frappe.throw(
					_("National code {0} already belongs to employee {1}").format(self.national_id, duplicate)
				)
		clean_jdate(self, "start_date", required=True)
		clean_jdate(self, "end_date")
		validate_date_order(self, "start_date", "end_date")
		clean_jdate(self, "birth_date")
		clean_jdate(self, "biometric_consent_date")
		if self.status == "Left" and not self.end_date:
			frappe.throw(_("Enter the end date for an employee who has left"))
		if self.reports_to and self.reports_to == self.name:
			frappe.throw(_("An employee cannot be their own manager"))
		if self.user:
			other = frappe.db.get_value("Employee", {"user": self.user, "name": ["!=", self.name]}, "name")
			if other:
				frappe.throw(_("User {0} is already linked to employee {1}").format(self.user, other))

	def on_update(self):
		if self.user:
			add_role(self.user, "Hozur Employee")


def add_role(user: str, role: str):
	user_doc = frappe.get_doc("User", user)
	if role not in {r.role for r in user_doc.roles}:
		user_doc.flags.ignore_permissions = True
		user_doc.add_roles(role)
