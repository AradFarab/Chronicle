"""Build report rows from Daily Attendance. Reports always come from the calculated days, so
every number matches the app. Visibility rules apply: a manager only gets their department."""

from __future__ import annotations

from collections import OrderedDict

import frappe
from frappe import _

from hozur.jalali.dates import iter_days, normalize_jdate
from hozur.reports import catalog
from hozur.reports.catalog import COUNT, DAILY, DAYS, LEAVE_PREFIX, MINUTES, SUMMARY

GROUPS = ("", "Employee", "Department", "Day")
NUMERIC = (MINUTES, DAYS, COUNT)


def leave_types() -> set[str]:
	return set(frappe.get_all("Leave Type", pluck="name"))


def department_subtree(department: str) -> list[str]:
	lft, rgt = frappe.db.get_value("Department", department, ["lft", "rgt"])
	return frappe.get_all("Department", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")


def validate_spec(spec: dict) -> dict:
	source = spec.get("source") or SUMMARY
	if source not in (DAILY, SUMMARY):
		frappe.throw(_("Unknown report source"))
	if (spec.get("group_by") or "") not in GROUPS:
		frappe.throw(_("Unknown grouping"))
	types = leave_types()
	columns = []
	for col in spec.get("columns") or []:
		try:
			field = catalog.resolve(col["field"], source, types)
		except ValueError as e:
			frappe.throw(_("Report field not allowed: {0}").format(str(e)))
		columns.append(
			{
				"key": field.key,
				"label": col.get("label") or _(field.label),
				"kind": field.kind,
				"width": col.get("width"),
			}
		)
	if not columns:
		frappe.throw(_("Choose at least one column"))
	return {**spec, "source": source, "columns": columns}


def _filters(filters: dict, user: str | None) -> dict:
	from hozur.permissions import visible_employees

	start = normalize_jdate(filters["from_date"])
	end = normalize_jdate(filters["to_date"])
	if end < start:
		frappe.throw(_("The end date is before the start date"))
	db_filters = {"jdate": ["between", [start, end]]}
	for field in ("branch", "designation", "employee"):
		if filters.get(field):
			db_filters[field] = filters[field]
	if filters.get("department"):
		db_filters["department"] = ["in", department_subtree(filters["department"])]
	allowed = visible_employees(user)
	if allowed is not None:
		if filters.get("employee") and filters["employee"] not in allowed:
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		db_filters.setdefault("employee", ["in", allowed or [""]])
	return db_filters


DA_COLUMNS = (
	"name",
	"employee",
	"employee_name",
	"branch",
	"department",
	"designation",
	"jdate",
	"weekday_name",
	"status",
	"day_type",
	"holiday_title",
	"shift",
	"first_in",
	"last_out",
	"warnings",
	"required_minutes",
	"worked_minutes",
	"credited_minutes",
	"late_minutes",
	"early_leave_minutes",
	"absence_minutes",
	"absent_day",
	"overtime_normal_minutes",
	"overtime_exceptional_minutes",
	"overtime_emergency_minutes",
	"unapproved_extra_minutes",
	"night_work_minutes",
	"rest_day_work_minutes",
	"friday_premium_minutes",
	"holiday_work_minutes",
	"company_holiday_work_minutes",
	"leave_days",
	"leave_minutes",
	"mission_minutes",
	"nursing_minutes",
)


def _day_rows(db_filters: dict) -> list[dict]:
	rows = frappe.get_all(
		"Daily Attendance", filters=db_filters, fields=list(DA_COLUMNS), order_by="employee, jdate"
	)
	leaves = {}
	if rows:
		for r in frappe.get_all(
			"Daily Attendance Leave",
			filters={"parenttype": "Daily Attendance", "parent": ["in", [r.name for r in rows]]},
			fields=["parent", "leave_type", "days"],
		):
			leaves.setdefault(r.parent, {})[r.leave_type] = r.days
	unpaid = set(frappe.get_all("Leave Type", filters={"is_paid": 0}, pluck="name"))
	out = []
	for r in rows:
		row = dict(r)
		row["absent_days"] = int(r.absent_day)
		row["mission_days"] = int(r.status == "Mission")
		row["overtime_total_minutes"] = (
			r.overtime_normal_minutes + r.overtime_exceptional_minutes + r.overtime_emergency_minutes
		)
		day_leaves = leaves.get(r.name, {})
		for leave_type, days in day_leaves.items():
			row[LEAVE_PREFIX + leave_type] = days
		row["_unpaid_leave_days"] = sum(d for t, d in day_leaves.items() if t in unpaid)
		out.append(row)
	return out


def _sum_rows(rows: list[dict], columns: list[dict], key_of, first_fields) -> list[dict]:
	groups: OrderedDict = OrderedDict()
	for r in rows:
		groups.setdefault(key_of(r), []).append(r)
	out = []
	for _key, members in groups.items():
		row = {f: members[0].get(f) for f in first_fields}
		for c in columns:
			if c["kind"] in NUMERIC:
				row[c["key"]] = sum(m.get(c["key"]) or 0 for m in members)
		row["_members"] = members
		out.append(row)
	return out


def _summary_extras(row: dict, members: list[dict], start: str, end: str) -> None:
	from hozur.leave import balance, earned_leave_type

	emp = frappe.db.get_value(
		"Employee", row["employee"], ["start_date", "end_date", "national_id"], as_dict=True
	)
	lo = max(start, emp.start_date) if emp.start_date else start
	hi = min(end, emp.end_date) if emp.end_date else end
	employed = len(list(iter_days(lo, hi))) if lo <= hi else 0
	row["national_id"] = emp.national_id
	row["employed_days"] = employed
	row["present_days"] = sum(1 for m in members if m["status"] in ("Present", "Incomplete"))
	row["holiday_days"] = sum(1 for m in members if m["status"] == "Holiday")
	row["rest_days"] = sum(1 for m in members if m["status"] == "Rest Day")
	absent = sum(m["absent_days"] for m in members)
	unpaid = sum(m["_unpaid_leave_days"] for m in members)
	# Paid days: employed days minus unexcused absence and leave the employer does not pay.
	row["paid_days"] = round(max(0, employed - absent - unpaid), 4)
	leave_type = earned_leave_type()
	row["leave_balance"] = balance(row["employee"], leave_type, upto=end) if leave_type else 0


def build(spec: dict, filters: dict, user: str | None = None) -> dict:
	"""-> {"columns": [...], "rows": [...]} with raw values (minutes as ints)."""
	spec = validate_spec(spec)
	columns = spec["columns"]
	db_filters = _filters(filters, user)
	start, end = db_filters["jdate"][1]
	rows = _day_rows(db_filters)
	identity = ("employee", "employee_name", "branch", "department", "designation")
	if spec["source"] == SUMMARY:
		rows = _sum_rows(rows, columns, lambda r: r["employee"], identity)
		for r in rows:
			_summary_extras(r, r["_members"], start, end)
	elif spec.get("group_by") == "Employee":
		rows = _sum_rows(rows, columns, lambda r: r["employee"], identity)
	elif spec.get("group_by") == "Department":
		rows = _sum_rows(rows, columns, lambda r: r["department"], ("department", "branch"))
	elif spec.get("group_by") == "Day":
		rows = _sum_rows(
			rows, columns, lambda r: r["jdate"], ("jdate", "weekday_name", "day_type", "holiday_title")
		)
	else:
		for r in rows:
			r["national_id"] = None
		ids = {r["employee"] for r in rows}
		if ids and any(c["key"] == "national_id" for c in columns):
			national = dict(
				frappe.get_all(
					"Employee",
					filters={"name": ["in", list(ids)]},
					fields=["name", "national_id"],
					as_list=True,
				)
			)
			for r in rows:
				r["national_id"] = national.get(r["employee"])
	return {
		"columns": columns,
		"rows": [{c["key"]: r.get(c["key"]) for c in columns} for r in rows],
		"from_date": start,
		"to_date": end,
	}
