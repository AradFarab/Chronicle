# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate


class ShiftOverride(Document):
	"""A one-day change of shift (or a day off), set by a manager or an operator."""

	def validate(self):
		clean_jdate(self, "jdate", required=True)
		from hozur.periods import assert_open
		from hozur.permissions import visible_employees

		assert_open(self.jdate)
		allowed = visible_employees()
		if allowed is not None and self.employee not in allowed:
			frappe.throw(
				_("You cannot change the shift of {0}").format(self.employee), frappe.PermissionError
			)
		other = frappe.db.get_value(
			"Shift Override",
			{"employee": self.employee, "jdate": self.jdate, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} already has a shift change on {1} ({2})").format(self.employee, self.jdate, other)
			)

	def on_update(self):
		self._recalculate()

	def on_trash(self):
		from hozur.periods import assert_open

		assert_open(self.jdate)

	def after_delete(self):
		self._recalculate()

	def _recalculate(self):
		from hozur.attendance import schedule_recalculation

		schedule_recalculation([(self.employee, self.jdate)], _("Shift change {0}").format(self.name))
