# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from hozur.approvals import APPROVED, ApprovableRequest
from hozur.attendance import schedule_recalculation
from hozur.devices.service import employee_punches
from hozur.jalali.dates import normalize_time
from hozur.utils import clean_jdate, set_year_month, today_jalali


class AttendanceCorrection(ApprovableRequest):
	"""Manual punch times (اصلاح تردد / ورود دستی ساعت): adds missing punches or ignores wrong
	ones for one employee and one day. Raw punches stay untouched; once approved, the
	calculation uses the corrected set (hozur.punches.effective_punches)."""

	request_type = "Attendance Correction"

	def validate(self):
		clean_jdate(self, "jdate", required=True)
		set_year_month(self)
		if self.jdate > today_jalali():
			frappe.throw(_("A correction cannot be for a future day"))
		if not (self.reason or "").strip():
			frappe.throw(_("Enter the reason for the correction"))
		if not self.items:
			frappe.throw(_("Add at least one time"))
		day_punches = None
		seen = set()
		for item in self.items:
			if item.action == "Add Punch":
				item.raw_punch = None
				item.time = normalize_time(item.time)
				if not item.time:
					frappe.throw(_("Row {0}: enter the time as HH:MM").format(item.idx))
				key = ("add", item.time)
			else:
				item.time = item.direction = None
				if day_punches is None:
					day_punches = {p.name for p in employee_punches(self.employee, self.jdate, self.jdate)}
				if item.raw_punch not in day_punches:
					frappe.throw(
						_("Row {0}: punch {1} is not a punch of this employee on {2}").format(
							item.idx, item.raw_punch, self.jdate
						)
					)
				key = ("ignore", item.raw_punch)
			if key in seen:
				frappe.throw(_("Row {0} repeats an earlier row").format(item.idx))
			seen.add(key)

	def affected_range(self):
		return self.jdate, self.jdate

	def on_approved(self):
		schedule_recalculation(
			[(self.employee, self.jdate)], _("Attendance correction {0}").format(self.name)
		)

	def on_cancelled(self, previous_status):
		if previous_status == APPROVED:
			schedule_recalculation(
				[(self.employee, self.jdate)], _("Attendance correction {0} cancelled").format(self.name)
			)
