import frappe

from hozur.calendar_sync import install_calendar
from hozur.rule_sets import seed_baseline
from hozur.setup.data import DEFAULT_PROCESSES, LEAVE_TYPES, ROLES, ROOT_DEPARTMENT, STANDARD_PROCESSES


def after_install():
	set_system_defaults()
	ensure_settings()
	ensure_roles()
	ensure_root_department()
	install_calendar()
	ensure_approval_processes()
	seed_baseline()
	ensure_leave_types()


def after_migrate():
	ensure_settings()
	ensure_roles()
	ensure_root_department()
	install_calendar()
	ensure_approval_processes()
	seed_baseline()
	ensure_leave_types()


def ensure_leave_types():
	for name, category, paid, deducts, hourly, rule_limit, once in LEAVE_TYPES:
		if frappe.db.exists("Leave Type", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Leave Type",
				"leave_type_name": name,
				"category": category,
				"is_paid": paid,
				"deducts_from_balance": deducts,
				"allow_hourly": hourly,
				"rule_limit": rule_limit,
				"once_in_service": once,
				"is_standard": 1,
			}
		)
		doc.flags.skip_audit = True
		doc.insert(ignore_permissions=True)


def ensure_approval_processes():
	"""The four standard processes of the design doc, and a default for each request type."""
	for name, steps in STANDARD_PROCESSES.items():
		if frappe.db.exists("Approval Process", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Approval Process",
				"process_name": name,
				"is_standard": 1,
				"steps": [{"approver_type": s} for s in steps],
			}
		)
		doc.flags.skip_audit = True
		doc.insert(ignore_permissions=True)
	settings = frappe.get_single("Hozur Settings")
	changed = False
	for field, process in DEFAULT_PROCESSES.items():
		if not settings.get(field):
			settings.set(field, process)
			changed = True
	if changed:
		settings.flags.ignore_permissions = settings.flags.skip_audit = True
		settings.save()


def ensure_settings():
	"""Save single doctypes once so their field defaults exist in the database."""
	for doctype in ("Hozur Settings",):
		if not frappe.db.exists("Singles", {"doctype": doctype}):
			doc = frappe.get_single(doctype)
			doc.flags.ignore_permissions = doc.flags.skip_audit = True
			doc.save()


def set_system_defaults():
	settings = frappe.get_single("System Settings")
	settings.time_zone = "Asia/Tehran"
	settings.country = settings.country or "Iran"
	settings.flags.ignore_mandatory = True
	settings.save()


def ensure_roles():
	"""Hozur roles work in the PWA; only System Manager uses the Frappe desk (design doc)."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(
				ignore_permissions=True
			)
		elif frappe.db.get_value("Role", role, "desk_access"):
			frappe.db.set_value("Role", role, "desk_access", 0)


def ensure_root_department():
	if frappe.db.exists("Department", ROOT_DEPARTMENT):
		return
	doc = frappe.get_doc({"doctype": "Department", "department_name": ROOT_DEPARTMENT, "is_group": 1})
	doc.flags.skip_audit = True
	doc.insert(ignore_permissions=True)
