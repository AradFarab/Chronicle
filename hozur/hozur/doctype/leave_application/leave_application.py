# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from hozur.approvals import APPROVED, ApprovableRequest
from hozur.attendance import schedule_recalculation
from hozur.jalali.dates import iter_days
from hozur.leave import add_entry, balance, working_days
from hozur.rule_sets import get_rule_set
from hozur.schedule import time_to_minutes
from hozur.utils import clean_jdate, validate_date_order


class LeaveApplication(ApprovableRequest):
	def get_request_type(self):
		return "Hourly Leave" if self.leave_unit == "Hourly" else "Daily Leave"

	def validate(self):
		leave_type = frappe.get_cached_doc("Leave Type", self.leave_type)
		if self.leave_unit == "Hourly":
			if not leave_type.allow_hourly:
				frappe.throw(_("{0} cannot be taken by the hour").format(self.leave_type))
			clean_jdate(self, "jdate", required=True)
			start, end = time_to_minutes(self.from_time), time_to_minutes(self.to_time)
			if start is None or end is None or end <= start:
				frappe.throw(_("The end time must be after the start time"))
			self.from_date = self.to_date = None
			self.start_jdate = self.end_jdate = self.jdate
			self.total_minutes = end - start
			_name, rules = get_rule_set(self.jdate)
			self.total_days = round(self.total_minutes / rules.hourly_leave_minutes_per_day, 4)  # Article 70
		else:
			clean_jdate(self, "from_date", required=True)
			clean_jdate(self, "to_date", required=True)
			validate_date_order(self, "from_date", "to_date")
			self.jdate = self.from_time = self.to_time = None
			self.start_jdate, self.end_jdate = self.from_date, self.to_date
			self.total_minutes = 0
			self.total_days = len(working_days(self.employee, self.from_date, self.to_date))
			if not self.total_days:
				frappe.throw(_("There is no working day in this leave"))
		self.validate_limits(leave_type)
		self.validate_overlap()

	def validate_limits(self, leave_type):
		_name, rules = get_rule_set(self.start_jdate)
		limit = rules.as_dict().get(leave_type.rule_limit) if leave_type.rule_limit else None
		if leave_type.max_days_per_request:
			limit = min(limit, leave_type.max_days_per_request) if limit else leave_type.max_days_per_request
		calendar_days = len(list(iter_days(self.start_jdate, self.end_jdate)))
		if limit and calendar_days > limit:
			frappe.throw(_("{0} is at most {1} days").format(self.leave_type, limit))
		if leave_type.once_in_service and frappe.db.exists(
			"Leave Application",
			{
				"employee": self.employee,
				"leave_type": self.leave_type,
				"docstatus": 1,
				"status": ["in", ["Pending", "Approved"]],
				"name": ["!=", self.name],
			},
		):
			frappe.throw(_("{0} can be taken only once during employment").format(self.leave_type))

	def validate_overlap(self):
		for other in frappe.get_all(
			"Leave Application",
			filters={
				"employee": self.employee,
				"docstatus": ["<", 2],
				"status": ["not in", ["Rejected", "Cancelled"]],
				"name": ["!=", self.name],
				"start_jdate": ["<=", self.end_jdate],
				"end_jdate": [">=", self.start_jdate],
			},
			fields=["name", "leave_unit", "from_time", "to_time"],
		):
			if self.leave_unit == "Hourly" and other.leave_unit == "Hourly":
				a, b = time_to_minutes(self.from_time), time_to_minutes(self.to_time)
				c, d = time_to_minutes(other.from_time), time_to_minutes(other.to_time)
				if b <= c or d <= a:
					continue
			frappe.throw(_("Overlaps leave application {0}").format(other.name))

	def before_submit(self):
		super().before_submit()
		leave_type = frappe.get_cached_doc("Leave Type", self.leave_type)
		allow_negative = frappe.db.get_single_value("Hozur Settings", "allow_negative_leave_balance")
		if leave_type.deducts_from_balance and not allow_negative:
			available = balance(self.employee, self.leave_type)
			if available < self.total_days:
				frappe.throw(
					_("Not enough leave: {0} days available, {1} requested").format(
						available, self.total_days
					)
				)

	def affected_range(self):
		return self.start_jdate, self.end_jdate

	def _days(self):
		return [(self.employee, d) for d in iter_days(self.start_jdate, self.end_jdate)]

	def on_approved(self):
		if frappe.get_cached_value("Leave Type", self.leave_type, "deducts_from_balance"):
			add_entry(self.employee, self.leave_type, "Usage", self.start_jdate, -self.total_days, self)
		schedule_recalculation(self._days(), _("Leave {0} approved").format(self.name))

	def on_cancelled(self, previous_status):
		if previous_status != APPROVED:
			return
		if frappe.get_cached_value("Leave Type", self.leave_type, "deducts_from_balance"):
			add_entry(self.employee, self.leave_type, "Reversal", self.start_jdate, self.total_days, self)
		schedule_recalculation(self._days(), _("Leave {0} cancelled").format(self.name))
