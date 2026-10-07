"""Endpoints of the PWA at /hozur. Everything goes through the same permission rules as the
desk: an employee only reaches their own data, a manager their department subtree."""

from __future__ import annotations

import frappe
from frappe import _

from hozur.approvals import is_operator, my_approvals, request_doctypes
from hozur.jalali.calendar import resolve_day_type
from hozur.jalali.dates import month_bounds, normalize_jdate
from hozur.permissions import employee_of, visible_employees
from hozur.utils import now_jalali, today_jalali

REQUEST_KINDS = {
	"leave": "Leave Application",
	"mission": "Mission",
	"overtime": "Overtime Request",
	"correction": "Attendance Correction",
}
DEVICE_FIELDS = (
	"device_name",
	"adapter_type",
	"branch",
	"enabled",
	"direction_mode",
	"host",
	"port",
	"comm_key",
	"polling_interval_minutes",
	"timeout_seconds",
	"use_udp",
)


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _employee(employee: str | None = None) -> str:
	"""The employee the request is about: yourself by default, or someone you may see."""
	_require_login()
	me = employee_of()
	employee = employee or me
	if not employee:
		frappe.throw(_("Your user is not linked to an employee"))
	allowed = visible_employees()
	if allowed is not None and employee not in allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return employee


@frappe.whitelist()
def translations() -> dict[str, str]:
	"""This app's messages in the user's language, for the PWA's __() (English source strings)."""
	from frappe.gettext.translate import get_translations_from_mo

	lang = frappe.local.lang or "fa"
	if lang == "en":
		return {}
	return get_translations_from_mo(lang, "hozur") or {}


def get_boot() -> dict:
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	me = employee_of(user)
	employee = (
		frappe.db.get_value(
			"Employee", me, ["name", "full_name", "department", "designation", "branch"], as_dict=True
		)
		if me
		else None
	)
	visible = visible_employees(user)
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"employee": employee,
		"organization": frappe.db.get_single_value("Organization", "organization_name") or "",
		"today": today_jalali(),
		"is_operator": is_operator(user),
		"is_system_manager": "System Manager" in roles,
		"is_ceo": "Hozur CEO" in roles,
		"is_manager": "Hozur Manager" in roles or visible is None or len(visible or []) > 1,
	}


@frappe.whitelist()
def boot() -> dict:
	_require_login()
	return get_boot()


def _attendance(employee: str, jdate: str) -> dict | None:
	from hozur.attendance import attendance_name

	return frappe.db.get_value(
		"Daily Attendance",
		attendance_name(employee, jdate),
		[
			"jdate",
			"status",
			"shift",
			"day_type",
			"holiday_title",
			"first_in",
			"last_out",
			"required_minutes",
			"worked_minutes",
			"credited_minutes",
			"late_minutes",
			"early_leave_minutes",
			"absence_minutes",
			"leave_minutes",
			"mission_minutes",
			"overtime_normal_minutes",
			"unapproved_extra_minutes",
			"warnings",
		],
		as_dict=True,
	)


@frappe.whitelist()
def today(employee: str | None = None) -> dict:
	"""Today's status, recalculated on the spot so it reflects the latest punches."""
	from hozur.attendance import calculate
	from hozur.leave import balance, earned_leave_type
	from hozur.punches import effective_punches

	employee = _employee(employee)
	jdate = today_jalali()
	calculate(employee, jdate)
	leave_type = earned_leave_type()
	return {
		"jdate": jdate,
		"time": now_jalali()[1][:5],
		"attendance": _attendance(employee, jdate),
		"punches": effective_punches(employee, jdate),
		"leave_balance": balance(employee, leave_type) if leave_type else None,
		"pending_approvals": len(my_approvals()),
	}


@frappe.whitelist()
def month(year: int, month: int, employee: str | None = None) -> dict:
	employee = _employee(employee)
	start, end = month_bounds(int(year), int(month))
	attendance = {
		r.jdate: r
		for r in frappe.get_all(
			"Daily Attendance",
			filters={"employee": employee, "jdate": ["between", [start, end]]},
			fields=[
				"jdate",
				"status",
				"first_in",
				"last_out",
				"worked_minutes",
				"late_minutes",
				"absence_minutes",
				"warnings",
			],
		)
	}
	branch = frappe.db.get_value("Employee", employee, "branch")
	province = frappe.db.get_value("Branch", branch, "province") if branch else None
	holidays: dict[str, list] = {}
	for h in frappe.get_all(
		"Iran Holiday",
		filters={"jdate": ["between", [start, end]]},
		fields=[
			"jdate",
			"title",
			"holiday_type",
			"status",
			"scope",
			"province",
			"branch",
			"closure_pay_mode",
		],
	):
		holidays.setdefault(h.jdate, []).append(h)
	days = []
	for cal in frappe.get_all(
		"Calendar Day",
		filters={"jdate": ["between", [start, end]]},
		fields=["jdate", "weekday", "day_type"],
		order_by="jdate",
	):
		info = resolve_day_type(cal, holidays.get(cal.jdate, []), branch, province)
		days.append(
			{
				"jdate": cal.jdate,
				"weekday": cal.weekday,
				"day_type": info["day_type"],
				"holiday": " / ".join(info["titles"]),
				"predicted": info["predicted"],
				"attendance": attendance.get(cal.jdate),
			}
		)
	return {"employee": employee, "days": days}


@frappe.whitelist()
def day(jdate: str, employee: str | None = None) -> dict:
	from hozur.punches import effective_punches

	employee = _employee(employee)
	jdate = normalize_jdate(jdate)
	return {"attendance": _attendance(employee, jdate), "punches": effective_punches(employee, jdate)}


def _summary(doctype: str, r) -> str:
	if doctype == "Leave Application":
		if r.leave_unit == "Hourly":
			return f"{r.leave_type} · {r.jdate} {str(r.from_time)[:5]}–{str(r.to_time)[:5]}"
		return f"{r.leave_type} · {r.from_date} – {r.to_date}"
	if doctype == "Mission":
		return f"{r.destination or ''} · {r.start_jdate}" + (
			f" – {r.end_jdate}" if r.end_jdate != r.start_jdate else ""
		)
	if doctype == "Overtime Request":
		return f"{r.jdate} · {r.minutes} " + _("Minutes")
	return f"{r.jdate}"


SUMMARY_FIELDS = {
	"Leave Application": [
		"leave_type",
		"leave_unit",
		"jdate",
		"from_time",
		"to_time",
		"from_date",
		"to_date",
	],
	"Mission": ["destination", "start_jdate", "end_jdate"],
	"Overtime Request": ["jdate", "minutes"],
	"Attendance Correction": ["jdate"],
}


@frappe.whitelist()
def my_requests(employee: str | None = None, limit: int = 30) -> list[dict]:
	employee = _employee(employee)
	rows = []
	for doctype in request_doctypes():
		for r in frappe.get_all(
			doctype,
			filters={"employee": employee, "docstatus": ["<", 2]},
			fields=["name", "status", "pending_approver", "creation", *SUMMARY_FIELDS[doctype]],
			order_by="creation desc",
			limit=int(limit),
		):
			rows.append(
				{
					"doctype": doctype,
					"kind": _(doctype),
					"name": r.name,
					"status": r.status,
					"status_label": _(r.status),
					"summary": _summary(doctype, r),
					"waiting_for": frappe.db.get_value("Employee", r.pending_approver, "full_name")
					if r.pending_approver
					else None,
					"creation": r.creation,
				}
			)
	rows.sort(key=lambda x: x["creation"], reverse=True)
	for r in rows:
		r.pop("creation")
	return rows[: int(limit)]


@frappe.whitelist()
def submit_request(kind: str, values: dict | str) -> dict:
	"""Create and submit a request from the PWA."""
	_require_login()
	doctype = REQUEST_KINDS.get(kind)
	if not doctype:
		frappe.throw(_("Unknown request type"))
	values = frappe.parse_json(values) if isinstance(values, str) else dict(values)
	values["employee"] = _employee(values.get("employee"))
	for key in (
		"doctype",
		"name",
		"docstatus",
		"status",
		"approvals",
		"approval_process",
		"pending_approver",
		"pending_approver_user",
	):
		values.pop(key, None)
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert()
	doc.submit()
	return {"doctype": doctype, "name": doc.name, "status": doc.status, "status_label": _(doc.status)}


@frappe.whitelist()
def inbox() -> list[dict]:
	_require_login()
	rows = []
	for r in my_approvals():
		doctype = r["doctype"]
		doc = frappe.get_doc(doctype, r["name"])
		rows.append(
			{
				"doctype": doctype,
				"kind": _(doctype),
				"name": r["name"],
				"employee_name": doc.employee_name,
				"summary": _summary(doctype, doc),
				"reason": doc.get("reason"),
				"acceptance": bool(
					doctype == "Overtime Request"
					and doc.assigned_by_manager
					and frappe.db.get_value("Employee", doc.employee, "user") == frappe.session.user
				),
			}
		)
	return rows


@frappe.whitelist()
def leave_types() -> list[dict]:
	_require_login()
	return frappe.get_all("Leave Type", fields=["name", "allow_hourly", "category"], order_by="name")


# devices (operators) -----------------------------------------------------------------------


def _operator():
	if not is_operator():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def devices() -> list[dict]:
	_operator()
	rows = frappe.get_all(
		"Attendance Device",
		fields=[
			"name",
			"adapter_type",
			"branch",
			"enabled",
			"host",
			"port",
			"direction_mode",
			"polling_interval_minutes",
			"last_sync",
			"last_sync_status",
			"last_error",
			"punches_last_sync",
			"model",
			"serial_number",
			"user_count",
			"record_count",
			"clock_drift_seconds",
		],
		order_by="name",
	)
	unmapped = {}
	from hozur.devices.service import unmapped_device_users

	for r in unmapped_device_users():
		unmapped[r.device] = unmapped.get(r.device, 0) + 1
	for r in rows:
		r["unmapped_users"] = unmapped.get(r.name, 0)
	return rows


@frappe.whitelist()
def save_device(values: dict | str) -> dict:
	"""Create or update a device from the PWA form (no code involved, CLAUDE.md rule 5)."""
	_operator()
	values = frappe.parse_json(values) if isinstance(values, str) else dict(values)
	clean = {k: values.get(k) for k in DEVICE_FIELDS if k in values}
	name = values.get("name")
	if name and frappe.db.exists("Attendance Device", name):
		doc = frappe.get_doc("Attendance Device", name)
		if clean.get("comm_key") in (None, "", "*****"):
			clean.pop("comm_key", None)  # keep the stored password
		clean.pop("device_name", None)
		doc.update(clean)
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": "Attendance Device", **clean})
		doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def device_options() -> dict:
	"""Choices for the device form: adapter types, direction modes, branches, import templates."""
	_operator()
	meta = frappe.get_meta("Attendance Device")

	def options(fieldname):
		return [{"value": o, "label": _(o)} for o in meta.get_options(fieldname).split("\n") if o]

	return {
		"adapter_types": options("adapter_type"),
		"direction_modes": options("direction_mode"),
		"branches": frappe.get_all("Branch", pluck="name", order_by="name"),
		"import_templates": frappe.get_all("Punch Import Template", pluck="name", order_by="name"),
	}


@frappe.whitelist()
def device(name: str) -> dict:
	"""A device for the PWA form. The communication key is never sent back, only whether it is set."""
	_operator()
	doc = frappe.get_doc("Attendance Device", name)
	doc.check_permission("read")
	values = {k: doc.get(k) for k in DEVICE_FIELDS if k != "comm_key"}
	values["name"] = doc.name
	values["comm_key"] = "*****" if doc.get_password("comm_key", raise_exception=False) else ""
	return values


@frappe.whitelist()
def import_punches(device: str, template: str, file_url: str) -> dict:
	"""Import a punch file uploaded from the PWA (USB export, Excel or CSV) for a device."""
	_operator()
	doc = frappe.get_doc(
		{"doctype": "Punch Import", "device": device, "template": template, "file": file_url}
	).insert()
	stats = doc.run_import()
	doc.reload()
	return {
		"name": doc.name,
		"total_rows": doc.total_rows,
		"created": stats["created"],
		"existing": stats["existing"],
		"duplicates": stats["duplicates"],
		"errors": doc.error_count,
		"error_log": (doc.error_log or "")[:2000],
	}


@frappe.whitelist()
def device_users(device: str) -> list[dict]:
	_operator()
	return frappe.get_all(
		"Device User Map",
		filters={"device": device},
		fields=[
			"name",
			"device_user_id",
			"device_user_name",
			"employee",
			"employee_name",
			"valid_from",
			"valid_to",
		],
		order_by="device_user_id",
	)


@frappe.whitelist()
def map_device_user(name: str, employee: str | None) -> dict:
	_operator()
	doc = frappe.get_doc("Device User Map", name)
	doc.employee = employee or None
	doc.save()
	return {"name": doc.name, "employee": doc.employee, "employee_name": doc.employee_name}


@frappe.whitelist()
def employees(search: str = "", limit: int = 20) -> list[dict]:
	_require_login()
	filters = {"status": ["!=", "Left"]}
	allowed = visible_employees()
	if allowed is not None:
		filters["name"] = ["in", allowed or [""]]
	or_filters = {"full_name": ["like", f"%{search}%"], "name": ["like", f"%{search}%"]} if search else None
	return frappe.get_all(
		"Employee",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name"],
		limit=min(int(limit), 1000),
		order_by="full_name",
	)


# service worker ------------------------------------------------------------------------------

SERVICE_WORKER = """
// hozur PWA service worker: cache the app shell assets, keep data always fresh.
const CACHE = "hozur-v1";
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => {
	e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
	const url = new URL(event.request.url);
	if (event.request.method !== "GET" || url.origin !== location.origin) return;
	if (url.pathname.startsWith("/assets/hozur/")) {
		event.respondWith(
			caches.open(CACHE).then(async (cache) => {
				const cached = await cache.match(event.request);
				const network = fetch(event.request).then((response) => {
					if (response.ok) cache.put(event.request, response.clone());
					return response;
				});
				return cached || network;
			})
		);
		return;
	}
	if (event.request.mode === "navigate" && url.pathname.startsWith("/hozur")) {
		event.respondWith(
			fetch(event.request).catch(() =>
				new Response(
					'<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body style="font-family:Tahoma,sans-serif;text-align:center;padding:4rem 1rem">اتصال به سرور برقرار نیست. دوباره امتحان کنید.</body></html>',
					{ headers: { "Content-Type": "text/html; charset=utf-8" } }
				)
			)
		);
	}
});
"""


# Guest on purpose: the browser re-fetches the worker script on its own, also after logout. It
# returns a constant script and touches no data.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep
def service_worker():
	"""Served from /api/method/... with a header that lets it control /hozur/."""
	from werkzeug.wrappers import Response

	return Response(
		SERVICE_WORKER,
		mimetype="application/javascript",
		headers={"Service-Worker-Allowed": "/hozur/", "Cache-Control": "no-cache"},
	)
