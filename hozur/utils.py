"""Frappe-side helpers shared by doctypes. Business dates are Jalali strings (see hozur.jalali)."""

import frappe
from frappe import _

from hozur.jalali.dates import InvalidJalaliDate, from_gregorian, normalize_jdate, parse_jdate


def now_jalali() -> tuple[str, str]:
	"""Current Jalali day and time in the system time zone (Asia/Tehran)."""
	now = frappe.utils.now_datetime()
	return from_gregorian(now.date()), now.strftime("%H:%M:%S")


def today_jalali() -> str:
	return now_jalali()[0]


def clean_jdate(doc, fieldname: str, required: bool = False) -> str | None:
	"""Normalize a Jalali date field in place (Persian digits allowed) or throw a translated error."""
	value = (doc.get(fieldname) or "").strip()
	if not value:
		if required:
			frappe.throw(_("{0} is required").format(_(doc.meta.get_label(fieldname))))
		doc.set(fieldname, None)
		return None
	try:
		value = normalize_jdate(value)
	except InvalidJalaliDate:
		frappe.throw(
			_("{0}: {1} is not a valid Jalali date (expected e.g. 1405/07/14)").format(
				_(doc.meta.get_label(fieldname)), value
			),
			title=_("Invalid Date"),
		)
	doc.set(fieldname, value)
	return value


def set_year_month(doc, source: str = "jdate", year_field: str = "jyear", month_field: str = "jmonth"):
	if doc.get(source):
		year, month, _day = parse_jdate(doc.get(source))
		doc.set(year_field, year)
		doc.set(month_field, month)


def validate_date_order(doc, start_field: str, end_field: str):
	start, end = doc.get(start_field), doc.get(end_field)
	if start and end and end < start:
		frappe.throw(
			_("{0} cannot be before {1}").format(
				_(doc.meta.get_label(end_field)), _(doc.meta.get_label(start_field))
			)
		)
