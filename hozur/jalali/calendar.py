"""Calendar Day generation and day-type resolution. Pure Python: must not import frappe."""

from __future__ import annotations

from collections.abc import Iterable

from hozur.jalali.dates import FRIDAY, WEEKDAY_NAMES, iter_days, parse_jdate, weekday, year_bounds
from hozur.jalali.holidays import PREDICTED, day_off_kind

# Calendar Day.day_type: the nationwide type of the day. Branch/province/company holidays
# are resolved per employee by resolve_day_type. Whether Friday is the weekly rest day of a
# given employee is decided by their work pattern, not here.
WORKDAY, FRIDAY_TYPE, OFFICIAL_HOLIDAY, COMPANY_HOLIDAY = (
	"Workday",
	"Friday",
	"Official Holiday",
	"Company Holiday",
)
DAY_TYPES = (WORKDAY, FRIDAY_TYPE, OFFICIAL_HOLIDAY, COMPANY_HOLIDAY)


def _nationwide(holidays: Iterable[dict]) -> list[dict]:
	return [h for h in holidays if h.get("scope") == "Country" and day_off_kind(h) == "official"]


def build_day(jdate: str, holidays: Iterable[dict] = ()) -> dict:
	"""One Calendar Day row. `holidays` are the Iran Holiday records on that date."""
	year, month, day = parse_jdate(jdate)
	wd = weekday(jdate)
	national = _nationwide(holidays)
	if national:
		day_type = OFFICIAL_HOLIDAY
	elif wd == FRIDAY:
		day_type = FRIDAY_TYPE
	else:
		day_type = WORKDAY
	return {
		"jdate": jdate,
		"jyear": year,
		"jmonth": month,
		"jday": day,
		"weekday": wd,
		"weekday_name": WEEKDAY_NAMES[wd],
		"day_type": day_type,
		"holiday_title": " / ".join(dict.fromkeys(h["title"] for h in national)),
		"has_predicted_holiday": int(any(h.get("status") == PREDICTED for h in national)),
	}


def generate_days(first_year: int, last_year: int, holidays: Iterable[dict] = ()) -> list[dict]:
	"""Every Jalali day of the given years (inclusive), with holidays applied."""
	by_date: dict[str, list[dict]] = {}
	for h in holidays:
		by_date.setdefault(h["date"], []).append(h)
	start, _ = year_bounds(first_year)
	_, end = year_bounds(last_year)
	return [build_day(d, by_date.get(d, ())) for d in iter_days(start, end)]


def _applies(holiday: dict, branch: str | None, province: str | None) -> bool:
	scope = holiday.get("scope")
	return (
		scope in ("Country", "Company")
		or (scope == "Province" and bool(province) and holiday.get("province") == province)
		or (scope == "Branch" and bool(branch) and holiday.get("branch") == branch)
	)


def resolve_day_type(
	calendar_day: dict, holidays: Iterable[dict], branch: str | None, province: str | None
) -> dict:
	"""Day type for one employee: the nationwide Calendar Day plus the holidays scoped to their
	province, branch or the whole company. Official holidays win over company holidays.
	Returns {"day_type", "titles", "predicted"}."""
	by_kind: dict[str, list[dict]] = {"official": [], "company": []}
	for h in holidays:
		kind = day_off_kind(h)
		if kind and _applies(h, branch, province):
			by_kind[kind].append(h)
	for kind, day_type in (("official", OFFICIAL_HOLIDAY), ("company", COMPANY_HOLIDAY)):
		if by_kind[kind]:
			return {
				"day_type": day_type,
				"titles": list(dict.fromkeys(h["title"] for h in by_kind[kind])),
				"predicted": any(h.get("status") == PREDICTED for h in by_kind[kind]),
			}
	return {"day_type": calendar_day["day_type"], "titles": [], "predicted": False}
