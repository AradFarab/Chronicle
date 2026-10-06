# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.approvals import SPECIFIC


class ApprovalProcess(Document):
	def validate(self):
		for step in self.steps:
			if step.approver_type == SPECIFIC and not step.approver:
				frappe.throw(_("Step {0}: choose the person who approves").format(step.idx))
			if step.approver_type != SPECIFIC:
				step.approver = None

	def on_trash(self):
		from hozur.approvals import SETTINGS_FIELD

		for field in [*SETTINGS_FIELD.values(), "operator_entry_process"]:
			if frappe.db.get_single_value("Hozur Settings", field) == self.name:
				frappe.throw(_("{0} is a default process in Hozur Settings").format(self.name))
