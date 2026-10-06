# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate


class LeaveLedgerEntry(Document):
	"""Append-only. Operators may add Adjustment entries by hand; everything else is posted by
	the system (hozur.leave)."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Ledger entries cannot be changed; add an adjustment instead"))
		clean_jdate(self, "jdate", required=True)
		self.jyear = int(self.jdate[:4])
		if not self.flags.from_system:
			if self.entry_type != "Adjustment":
				frappe.throw(_("Only adjustments can be entered by hand"))
			if not (self.note or "").strip():
				frappe.throw(_("Enter the reason for the adjustment"))

	def after_insert(self):
		if not self.flags.from_system:
			from hozur import audit

			audit.log(
				self.doctype,
				self.name,
				"Insert",
				self.note,
				after={"days": self.days, "leave_type": self.leave_type},
			)

	def on_trash(self):
		frappe.throw(_("Ledger entries cannot be deleted; add an adjustment instead"))
