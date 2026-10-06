# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.calendar_sync import refresh_days
from hozur.jalali import holidays as jhol
from hozur.utils import clean_jdate, set_year_month

OFFICIAL_SCOPES = ("Country", "Province")
COMPANY_SCOPES = ("Company", "Branch")


class IranHoliday(Document):
	def validate(self):
		clean_jdate(self, "jdate", required=True)
		set_year_month(self)
		self.validate_scope()
		if self.holiday_type != jhol.OFFICE_CLOSURE:
			self.closure_pay_mode = None
		if self.scope != "Province":
			self.province = None
		if self.scope != "Branch":
			self.branch = None
		if not self.is_new() and not self.flags.from_seed and self.has_value_changed_any():
			self.edited_by_operator = 1

	def has_value_changed_any(self):
		return any(
			self.has_value_changed(f)
			for f in (
				"jdate",
				"title",
				"holiday_type",
				"status",
				"scope",
				"province",
				"branch",
				"closure_pay_mode",
			)
		)

	def validate_scope(self):
		if self.holiday_type == jhol.COMPANY_INTERNAL and self.scope not in COMPANY_SCOPES:
			frappe.throw(_("A company internal holiday applies to the whole company or one branch"))
		if self.holiday_type in (jhol.OFFICIAL_SOLAR, jhol.OFFICIAL_LUNAR) and self.scope != "Country":
			frappe.throw(_("Official solar and lunar holidays apply to the whole country"))
		if self.holiday_type == jhol.OFFICIAL_OCCASIONAL and self.scope not in OFFICIAL_SCOPES:
			frappe.throw(_("A government-declared holiday applies to the whole country or one province"))
		if self.holiday_type == jhol.OFFICE_CLOSURE and not self.closure_pay_mode:
			frappe.throw(_("Choose how the office closure is paid"))

	def on_update(self):
		before = self.get_doc_before_save()
		refresh_days([self.jdate, before.jdate if before else None])

	def on_trash(self):
		self.flags.deleted_jdate = self.jdate

	def after_delete(self):
		refresh_days([self.flags.deleted_jdate])
