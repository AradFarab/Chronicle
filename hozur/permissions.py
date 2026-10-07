"""Row-level visibility (CLAUDE.md rule 8): role plus department subtree.

- System Manager, Hozur Operator and Hozur CEO see everyone.
- A manager sees their direct reports and every employee in the departments they manage
  (or act for as deputy), including all sub-departments.
- Everybody sees their own records.

The same rules apply to every doctype that has an `employee` field (punches, attendance,
requests) through employee_condition / has_employee_permission.
"""

import frappe
from frappe.utils.caching import request_cache

from hozur.utils import today_jalali

ALL_ACCESS_ROLES = {"System Manager", "Hozur Operator", "Hozur CEO", "Administrator"}


def has_all_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(ALL_ACCESS_ROLES & set(frappe.get_roles(user)))


def employee_of(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user": user}, "name")


def managed_departments(employee: str) -> list[str]:
	"""Departments (with all descendants) managed by the employee, or covered as acting deputy today."""
	today = today_jalali()
	roots = frappe.get_all("Department", filters={"manager": employee}, fields=["lft", "rgt"])
	for d in frappe.get_all(
		"Department", filters={"deputy": employee}, fields=["lft", "rgt", "deputy_from", "deputy_to"]
	):
		if (not d.deputy_from or d.deputy_from <= today) and (not d.deputy_to or today <= d.deputy_to):
			roots.append(d)
	names: set[str] = set()
	for root in roots:
		names.update(
			frappe.get_all(
				"Department",
				filters={"lft": [">=", root.lft], "rgt": ["<=", root.rgt]},
				pluck="name",
			)
		)
	return sorted(names)


def visible_employees(user: str | None = None) -> list[str] | None:
	"""Employee names the user may see, or None for unrestricted access."""
	return _visible_employees(user or frappe.session.user)


@request_cache
def _visible_employees(user: str) -> list[str] | None:
	if has_all_access(user):
		return None
	me = employee_of(user)
	if not me:
		return []
	names = {me}
	names.update(frappe.get_all("Employee", filters={"reports_to": me}, pluck="name"))
	departments = managed_departments(me)
	if departments:
		names.update(frappe.get_all("Employee", filters={"department": ["in", departments]}, pluck="name"))
	return sorted(names)


def _in_condition(column: str, names: list[str]) -> str:
	if not names:
		return "1=0"
	return f"{column} in ({', '.join(frappe.db.escape(n) for n in names)})"


def employee_query(user=None, doctype=None):
	names = visible_employees(user)
	return "" if names is None else _in_condition("`tabEmployee`.`name`", names)


def has_employee_doc_permission(doc, ptype=None, user=None, debug=False):
	names = visible_employees(user)
	return True if names is None else doc.name in names


def employee_condition(user=None, doctype=None):
	"""permission_query_conditions for doctypes with an `employee` field."""
	names = visible_employees(user)
	if names is None:
		return ""
	return _in_condition(f"`tab{doctype}`.`employee`", names)


def has_employee_permission(doc, ptype=None, user=None, debug=False):
	names = visible_employees(user)
	return True if names is None else doc.get("employee") in names
