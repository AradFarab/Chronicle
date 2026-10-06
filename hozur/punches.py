"""The punches the calculation uses: device punches plus approved manual corrections."""

from __future__ import annotations

import frappe

from hozur.devices.service import employee_punches


def effective_punches(employee: str, start: str, end: str | None = None) -> list[dict]:
	"""Punches of an employee from start to end (Jalali, inclusive), ordered by day and time:
	raw device/file punches that are not flagged duplicate and not ignored by an approved
	correction, plus the times added by approved corrections. Each item has jdate, time,
	direction, source ('Device', 'File Import' or 'Manual') and ref (document name)."""
	end = end or start
	corrections = frappe.get_all(
		"Attendance Correction",
		filters={
			"employee": employee,
			"jdate": ["between", [start, end]],
			"docstatus": 1,
			"status": "Approved",
		},
		pluck="name",
	)
	items = (
		frappe.get_all(
			"Attendance Correction Item",
			filters={"parent": ["in", corrections], "parenttype": "Attendance Correction"},
			fields=["parent", "action", "time", "direction", "raw_punch"],
		)
		if corrections
		else []
	)
	ignored = {i.raw_punch for i in items if i.action == "Ignore Punch"}
	result = [
		{"jdate": p.jdate, "time": p.time, "direction": p.direction, "source": p.source, "ref": p.name}
		for p in employee_punches(employee, start, end)
		if not p.is_duplicate and p.name not in ignored
	]
	day_of = (
		dict(
			frappe.get_all(
				"Attendance Correction",
				filters={"name": ["in", corrections]},
				fields=["name", "jdate"],
				as_list=True,
			)
		)
		if corrections
		else {}
	)
	result += [
		{
			"jdate": day_of[i.parent],
			"time": i.time,
			"direction": i.direction or "Unknown",
			"source": "Manual",
			"ref": i.parent,
		}
		for i in items
		if i.action == "Add Punch"
	]
	result.sort(key=lambda p: (p["jdate"], p["time"]))
	return result
