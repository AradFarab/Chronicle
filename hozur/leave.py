"""Leave balances. Like a ledger: a balance is never edited, it is the sum of its entries
(allocation, usage, reversal, expiry, manual adjustment), the same logic as Frappe HR."""

from __future__ import annotations

import frappe
from frappe import _

from hozur.engine.periodic import annual_leave_entitlement, year_end_carry_over
from hozur.jalali.calendar import resolve_day_type
from hozur.jalali.dates import iter_days, month_bounds, year_bounds
from hozur.rule_sets import get_rule_set
from hozur.schedule import resolve


def earned_leave_type() -> str | None:
	return frappe.db.get_value("Leave Type", {"category": "Earned", "deducts_from_balance": 1}, "name")


def balance(employee: str, leave_type: str, upto: str | None = None) -> float:
	filters = {"employee": employee, "leave_type": leave_type}
	if upto:
		filters["jdate"] = ["<=", upto]
	return round(sum(frappe.get_all("Leave Ledger Entry", filters=filters, pluck="days")), 4)


def add_entry(employee, leave_type, entry_type, jdate, days, reference=None, note=None):
	doc = frappe.get_doc(
		{
			"doctype": "Leave Ledger Entry",
			"employee": employee,
			"leave_type": leave_type,
			"entry_type": entry_type,
			"jdate": jdate,
			"days": round(days, 4),
			"reference_doctype": reference.doctype if reference else None,
			"reference_name": reference.name if reference else None,
			"note": note,
		}
	)
	doc.flags.from_system = True
	doc.insert(ignore_permissions=True)
	return doc


def working_days(employee: str, start: str, end: str) -> list[str]:
	"""Days of a daily leave that count: scheduled working days only. Official holidays and
	weekly rest days inside a leave are not leave (Article 64)."""
	branch = frappe.db.get_value("Employee", employee, "branch")
	province = frappe.db.get_value("Branch", branch, "province") if branch else None
	days = []
	for jdate in iter_days(start, end):
		calendar_day = frappe.db.get_value("Calendar Day", jdate, ["day_type"], as_dict=True) or {
			"day_type": "Workday"
		}
		holidays = frappe.get_all(
			"Iran Holiday",
			filters={"jdate": jdate},
			fields=["title", "holiday_type", "status", "scope", "province", "branch", "closure_pay_mode"],
		)
		if resolve_day_type(calendar_day, holidays, branch, province)["day_type"] in (
			"Official Holiday",
			"Company Holiday",
		):
			continue
		schedule = resolve(employee, jdate)
		if schedule.shift and not schedule.rest_day:
			days.append(jdate)
	return days


def _employed_days(employee: str, start: str, end: str) -> int:
	emp = frappe.db.get_value("Employee", employee, ["start_date", "end_date", "status"], as_dict=True)
	if not emp.start_date:
		return 0
	lo, hi = max(start, emp.start_date), min(end, emp.end_date) if emp.end_date else end
	return len(list(iter_days(lo, hi))) if lo <= hi else 0


def allocate_month(period: str) -> int:
	"""Accrue earned leave for a finished Jalali month ('1405/07') in proportion to the days
	employed (Articles 64, 65). Idempotent per employee and month."""
	leave_type = earned_leave_type()
	if not leave_type:
		return 0
	year, month = int(period[:4]), int(period[5:7])
	start, end = month_bounds(year, month)
	y_start, y_end = year_bounds(year)
	year_days = len(list(iter_days(y_start, y_end)))
	_name, rules = get_rule_set(end)
	created = 0
	for emp in frappe.get_all(
		"Employee", filters={"status": ["!=", "Suspended"]}, fields=["name", "designation"]
	):
		note = f"accrual {period}"
		if frappe.db.exists(
			"Leave Ledger Entry", {"employee": emp.name, "entry_type": "Allocation", "note": note}
		):
			continue
		days = _employed_days(emp.name, start, end)
		if not days:
			continue
		hard = bool(emp.designation and frappe.db.get_value("Designation", emp.designation, "hard_harmful"))
		amount = annual_leave_entitlement(days, year_days, rules, hard_harmful=hard)
		add_entry(emp.name, leave_type, "Allocation", end, amount, note=note)
		created += 1
	return created


def close_leave_year(year: int) -> int:
	"""Year end (Article 66): up to the carry-over limit stays, the rest expires."""
	leave_type = earned_leave_type()
	if not leave_type:
		return 0
	_start, end = year_bounds(year)
	_name, rules = get_rule_set(end)
	expired_count = 0
	for employee in frappe.get_all("Employee", pluck="name"):
		note = f"year end {year}"
		if frappe.db.exists(
			"Leave Ledger Entry", {"employee": employee, "entry_type": "Expiry", "note": note}
		):
			continue
		_carried, expired = year_end_carry_over(balance(employee, leave_type, upto=end), rules)
		if expired > 0:
			add_entry(employee, leave_type, "Expiry", end, -expired, note=note)
			expired_count += 1
	return expired_count


@frappe.whitelist()
def get_balance(employee: str, leave_type: str | None = None) -> dict:
	from hozur.permissions import visible_employees

	allowed = visible_employees()
	if allowed is not None and employee not in allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	leave_type = leave_type or earned_leave_type()
	return {"leave_type": leave_type, "balance": balance(employee, leave_type) if leave_type else 0}
