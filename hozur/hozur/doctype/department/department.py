# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet

from hozur.utils import clean_jdate, validate_date_order


class Department(NestedSet):
	nsm_parent_field = "parent_department"

	def validate(self):
		clean_jdate(self, "deputy_from")
		clean_jdate(self, "deputy_to")
		validate_date_order(self, "deputy_from", "deputy_to")
		if not self.deputy:
			self.deputy_from = self.deputy_to = None
		if self.deputy and self.deputy == self.manager:
			frappe.throw(_("The deputy must be someone other than the manager"))

	def on_trash(self):
		if frappe.db.exists("Employee", {"department": self.name}):
			frappe.throw(_("Department {0} still has employees").format(self.name))
		super().on_trash()
