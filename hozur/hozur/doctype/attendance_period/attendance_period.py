# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from hozur import audit
from hozur.jalali.dates import month_bounds, to_ascii_digits
from hozur.utils import clear_request_cache, now_jalali

PERIOD_RE = re.compile(r"^(\d{4})/(\d{2})$")
REQUEST_DOCTYPES = (
	("Leave Application", "start_jdate", "end_jdate"),
	("Mission", "start_jdate", "end_jdate"),
	("Overtime Request", "jdate", "jdate"),
	("Attendance Correction", "jdate", "jdate"),
)


class AttendancePeriod(Document):
	def validate(self):
		self.period = to_ascii_digits((self.period or "").strip())
		m = PERIOD_RE.match(self.period)
		if not m or not 1 <= int(m[2]) <= 12:
			frappe.throw(_("Enter the period as a Jalali month, e.g. 1405/07"))
		self.jyear, self.jmonth = int(m[1]), int(m[2])
		if not self.is_new() and self.has_value_changed("status") and not self.flags.status_action:
			frappe.throw(_("Use the Close and Reopen buttons"))

	def bounds(self):
		return month_bounds(self.jyear, self.jmonth)

	@frappe.whitelist()
	def close(self):
		"""Recalculate the month one last time and lock it."""
		frappe.only_for(["System Manager", "Hozur Operator"])
		if self.status == "Closed":
			return
		start, end = self.bounds()
		pending = []
		for doctype, lo, hi in REQUEST_DOCTYPES:
			pending += frappe.get_all(
				doctype,
				filters={"docstatus": 1, "status": "Pending", lo: ["<=", end], hi: [">=", start]},
				pluck="name",
			)
		if pending:
			frappe.throw(_("These requests are still waiting for approval: {0}").format(", ".join(pending)))
		from hozur.attendance import active_employees, calculate
		from hozur.jalali.dates import iter_days

		for jdate in iter_days(start, min(end, now_jalali()[0])):
			for employee in active_employees(jdate):
				calculate(employee, jdate, _("Closing period {0}").format(self.period))
		jdate, time = now_jalali()
		self.flags.status_action = True
		self.status, self.closed_by, self.closed_on = "Closed", frappe.session.user, f"{jdate} {time}"
		self.save(ignore_permissions=True)
		audit.log(self.doctype, self.name, "Lock", self.note)
		clear_request_cache()

	@frappe.whitelist()
	def reopen(self, reason: str):
		frappe.only_for(["System Manager", "Hozur Operator"])
		if not (reason or "").strip():
			frappe.throw(_("Enter the reason for reopening"))
		self.flags.status_action = True
		self.status, self.closed_by, self.closed_on = "Open", None, None
		self.save(ignore_permissions=True)
		audit.log(self.doctype, self.name, "Reopen", reason)
		clear_request_cache()
