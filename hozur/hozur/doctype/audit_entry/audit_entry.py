# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AuditEntry(Document):
	"""Append-only: created by hozur.audit, never edited or deleted."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Audit entries cannot be changed"))

	def on_trash(self):
		frappe.throw(_("Audit entries cannot be deleted"))
