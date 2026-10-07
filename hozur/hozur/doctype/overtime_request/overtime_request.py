# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from hozur.approvals import APPROVED, PENDING, ApprovableRequest, is_operator
from hozur.attendance import schedule_recalculation
from hozur.permissions import employee_of, visible_employees
from hozur.schedule import time_to_minutes
from hozur.utils import clean_jdate

EMPLOYEE_ACCEPTANCE = "Employee Acceptance"


class OvertimeRequest(ApprovableRequest):
	"""Overtime needs the worker's consent (Article 59). When a manager assigns it, the first
	step is the employee's acceptance; the assigning manager's own steps count as approved."""

	request_type = "Overtime"

	def validate(self):
		clean_jdate(self, "jdate", required=True)
		start, end = time_to_minutes(self.from_time), time_to_minutes(self.to_time)
		if start is not None and end is not None:
			self.minutes = (end - start) % 1440
		if not self.minutes or self.minutes <= 0:
			frappe.throw(_("Enter the overtime minutes"))
		if self.overtime_kind != "Normal" and not (self.reason or "").strip():
			frappe.throw(_("Enter the reason for {0} overtime").format(_(self.overtime_kind)))

	def validate_requester(self):
		me = employee_of()
		if me == self.employee:
			self.assigned_by_manager = 0
			self.entered_by_operator = 0
			return
		if is_operator():
			self.entered_by_operator = 1
			self.assigned_by_manager = 0
			return
		allowed = visible_employees()
		if allowed is not None and self.employee not in allowed:
			frappe.throw(_("You can only assign overtime to your own team"), frappe.PermissionError)
		self.assigned_by_manager = 1
		self.entered_by_operator = 0

	def build_approval_steps(self):
		super().build_approval_steps()
		if not self.assigned_by_manager:
			return
		assigner = employee_of()
		for row in self.approvals:
			if row.approver == assigner and row.status == PENDING:
				row.update(
					{
						"status": APPROVED,
						"acted_by": frappe.session.user,
						"comment": _("Assigned the overtime"),
					}
				)
		acceptance = {
			"step": 0,
			"approver_type": EMPLOYEE_ACCEPTANCE,
			"approver": self.employee,
			"approver_user": frappe.db.get_value("Employee", self.employee, "user"),
			"status": PENDING,
		}
		fields = (
			"step",
			"approver_type",
			"approver",
			"approver_user",
			"status",
			"acted_by",
			"acted_on",
			"comment",
		)
		self.set("approvals", [acceptance] + [{f: row.get(f) for f in fields} for row in self.approvals])
		self.status = PENDING
		self.advance(None)

	def affected_range(self):
		return self.jdate, self.jdate

	def on_approved(self):
		schedule_recalculation([(self.employee, self.jdate)], _("Overtime {0} approved").format(self.name))

	def on_cancelled(self, previous_status):
		if previous_status == APPROVED:
			schedule_recalculation(
				[(self.employee, self.jdate)], _("Overtime {0} cancelled").format(self.name)
			)
