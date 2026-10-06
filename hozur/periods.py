"""Monthly period lock (CLAUDE.md rule 9). Once a Jalali month is closed, nothing inside it
changes until it is formally reopened."""

import frappe
from frappe import _
from frappe.utils.caching import request_cache

from hozur.jalali.dates import iter_days


class PeriodLockedError(frappe.ValidationError):
	pass


def period_of(jdate: str) -> str:
	return jdate[:7]


@request_cache
def _closed(period: str) -> bool:
	return frappe.db.get_value("Attendance Period", period, "status") == "Closed"


def is_locked(jdate: str) -> bool:
	return bool(jdate) and _closed(period_of(jdate))


def assert_open(*jdates: str | None) -> None:
	for jdate in jdates:
		if jdate and is_locked(jdate):
			frappe.throw(
				_("Period {0} is closed. Reopen it formally before changing anything in it.").format(
					period_of(jdate)
				),
				PeriodLockedError,
				title=_("Period Closed"),
			)


def assert_range_open(start: str, end: str) -> None:
	periods = sorted({period_of(d) for d in (start, end)})
	if start[:7] != end[:7]:
		periods = sorted({period_of(d) for d in iter_days(start, end)})
	for period in periods:
		assert_open(period + "/01")
