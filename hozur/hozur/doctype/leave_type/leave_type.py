# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class LeaveType(Document):
	def validate(self):
		if self.category == "Sick" and self.deducts_from_balance:
			frappe.throw(_("Sick leave never reduces the leave balance (Article 74)"))
		if self.category == "Earned" and not self.is_paid:
			frappe.throw(_("Earned leave is paid (Article 64)"))
