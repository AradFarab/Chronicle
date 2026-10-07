"""The current moment in the company's timezone, as Jalali day and time."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from hozur.config import get_settings
from hozur.jalali.dates import to_jalali


def now() -> datetime:
	return datetime.now(ZoneInfo(get_settings().timezone))


def today_jalali() -> str:
	return to_jalali(now().replace(tzinfo=None))[0]


def now_jalali() -> tuple[str, str]:
	return to_jalali(now().replace(tzinfo=None))
