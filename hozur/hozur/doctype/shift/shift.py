# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.schedule import time_to_minutes


class Shift(Document):
	def validate(self):
		start, end = time_to_minutes(self.start_time), time_to_minutes(self.end_time)
		if start == end:
			frappe.throw(_("Start and end cannot be the same"))
		self.crosses_midnight = int(end < start)
		if end < start:
			end += 1440
		if self.shift_type == "Flexible":
			latest = time_to_minutes(self.latest_start_time)
			if latest is None or not (start <= latest < end):
				frappe.throw(_("The latest start must be inside the shift"))
			if not self.required_minutes or self.required_minutes <= 0:
				frappe.throw(_("Enter the required work minutes"))
			self.scheduled_minutes = self.required_minutes
		else:
			self.latest_start_time = None
			self.required_minutes = 0
			brk = 0
			b_start, b_end = time_to_minutes(self.break_start_time), time_to_minutes(self.break_end_time)
			if (b_start is None) != (b_end is None):
				frappe.throw(_("Enter both the start and the end of the break"))
			if b_start is not None:
				if b_start < start:
					b_start += 1440
				if b_end <= b_start:
					b_end += 1440
				if not (start <= b_start and b_end <= end):
					frappe.throw(_("The break must be inside the shift"))
				brk = b_end - b_start
			self.scheduled_minutes = end - start - brk
		for field in ("grace_late_minutes", "grace_early_minutes", "overtime_after_minutes", "break_minutes"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(_(self.meta.get_label(field))))
		from hozur.rule_sets import get_rule_set
		from hozur.utils import today_jalali

		_name, rules = get_rule_set(today_jalali())
		if self.scheduled_minutes > rules.max_daily_minutes:
			frappe.msgprint(
				_(
					"This shift has {0} minutes of work, more than the daily limit of {1} (Article 51)."
				).format(self.scheduled_minutes, rules.max_daily_minutes),
				indicator="orange",
				alert=True,
			)
