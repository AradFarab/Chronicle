"""Iranian official holiday definitions and seed data. Pure Python: must not import frappe."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

SEED_FILE = Path(__file__).parent / "data" / "holidays.json"

# Holiday types (Iran Holiday.holiday_type). Values are stored; labels are translated.
OFFICIAL_SOLAR = "Official Solar"
OFFICIAL_LUNAR = "Official Lunar"
OFFICIAL_OCCASIONAL = "Official Occasional"  # declared by government, nationwide or per province (Article 63)
OFFICE_CLOSURE = "Office Closure"  # e.g. air pollution; pay handling chosen by the operator
COMPANY_INTERNAL = "Company Internal"  # paid, this company only
HOLIDAY_TYPES = (OFFICIAL_SOLAR, OFFICIAL_LUNAR, OFFICIAL_OCCASIONAL, OFFICE_CLOSURE, COMPANY_INTERNAL)

CONFIRMED, PREDICTED = "Confirmed", "Predicted"
SCOPES = ("Country", "Province", "Company", "Branch")

# Official solar holidays: fixed Jalali dates, never need updating.
SOLAR = (
	# (month, day, code, title)
	(1, 1, "nowruz-1", "نوروز"),
	(1, 2, "nowruz-2", "نوروز"),
	(1, 3, "nowruz-3", "نوروز"),
	(1, 4, "nowruz-4", "نوروز"),
	(1, 12, "islamic-republic-day", "روز جمهوری اسلامی"),
	(1, 13, "nature-day", "روز طبیعت"),
	(3, 14, "khomeini-demise", "رحلت امام خمینی"),
	(3, 15, "khordad-15", "قیام ۱۵ خرداد"),
	(11, 22, "revolution-day", "پیروزی انقلاب اسلامی"),
	(12, 29, "oil-nationalization", "ملی شدن صنعت نفت"),
)

# Official lunar holidays: (hijri month, day or "end", code, title). Their Jalali dates move
# every year and depend on the officially announced month starts in Iran.
LUNAR = (
	(1, 9, "tasua", "تاسوعای حسینی"),
	(1, 10, "ashura", "عاشورای حسینی"),
	(2, 20, "arbaeen", "اربعین حسینی"),
	(2, 28, "prophet-demise", "رحلت پیامبر اکرم و شهادت امام حسن مجتبی"),
	(2, "end", "imam-reza", "شهادت امام رضا"),
	(3, 8, "imam-askari", "شهادت امام حسن عسکری"),
	(3, 17, "prophet-birth", "میلاد پیامبر اکرم و امام جعفر صادق"),
	(6, 3, "fatima", "شهادت حضرت فاطمه زهرا"),
	(7, 13, "imam-ali-birth", "ولادت امام علی"),
	(7, 27, "mabath", "مبعث پیامبر اکرم"),
	(8, 15, "mahdi-birth", "ولادت حضرت قائم"),
	(9, 21, "imam-ali-martyrdom", "شهادت امام علی"),
	(10, 1, "fitr-1", "عید فطر"),
	(10, 2, "fitr-2", "تعطیل به مناسبت عید فطر"),
	(10, 25, "imam-sadiq", "شهادت امام جعفر صادق"),
	(12, 10, "adha", "عید قربان"),
	(12, 18, "ghadir", "عید غدیر"),
)


def solar_holidays(year: int) -> list[dict]:
	"""Seed records for the fixed solar holidays of a Jalali year (used for years past the seed file)."""
	return [
		{
			"key": f"{year:04d}/{m:02d}/{d:02d}:{code}",
			"date": f"{year:04d}/{m:02d}/{d:02d}",
			"title": title,
			"holiday_type": OFFICIAL_SOLAR,
			"status": CONFIRMED,
			"scope": "Country",
			"province": None,
			"note": "",
		}
		for m, d, code, title in SOLAR
	]


@cache
def _seed() -> dict:
	return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def seed_holidays(first_year: int | None = None, last_year: int | None = None) -> list[dict]:
	"""Holiday seed records (see tools/build_holiday_seed.py), optionally limited to a year range."""
	rows = _seed()["holidays"]
	if first_year is not None:
		rows = [r for r in rows if int(r["date"][:4]) >= first_year]
	if last_year is not None:
		rows = [r for r in rows if int(r["date"][:4]) <= last_year]
	return [dict(r) for r in rows]


def seed_years() -> tuple[int, int]:
	first, last = _seed()["years"]
	return first, last


# Office Closure.closure_pay_mode
CLOSURE_PAID_HOLIDAY, CLOSURE_EMPLOYER_PAID, CLOSURE_WORKDAY = "Paid Holiday", "Employer Paid", "workday"


def day_off_kind(holiday: dict) -> str | None:
	"""'official' (Article 63 holiday), 'company' (paid day off decided by the employer) or
	None when the record does not make the day a day off (an office closure kept as workday)."""
	htype = holiday.get("holiday_type")
	if htype == OFFICE_CLOSURE:
		return {CLOSURE_PAID_HOLIDAY: "official", CLOSURE_EMPLOYER_PAID: "company"}.get(
			holiday.get("closure_pay_mode")
		)
	if htype == COMPANY_INTERNAL:
		return "company"
	return "official"
