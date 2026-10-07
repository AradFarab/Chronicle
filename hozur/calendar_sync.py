"""Calendar Day table and Iran Holiday records (Frappe side of hozur.jalali)."""

import json

import frappe
import requests
from frappe import _

from hozur.jalali import calendar as jcal
from hozur.jalali import holidays as jhol
from hozur.jalali.dates import year_bounds
from hozur.utils import now_jalali

HOLIDAY_FIELDS = [
	"name",
	"jdate",
	"title",
	"holiday_type",
	"status",
	"scope",
	"province",
	"branch",
	"closure_pay_mode",
]
DAY_FIELDS = [
	"jyear",
	"jmonth",
	"jday",
	"weekday",
	"weekday_name",
	"day_type",
	"holiday_title",
	"has_predicted_holiday",
]


def _holiday_rows(filters: dict) -> list[dict]:
	rows = frappe.get_all("Iran Holiday", filters=filters, fields=HOLIDAY_FIELDS)
	for r in rows:
		r["date"] = r["jdate"]
	return rows


def ensure_calendar_days(first_year: int, last_year: int) -> int:
	"""Create missing Calendar Day rows for the years (inclusive). Returns the number created."""
	start, _ = year_bounds(first_year)
	_, end = year_bounds(last_year)
	existing = set(frappe.get_all("Calendar Day", filters={"jdate": ["between", [start, end]]}, pluck="name"))
	holidays = _holiday_rows({"jdate": ["between", [start, end]]})
	rows = [r for r in jcal.generate_days(first_year, last_year, holidays) if r["jdate"] not in existing]
	if not rows:
		return 0
	now, user = frappe.utils.now(), frappe.session.user
	fields = ["name", "creation", "modified", "owner", "modified_by", "jdate", *DAY_FIELDS]
	values = [(r["jdate"], now, now, user, user, r["jdate"], *(r[f] for f in DAY_FIELDS)) for r in rows]
	frappe.db.bulk_insert("Calendar Day", fields=fields, values=values, ignore_duplicates=True)
	return len(rows)


def refresh_days(jdates) -> None:
	"""Recompute Calendar Day rows after holidays on these dates changed."""
	for jdate in {d for d in jdates if d}:
		if not frappe.db.exists("Calendar Day", jdate):
			continue
		row = jcal.build_day(jdate, _holiday_rows({"jdate": jdate}))
		frappe.db.set_value("Calendar Day", jdate, {f: row[f] for f in DAY_FIELDS}, update_modified=False)


def _insert_seed(record: dict, audit: bool = False) -> bool:
	if frappe.db.exists("Iran Holiday", {"seed_key": record["key"]}):
		return False
	doc = frappe.get_doc(
		{
			"doctype": "Iran Holiday",
			"jdate": record["date"],
			"title": record["title"],
			"holiday_type": record["holiday_type"],
			"status": record["status"],
			"scope": record["scope"],
			"province": record.get("province"),
			"note": record.get("note"),
			"seed_key": record["key"],
		}
	)
	doc.flags.from_seed = True
	doc.flags.skip_audit = not audit
	doc.flags.ignore_permissions = True
	doc.insert()
	return True


def seed_holidays(records=None) -> list[str]:
	"""Insert seed holidays that are not in the database yet (never overwrites).
	Returns the dates of the holidays created."""
	return [
		record["date"]
		for record in (records if records is not None else jhol.seed_holidays())
		if _insert_seed(record)
	]


def seed_provinces() -> None:
	from hozur.setup.data import PROVINCES

	for name in PROVINCES:
		if not frappe.db.exists("Province", name):
			frappe.get_doc({"doctype": "Province", "province_name": name}).insert(ignore_permissions=True)


def install_calendar() -> None:
	"""Seed provinces, holidays and Calendar Days for the seeded years. Idempotent."""
	seed_provinces()
	new_dates = seed_holidays()
	first, last = jhol.seed_years()
	ensure_calendar_days(first, last)
	refresh_days(new_dates)


def apply_calendar_update(records: list[dict]) -> dict:
	"""Apply a newer holiday file. Records the operator edited are never touched."""
	result = {"created": 0, "updated": 0, "skipped_edited": 0}
	touched = set()
	for record in records:
		name = frappe.db.get_value(
			"Iran Holiday", {"seed_key": record["key"]}, ["name", "edited_by_operator"], as_dict=True
		)
		if not name:
			result["created"] += _insert_seed(record, audit=True)
			touched.add(record["date"])
			continue
		if name.edited_by_operator:
			result["skipped_edited"] += 1
			continue
		doc = frappe.get_doc("Iran Holiday", name.name)
		new = {"jdate": record["date"], "title": record["title"], "status": record["status"]}
		if any(doc.get(k) != v for k, v in new.items()):
			touched.update({doc.jdate, record["date"]})
			doc.update(new)
			doc.flags.from_seed = True
			doc.flags.ignore_permissions = True
			doc.flags.audit_reason = _("Calendar update from the project repository")
			doc.save()
			result["updated"] += 1
	years = {int(r["date"][:4]) for r in records}
	if years:
		ensure_calendar_days(min(years), max(years))
	refresh_days(touched)
	return result


@frappe.whitelist()
def update_calendar() -> dict:
	"""'Update Calendar' button: fetch the confirmed holiday file from the project repository."""
	frappe.only_for(["System Manager", "Hozur Operator"])
	url = frappe.db.get_single_value("Hozur Settings", "calendar_update_url")
	if not url:
		frappe.throw(_("Set the Calendar Update URL in Hozur Settings first"))
	try:
		response = requests.get(url, timeout=30)
		response.raise_for_status()
		payload = response.json()
	except (requests.RequestException, json.JSONDecodeError) as e:
		frappe.throw(_("Could not download the calendar file: {0}").format(str(e)))
	result = apply_calendar_update(payload.get("holidays", []))
	jdate, time = now_jalali()
	frappe.db.set_single_value("Hozur Settings", "last_calendar_update", f"{jdate} {time}")
	return result


@frappe.whitelist()
def generate_year(year: int) -> dict:
	"""Create Calendar Days and the fixed solar holidays for a year beyond the seed file.
	Lunar holidays for that year arrive with the next calendar update or are entered by hand."""
	frappe.only_for(["System Manager", "Hozur Operator"])
	year = int(year)
	if not 1300 <= year <= 1500:
		frappe.throw(_("Year out of range"))
	new_dates = seed_holidays(jhol.solar_holidays(year))
	created_days = ensure_calendar_days(year, year)
	refresh_days(new_dates)
	return {"days": created_days, "holidays": len(new_dates)}


def warn_predicted_next_year() -> None:
	"""Daily from Esfand: remind operators that next year's lunar holidays are still predictions."""
	jdate, _time = now_jalali()
	year, month = int(jdate[:4]), int(jdate[5:7])
	if month != 12:
		return
	start, end = year_bounds(year + 1)
	predicted = frappe.db.count(
		"Iran Holiday", {"jdate": ["between", [start, end]], "status": jhol.PREDICTED}
	)
	if not predicted:
		return
	subject = _("{0} holidays of {1} are still predictions. Update the calendar or confirm them.").format(
		predicted, year + 1
	)
	users = frappe.get_all(
		"Has Role", filters={"role": "Hozur Operator", "parenttype": "User"}, pluck="parent", distinct=True
	)
	for user in users:
		if frappe.db.exists("Notification Log", {"for_user": user, "subject": subject}):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"document_type": "Iran Holiday",
			}
		).insert(ignore_permissions=True)
