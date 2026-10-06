# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReportTemplate(Document):
	def validate(self):
		from hozur.reports.builder import validate_spec

		if self.source != "Daily":
			self.group_by = None
		validate_spec(
			{
				"source": self.source,
				"group_by": self.group_by or "",
				"columns": [{"field": c.field, "label": c.label} for c in self.columns],
			}
		)
