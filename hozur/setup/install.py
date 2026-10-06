import frappe

from hozur.calendar_sync import install_calendar
from hozur.setup.data import DEFAULT_PROCESSES, ROLES, ROOT_DEPARTMENT, STANDARD_PROCESSES


def after_install():
	set_system_defaults()
	ensure_settings()
	ensure_roles()
	ensure_root_department()
	install_calendar()
	ensure_approval_processes()


def after_migrate():
	ensure_settings()
	ensure_roles()
	ensure_root_department()
	install_calendar()
	ensure_approval_processes()


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
