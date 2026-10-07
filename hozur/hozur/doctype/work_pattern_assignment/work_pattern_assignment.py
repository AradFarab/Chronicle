# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate, validate_date_order

TARGET_FIELD = {
	"Employee": "employee",
	"Designation": "designation",
	"Department": "department",
	"Company": None,
}


class WorkPatternAssignment(Document):
	def validate(self):
		clean_jdate(self, "valid_from", required=True)
		clean_jdate(self, "valid_to")
		validate_date_order(self, "valid_from", "valid_to")
		target = TARGET_FIELD[self.assign_to]
		for field in ("employee", "designation", "department"):
			if field != target:
				self.set(field, None)
		if target and not self.get(target):
			frappe.throw(_("Choose the {0}").format(_(self.assign_to)))
		from hozur.periods import assert_open

		assert_open(self.valid_from)
		self.validate_overlap(target)

	def validate_overlap(self, target):
		filters = {"assign_to": self.assign_to, "name": ["!=", self.name]}
		if target:
			filters[target] = self.get(target)
		lo, hi = self.valid_from, self.valid_to or "9999/99/99"
		for other in frappe.get_all(
			"Work Pattern Assignment", filters=filters, fields=["name", "valid_from", "valid_to"]
		):
			if lo <= (other.valid_to or "9999/99/99") and other.valid_from <= hi:
				frappe.throw(_("Overlaps assignment {0}. End that one first.").format(other.name))

	def on_update(self):
		self.recalculate()

	def on_trash(self):
		self.recalculate()

	def recalculate(self):
		from hozur.attendance import recalculate_everyone, schedule_recalculation
		from hozur.utils import today_jalali

		reason = _("Work pattern assignment {0}").format(self.name)
		today = today_jalali()
		if self.assign_to == "Employee":
			from hozur.jalali.dates import iter_days

			end = min(self.valid_to or today, today)
			if self.valid_from <= end:
				schedule_recalculation([(self.employee, d) for d in iter_days(self.valid_from, end)], reason)
		else:
			recalculate_everyone(self.valid_from, min(self.valid_to or today, today), reason)
