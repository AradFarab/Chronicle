# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RawPunch(Document):
	"""Append-only evidence (CLAUDE.md rule 4). Created by hozur.devices.service only;
	corrections are Attendance Correction documents."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Raw punches cannot be changed. Use an attendance correction instead."))

	def on_trash(self):
		frappe.throw(_("Raw punches cannot be deleted. Use an attendance correction instead."))
