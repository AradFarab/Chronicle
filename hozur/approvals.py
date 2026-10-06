"""Data-driven approval (CLAUDE.md rule 6).

An Approval Process is an ordered list of steps; each step is resolved to a person when the
request is submitted: the direct manager, the manager of the parent department, the CEO, or
a specific person. A process with no steps approves on submit. Every request type has a
default process (Hozur Settings) and any employee can have a per-type override (Approval
Override). Requests entered by an operator on someone's behalf can use their own process.
There are no numeric conditions.

The resolved steps are copied onto the request when it is submitted, so changing a process
only affects new requests.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from hozur import audit
from hozur.permissions import employee_of
from hozur.utils import now_jalali, today_jalali

REQUEST_TYPES = ("Daily Leave", "Hourly Leave", "Overtime", "Mission", "Attendance Correction")
SETTINGS_FIELD = {
	"Daily Leave": "daily_leave_process",
	"Hourly Leave": "hourly_leave_process",
	"Overtime": "overtime_process",
	"Mission": "mission_process",
	"Attendance Correction": "correction_process",
}
DIRECT_MANAGER, PARENT_MANAGER, CEO, SPECIFIC = (
	"Direct Manager",
	"Parent Department Manager",
	"CEO",
	"Specific Person",
)
PENDING, APPROVED, REJECTED, SKIPPED = "Pending", "Approved", "Rejected", "Skipped"
OPERATOR_ROLES = ("System Manager", "Hozur Operator")


def get_process(employee: str, request_type: str, entered_by_operator: bool = False) -> str | None:
	override = frappe.db.get_value(
		"Approval Override", {"employee": employee, "request_type": request_type}, "approval_process"
	)
	if override:
		return override
	if entered_by_operator:
		operator_process = frappe.db.get_single_value("Hozur Settings", "operator_entry_process")
		if operator_process:
			return operator_process
	return frappe.db.get_single_value("Hozur Settings", SETTINGS_FIELD[request_type])


def _acting_manager(department: str | None) -> str | None:
	"""Manager of a department, or its deputy while the deputy period covers today."""
	if not department:
		return None
	d = frappe.db.get_value(
		"Department", department, ["manager", "deputy", "deputy_from", "deputy_to"], as_dict=True
	)
	if not d:
		return None
	today = today_jalali()
	if d.deputy and d.deputy_from and (d.deputy_from <= today) and (not d.deputy_to or today <= d.deputy_to):
		return d.deputy
	return d.manager


def _manager_above(employee: str, department: str | None) -> str | None:
	"""Walk up the department tree to the first manager who is not the employee."""
	while department:
		manager = _acting_manager(department)
		if manager and manager != employee:
			return manager
		department = frappe.db.get_value("Department", department, "parent_department")
	return None


def direct_manager(employee: str) -> str | None:
	"""Employee.reports_to, else the department manager; a manager's direct manager is the
	manager of the department above (design doc, approval section)."""
	emp = frappe.db.get_value("Employee", employee, ["reports_to", "department"], as_dict=True)
	if emp.reports_to and emp.reports_to != employee:
		return emp.reports_to
	return _manager_above(employee, emp.department)


def parent_department_manager(employee: str) -> str | None:
	department = frappe.db.get_value("Employee", employee, "department")
	direct = direct_manager(employee)
	parent = frappe.db.get_value("Department", department, "parent_department") if department else None
	manager = _manager_above(employee, parent)
	if manager == direct:
		# The direct manager already runs the parent department: go one level higher.
		parent = frappe.db.get_value("Department", parent, "parent_department") if parent else None
		manager = _manager_above(employee, parent)
	return manager


def resolve_step(step, employee: str) -> str | None:
	if step.approver_type == DIRECT_MANAGER:
		return direct_manager(employee)
	if step.approver_type == PARENT_MANAGER:
		return parent_department_manager(employee)
	if step.approver_type == CEO:
		return frappe.db.get_single_value("Organization", "ceo")
	if step.approver_type == SPECIFIC:
		return step.approver
	frappe.throw(_("Unknown approver type {0}").format(step.approver_type))


def is_operator(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(OPERATOR_ROLES) & set(frappe.get_roles(user)))


class ApprovableRequest(Document):
	"""Base controller for requests. The doctype must be submittable and have the fields
	employee, status, approval_process, entered_by_operator, pending_approver,
	pending_approver_user and the table `approvals` (Request Approval)."""

	request_type: str = ""

	def get_request_type(self) -> str:
		return self.request_type

	# lifecycle -------------------------------------------------------------

	def validate_requester(self):
		"""Employees request for themselves; operators may enter requests for anyone."""
		if is_operator():
			self.entered_by_operator = int(employee_of() != self.employee)
			return
		if employee_of() != self.employee:
			frappe.throw(_("You can only submit requests for yourself"), frappe.PermissionError)
		self.entered_by_operator = 0

	def before_validate(self):
		if self.docstatus == 0:
			self.validate_requester()

	def before_submit(self):
		self.validate_requester()
		self.build_approval_steps()

	def build_approval_steps(self):
		process_name = get_process(self.employee, self.get_request_type(), bool(self.entered_by_operator))
		if not process_name:
			frappe.throw(
				_("No approval process is set for {0}. Set one in Hozur Settings.").format(
					_(self.get_request_type())
				)
			)
		process = frappe.get_doc("Approval Process", process_name)
		self.approval_process = process.name
		self.set("approvals", [])
		requester_user = frappe.db.get_value("Employee", self.employee, "user")
		for step in process.steps:
			approver = resolve_step(step, self.employee)
			if not approver:
				frappe.throw(
					_(
						"No approver found for step {0} ({1}). Set the manager of the department or the CEO."
					).format(step.idx, _(step.approver_type))
				)
			user = frappe.db.get_value("Employee", approver, "user")
			if approver != self.employee and not user:
				frappe.throw(_("Approver {0} has no user account").format(approver))
			self.append(
				"approvals",
				{
					"step": step.idx,
					"approver_type": step.approver_type,
					"approver": approver,
					"approver_user": user,
					# nobody approves their own request
					"status": SKIPPED
					if approver == self.employee or (user and user == requester_user)
					else PENDING,
				},
			)
		self.status = PENDING
		self.advance(None)

	def on_submit(self):
		audit.log(self.doctype, self.name, "Submit", self.get("reason"))
		if self.status == APPROVED:
			self.on_approved()

	def on_cancel(self):
		self.status = "Cancelled"
		self.pending_approver = self.pending_approver_user = None
		self.db_set({"status": "Cancelled", "pending_approver": None, "pending_approver_user": None})
		audit.log(self.doctype, self.name, "Cancel")
		self.on_cancelled()

	# approval actions --------------------------------------------------------

	def current_step(self):
		return next((row for row in self.approvals if row.status == PENDING), None)

	def advance(self, acted_row):
		nxt = self.current_step()
		if nxt:
			self.pending_approver, self.pending_approver_user = nxt.approver, nxt.approver_user
		else:
			self.pending_approver = self.pending_approver_user = None
			self.status = APPROVED

	def can_act(self, user=None) -> bool:
		"""The approver of the current step. A System Manager can act for an approver who is
		unavailable; the audit entry records who really acted."""
		user = user or frappe.session.user
		step = self.current_step()
		return bool(step) and (step.approver_user == user or "System Manager" in frappe.get_roles(user))

	def act(self, action: str, comment: str | None = None):
		if self.docstatus != 1 or self.status != PENDING:
			frappe.throw(_("This request is not waiting for approval"))
		step = self.current_step()
		if not self.can_act():
			frappe.throw(_("This request is waiting for {0}").format(step.approver), frappe.PermissionError)
		self.check_period_open()
		jdate, time = now_jalali()
		step.update(
			{
				"status": APPROVED if action == "Approve" else REJECTED,
				"acted_by": frappe.session.user,
				"acted_on": f"{jdate} {time}",
				"comment": comment,
			}
		)
		if action == "Reject":
			self.status = REJECTED
			self.pending_approver = self.pending_approver_user = None
		else:
			self.advance(step)
		self.save(ignore_permissions=True)
		audit.log(self.doctype, self.name, action, comment, after={"step": step.step, "status": self.status})
		if self.status == APPROVED:
			self.on_approved()

	def check_period_open(self):
		"""Overridden once Attendance Period exists (period lock)."""

	# hooks for concrete requests ---------------------------------------------

	def on_approved(self):
		pass

	def on_cancelled(self):
		pass


@frappe.whitelist()
def act_on_request(doctype: str, name: str, action: str, comment: str | None = None) -> dict:
	if action not in ("Approve", "Reject"):
		frappe.throw(_("Unknown action"))
	doc = frappe.get_doc(doctype, name)
	if not isinstance(doc, ApprovableRequest):
		frappe.throw(_("{0} is not a request").format(doctype))
	doc.act(action, comment)
	return {"status": doc.status, "pending_approver": doc.pending_approver}


@frappe.whitelist()
def my_approvals() -> list[dict]:
	"""Requests waiting for the current user (the approval inbox)."""
	rows = []
	for doctype in request_doctypes():
		rows += frappe.get_all(
			doctype,
			filters={"pending_approver_user": frappe.session.user, "docstatus": 1, "status": PENDING},
			fields=["name", "employee", "employee_name", "modified"],
			ignore_permissions=True,
		)
		for r in rows:
			r.setdefault("doctype", doctype)
	return rows


def request_doctypes() -> list[str]:
	return list(frappe.get_hooks("hozur_request_doctypes") or [])


# permissions: requests are visible to the employee scope and to anyone in their approval chain


def request_query(user=None, doctype=None):
	from hozur.permissions import employee_condition

	user = user or frappe.session.user
	base = employee_condition(user, doctype)
	if not base:
		return ""
	approver = (
		f"`tab{doctype}`.`name` in (select parent from `tabRequest Approval` "
		f"where parenttype = {frappe.db.escape(doctype)} and approver_user = {frappe.db.escape(user)})"
	)
	return f"(({base}) or {approver})"


def has_request_permission(doc, ptype=None, user=None, debug=False):
	from hozur.permissions import has_employee_permission

	user = user or frappe.session.user
	if has_employee_permission(doc, ptype, user):
		return True
	return ptype in ("read", "print") and any(row.approver_user == user for row in doc.get("approvals") or [])
