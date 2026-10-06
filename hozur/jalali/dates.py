"""Jalali date helpers. Pure Python: must not import frappe.

Business dates are strings in the form ``1405/07/14`` (ASCII digits, zero-padded).
That form sorts correctly and supports range filters without conversion.
Gregorian values only appear at the device boundary (``to_jalali``) and inside
these helpers; they are never stored as business dates.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import jdatetime

JDATE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")

MONTH_NAMES = (
	"فروردین",
	"اردیبهشت",
	"خرداد",
	"تیر",
	"مرداد",
	"شهریور",
	"مهر",
	"آبان",
	"آذر",
	"دی",
	"بهمن",
	"اسفند",
)

# Index = weekday(): 0 is Saturday (شنبه), 6 is Friday (جمعه).
WEEKDAY_NAMES = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
FRIDAY = 6

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_ASCII = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, "0123456789" * 2)
_TO_PERSIAN = str.maketrans("0123456789", _PERSIAN_DIGITS)


class InvalidJalaliDate(ValueError):
	pass


def to_ascii_digits(value: str) -> str:
	"""Persian/Arabic-Indic digits -> ASCII digits (what we store)."""
	return value.translate(_TO_ASCII)


def to_persian_digits(value: object) -> str:
	"""ASCII digits -> Persian digits (what we display)."""
	return str(value).translate(_TO_PERSIAN)


def is_leap(year: int) -> bool:
	return jdatetime.date(year, 1, 1).isleap()


def month_length(year: int, month: int) -> int:
	if not 1 <= month <= 12:
		raise InvalidJalaliDate(f"month out of range: {month}")
	if month <= 6:
		return 31
	if month <= 11:
		return 30
	return 30 if is_leap(year) else 29


def format_jdate(year: int, month: int, day: int) -> str:
	return f"{year:04d}/{month:02d}/{day:02d}"


def parse_jdate(value: str) -> tuple[int, int, int]:
	"""'1405/07/14' (Persian digits accepted) -> (1405, 7, 14). Raises InvalidJalaliDate."""
	if not isinstance(value, str):
		raise InvalidJalaliDate(f"not a string: {value!r}")
	m = JDATE_RE.match(to_ascii_digits(value.strip()))
	if not m:
		raise InvalidJalaliDate(f"expected YYYY/MM/DD, got {value!r}")
	year, month, day = (int(g) for g in m.groups())
	if not 1 <= month <= 12 or not 1 <= day <= month_length(year, month):
		raise InvalidJalaliDate(f"no such Jalali day: {value!r}")
	return year, month, day


def normalize_jdate(value: str) -> str:
	"""Validate and return the canonical stored form (ASCII, zero-padded)."""
	return format_jdate(*parse_jdate(value))


def is_valid_jdate(value: str) -> bool:
	try:
		parse_jdate(value)
	except InvalidJalaliDate:
		return False
	return True


def _to_jd(value: str) -> jdatetime.date:
	return jdatetime.date(*parse_jdate(value))


def to_gregorian(value: str) -> date:
	"""Internal conversion only (device queries, weekday math). Never store the result."""
	return _to_jd(value).togregorian()


def from_gregorian(value: date) -> str:
	j = jdatetime.date.fromgregorian(date=value)
	return format_jdate(j.year, j.month, j.day)


def to_jalali(ts: datetime) -> tuple[str, str]:
	"""Device wall-clock timestamp -> ('1405/07/14', '08:02:11'). Used once, at ingestion."""
	return from_gregorian(ts.date()), ts.strftime("%H:%M:%S")


def weekday(value: str) -> int:
	"""0 = Saturday ... 6 = Friday."""
	return _to_jd(value).weekday()


def add_days(value: str, days: int) -> str:
	return from_gregorian(to_gregorian(value) + timedelta(days=days))


def days_between(start: str, end: str) -> int:
	"""Number of days from start to end (end - start)."""
	return (to_gregorian(end) - to_gregorian(start)).days


def iter_days(start: str, end: str) -> Iterator[str]:
	"""Every Jalali day from start to end, both inclusive."""
	current = to_gregorian(start)
	last = to_gregorian(end)
	while current <= last:
		yield from_gregorian(current)
		current += timedelta(days=1)


def year_bounds(year: int) -> tuple[str, str]:
	return format_jdate(year, 1, 1), format_jdate(year, 12, month_length(year, 12))


def month_bounds(year: int, month: int) -> tuple[str, str]:
	return format_jdate(year, month, 1), format_jdate(year, month, month_length(year, month))


def display(value: str) -> str:
	"""'1405/07/14' -> '۱۴۰۵/۰۷/۱۴'."""
	return to_persian_digits(normalize_jdate(value))


def display_long(value: str) -> str:
	"""'1405/07/14' -> 'دوشنبه ۱۴ مهر ۱۴۰۵'."""
	year, month, day = parse_jdate(value)
	return f"{WEEKDAY_NAMES[weekday(value)]} {to_persian_digits(day)} {MONTH_NAMES[month - 1]} {to_persian_digits(year)}"


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def normalize_time(value: str) -> str | None:
	"""'8:05' / '۰۸:۰۵:۰۰' -> '08:05:00'; None when it is not a valid time of day."""
	m = _TIME_RE.match(to_ascii_digits(str(value or "").strip()))
	if not m:
		return None
	h, mi, s = int(m[1]), int(m[2]), int(m[3] or 0)
	if h > 23 or mi > 59 or s > 59:
		return None
	return f"{h:02d}:{mi:02d}:{s:02d}"
