"""What kind of day a Jalali date is for one person. Pure Python (no database).

There is no per-day table: the weekday comes from jdatetime, holidays from the `holiday`
table. Whether Friday is someone's weekly rest day is decided by their work pattern."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from hozur.jalali.dates import FRIDAY, weekday
from hozur.jalali.holidays import BRANCH, COMPANY, COUNTRY, PREDICTED, PROVINCE, day_off_kind

WORKDAY, FRIDAY_TYPE, OFFICIAL_HOLIDAY, COMPANY_HOLIDAY = (
	"workday",
	"friday",
	"official_holiday",
	"company_holiday",
)
DAY_TYPES = (WORKDAY, FRIDAY_TYPE, OFFICIAL_HOLIDAY, COMPANY_HOLIDAY)


@dataclass(frozen=True)
class DayInfo:
	jdate: str
	weekday: int  # 0 = Saturday ... 6 = Friday
	day_type: str
	titles: tuple[str, ...] = ()
	predicted: bool = False  # an official holiday that is still a prediction

	@property
	def title(self) -> str:
		return " / ".join(self.titles)


def applies(holiday: Mapping, branch_id: int | None, province_id: int | None) -> bool:
	"""Does a holiday row apply to someone in this branch / province?"""
	scope = holiday.get("scope")
	return (
		scope in (COUNTRY, COMPANY)
		or (scope == PROVINCE and province_id is not None and holiday.get("province_id") == province_id)
		or (scope == BRANCH and branch_id is not None and holiday.get("branch_id") == branch_id)
	)


def resolve_day(
	jdate: str, holidays: Iterable[Mapping] = (), branch_id: int | None = None, province_id: int | None = None
) -> DayInfo:
	"""Day type for one person: official holidays win over company holidays, which win over
	the plain weekday. `holidays` are the rows on that date (any scope)."""
	wd = weekday(jdate)
	by_kind: dict[str, list[Mapping]] = {"official": [], "company": []}
	for h in holidays:
		kind = day_off_kind(h)
		if kind and applies(h, branch_id, province_id):
			by_kind[kind].append(h)
	for kind, day_type in (("official", OFFICIAL_HOLIDAY), ("company", COMPANY_HOLIDAY)):
		rows = by_kind[kind]
		if rows:
			return DayInfo(
				jdate=jdate,
				weekday=wd,
				day_type=day_type,
				titles=tuple(dict.fromkeys(h["title"] for h in rows)),
				predicted=any(h.get("status") == PREDICTED for h in rows),
			)
	return DayInfo(jdate=jdate, weekday=wd, day_type=FRIDAY_TYPE if wd == FRIDAY else WORKDAY)
