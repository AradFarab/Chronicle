# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.jalali.dates import to_ascii_digits
from hozur.utils import clean_jdate, validate_date_order


class DeviceUserMap(Document):
	def validate(self):
		self.device_user_id = to_ascii_digits((self.device_user_id or "").strip())
		clean_jdate(self, "valid_from")
		clean_jdate(self, "valid_to")
		validate_date_order(self, "valid_from", "valid_to")
		self.validate_overlap()

	def validate_overlap(self):
		"""One device user id may belong to only one person on any given day."""
		lo, hi = self.valid_from or "0000/00/00", self.valid_to or "9999/99/99"
		for other in frappe.get_all(
			"Device User Map",
			filters={"device": self.device, "device_user_id": self.device_user_id, "name": ["!=", self.name]},
			fields=["name", "employee", "valid_from", "valid_to"],
		):
			o_lo, o_hi = other.valid_from or "0000/00/00", other.valid_to or "9999/99/99"
			if lo <= o_hi and o_lo <= hi:
				frappe.throw(
					_("Device user {0} on {1} is already mapped for an overlapping period ({2})").format(
						self.device_user_id, self.device, other.name
					)
				)
