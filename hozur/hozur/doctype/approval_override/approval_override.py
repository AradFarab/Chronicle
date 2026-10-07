# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ApprovalOverride(Document):
	def validate(self):
		other = frappe.db.get_value(
			"Approval Override",
			{"employee": self.employee, "request_type": self.request_type, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} already has an exception for {1} ({2})").format(
					self.employee, _(self.request_type), other
				)
			)
