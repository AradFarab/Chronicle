# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DailyAttendance(Document):
	"""Output of the engine (hozur.attendance). Never edited by hand: fix the punches or the
	requests and the day is recalculated."""

	def validate(self):
		if not self.flags.from_engine:
			frappe.throw(_("Daily attendance is calculated. Correct the punches or requests instead."))

	def on_trash(self):
		if not self.flags.from_engine and not frappe.flags.in_uninstall:
			from hozur.periods import assert_open

			assert_open(self.jdate)
