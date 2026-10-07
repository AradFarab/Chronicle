# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HozurSettings(Document):
	def validate(self):
		if (self.dedup_window_seconds or 0) < 0:
			frappe.throw(_("Duplicate Punch Window cannot be negative"))
