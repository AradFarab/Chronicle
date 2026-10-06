# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _

from hozur.approvals import ApprovableRequest
from hozur.devices.service import employee_punches
from hozur.jalali.dates import to_ascii_digits
from hozur.utils import clean_jdate, set_year_month, today_jalali

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def normalize_time(value: str) -> str | None:
	m = TIME_RE.match(to_ascii_digits((value or "").strip()))
	if not m:
		return None
	h, mi, s = int(m[1]), int(m[2]), int(m[3] or 0)
	if h > 23 or mi > 59 or s > 59:
		return None
	return f"{h:02d}:{mi:02d}:{s:02d}"


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
