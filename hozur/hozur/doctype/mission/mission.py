# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from hozur.approvals import APPROVED, ApprovableRequest
from hozur.attendance import schedule_recalculation
from hozur.jalali.dates import iter_days
from hozur.schedule import time_to_minutes
from hozur.utils import clean_jdate, validate_date_order


class Mission(ApprovableRequest):
	"""A mission counts as full work time (no detailed rule in the Labor Law)."""

	request_type = "Mission"

	def validate(self):
		if self.mission_unit == "Hourly":
			clean_jdate(self, "jdate", required=True)
			start, end = time_to_minutes(self.from_time), time_to_minutes(self.to_time)
			if start is None or end is None or end <= start:
				frappe.throw(_("The end time must be after the start time"))
			self.from_date = self.to_date = None
			self.start_jdate = self.end_jdate = self.jdate
		else:
			clean_jdate(self, "from_date", required=True)
			clean_jdate(self, "to_date", required=True)
			validate_date_order(self, "from_date", "to_date")
			self.jdate = self.from_time = self.to_time = None
			self.start_jdate, self.end_jdate = self.from_date, self.to_date

	def affected_range(self):
		return self.start_jdate, self.end_jdate

	def _days(self):
		return [(self.employee, d) for d in iter_days(self.start_jdate, self.end_jdate)]

	def on_approved(self):
		schedule_recalculation(self._days(), _("Mission {0} approved").format(self.name))

	def on_cancelled(self, previous_status):
		if previous_status == APPROVED:
			schedule_recalculation(self._days(), _("Mission {0} cancelled").format(self.name))
