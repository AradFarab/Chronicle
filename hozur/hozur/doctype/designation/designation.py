# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.utils import clean_jdate


class Designation(Document):
	def validate(self):
		if self.hard_and_harmful:
			if not self.committee_ruling_no:
				frappe.throw(_("A hard-and-harmful designation needs the committee ruling number"))
			clean_jdate(self, "committee_ruling_date", required=True)
		else:
			self.committee_ruling_no = self.committee_ruling_date = None
