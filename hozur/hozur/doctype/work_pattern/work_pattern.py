# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate


class WorkPattern(Document):
	def validate(self):
		if self.pattern_type == "Weekly":
			self.cycle_start_date = None
			seen = set()
			for row in self.days:
				row.cycle_day = 0
				if not row.weekday:
					frappe.throw(_("Row {0}: choose the weekday").format(row.idx))
				if row.weekday in seen:
					frappe.throw(_("{0} appears twice").format(_(row.weekday)))
				seen.add(row.weekday)
			if self.weekly_rest_day and any(r.weekday == self.weekly_rest_day and r.shift for r in self.days):
				frappe.throw(_("The weekly rest day cannot have a shift"))
			week = [self._minutes(r.shift) for r in self.days]
		else:
			clean_jdate(self, "cycle_start_date", required=True)
			self.weekly_rest_day = None
			for i, row in enumerate(sorted(self.days, key=lambda r: r.cycle_day or 0), start=1):
				row.weekday = None
				if row.cycle_day != i:
					frappe.throw(_("Cycle days must be numbered 1, 2, 3... without gaps"))
			cycle = [self._minutes(r.shift) for r in self.days]
			week = [sum(cycle) * 7 / len(cycle)] if cycle else [0]
		self.weekly_minutes = int(sum(week))
		self.warn_weekly_limit()

	def _minutes(self, shift):
		return frappe.db.get_value("Shift", shift, "scheduled_minutes") if shift else 0

	def warn_weekly_limit(self):
		from hozur.rule_sets import get_rule_set
		from hozur.utils import today_jalali

		_name, rules = get_rule_set(today_jalali())
		if self.weekly_minutes > rules.max_weekly_minutes:
			frappe.msgprint(
				_(
					"This pattern has {0} minutes of work a week, more than the weekly limit of {1} (Article 51)."
				).format(self.weekly_minutes, rules.max_weekly_minutes),
				indicator="orange",
				alert=True,
			)

	def on_update(self):
		if self.flags.in_insert:
			return
		_recalculate_pattern_users(self.name, _("Work pattern {0} changed").format(self.name))


def _recalculate_pattern_users(pattern: str, reason: str):
	from hozur.attendance import recalculate_everyone
	from hozur.utils import today_jalali

	if frappe.db.exists("Work Pattern Assignment", {"work_pattern": pattern}):
		today = today_jalali()
		recalculate_everyone(today[:7] + "/01", today, reason)
