# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.devices.file_import import ZKTECO_USB


class PunchImportTemplate(Document):
	def validate(self):
		if self.file_format == ZKTECO_USB:
			return
		if not self.user_id_column:
			frappe.throw(_("Enter the user id column"))
		if not self.datetime_column and not (self.date_column and self.time_column):
			frappe.throw(_("Enter either the date-time column or both the date and time columns"))
		if self.date_calendar == "Jalali" and self.date_format != "YYYY/MM/DD":
			self.date_format = "YYYY/MM/DD"
