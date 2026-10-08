"""Where a year's official holidays come from. Every source returns the same rows.

- time.ir: the official calendar (Institute of Geophysics); needs internet on the server.
- bundled: the seed shipped with the app (1400-1410); lunar holidays after 1405 are
  astronomical predictions, so years past the seed only get the fixed solar holidays.
- file: a JSON or CSV file the operator uploads (for servers without internet).
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

import httpx

from hozur.i18n import _
from hozur.jalali import holidays as hol
from hozur.jalali.dates import InvalidJalaliDate, format_jdate, normalize_jdate, to_ascii_digits
from hozur.services.errors import ValidationError

_BRACKETS = re.compile(r"\s*[\[(][^\])]*[\])]\s*")
_SPACES = re.compile(r"\s+")


class CalendarSourceError(ValidationError):
	pass


@dataclass(frozen=True)
class SourceHoliday:
	jdate: str
	title: str
	holiday_type: str
	status: str = hol.CONFIRMED
	scope: str = hol.COUNTRY
	province: str | None = None  # province name, for provincial holidays
	key: str = ""
	note: str = ""


def lenient_jdate(value: str) -> str:
	"""Operator files may write 1406/1/1 or 1406-01-01; store 1406/01/01 (raises if invalid)."""
	parts = re.split(r"[/-]", to_ascii_digits(value.strip()))
	if len(parts) != 3 or not all(p.isdigit() for p in parts):
		raise InvalidJalaliDate(value)
	return normalize_jdate(format_jdate(*(int(p) for p in parts)))


def clean_title(title: str) -> str:
	"""Drop bracketed dates ("عید غدیر [ ۱۸ ذوالحجه ]" -> "عید غدیر") and normalize spacing
	and Arabic letters."""
	title = title.replace("ي", "ی").replace("ك", "ک")
	return _SPACES.sub(" ", _BRACKETS.sub(" ", title)).strip()


class BundledSource:
	code = "bundled"

	def fetch(self, year: int) -> list[SourceHoliday]:
		first, last = hol.seed_years()
		rows = hol.seed_holidays(year, year) if first <= year <= last else hol.solar_holidays(year)
		return [
			SourceHoliday(
				jdate=r["date"],
				title=r["title"],
				holiday_type=r["holiday_type"],
				status=r["status"],
				scope=r["scope"],
				province=r.get("province"),
				key=r["key"],
				note=r.get("note") or "",
			)
			for r in rows
		]


def parse_time_ir_month(payload: dict, year: int, month: int) -> list[SourceHoliday]:
	"""Holidays in one month of the time.ir calendar API response."""
	try:
		events = payload["data"]["event_list"]
	except (KeyError, TypeError) as e:
		raise CalendarSourceError(_("time.ir answered in an unexpected format: {0}"), e)
	out: list[SourceHoliday] = []
	for event in events:
		if not event.get("is_holiday"):
			continue
		try:
			y, m, d = int(event["jalali_year"]), int(event["jalali_month"]), int(event["jalali_day"])
		except (KeyError, TypeError, ValueError) as e:
			raise CalendarSourceError(_("time.ir answered in an unexpected format: {0}"), e)
		if (y, m) != (year, month):
			continue  # neighbouring days shown in the month view
		try:
			jdate = normalize_jdate(format_jdate(y, m, d))
		except (ValueError, InvalidJalaliDate) as e:
			raise CalendarSourceError(_("time.ir answered in an unexpected format: {0}"), e)
		raw_title = str(event.get("title") or "").strip()
		title = clean_title(raw_title) or raw_title
		out.append(
			SourceHoliday(
				jdate=jdate,
				title=title,
				holiday_type=hol.classify_official(jdate, raw_title),
				key=f"time_ir:{jdate}:{title}",
			)
		)
	return out


class TimeIrSource:
	code = "time_ir"

	def __init__(
		self, url_template: str, api_key: str | None, client: httpx.Client | None = None, timeout: float = 20
	):
		self.url_template = url_template
		self.api_key = api_key
		self.client = client or httpx.Client(timeout=timeout)

	def fetch(self, year: int) -> list[SourceHoliday]:
		headers = {"X-Api-Key": self.api_key} if self.api_key else {}
		out: list[SourceHoliday] = []
		for month in range(1, 13):
			url = self.url_template.format(year=year, month=month)
			try:
				response = self.client.get(url, headers=headers)
				response.raise_for_status()
				payload = response.json()
			except httpx.HTTPError as e:
				raise CalendarSourceError(_("Cannot reach time.ir: {0}"), e)
			except ValueError as e:
				raise CalendarSourceError(_("time.ir answered in an unexpected format: {0}"), e)
			out.extend(parse_time_ir_month(payload, year, month))
		if not out:
			raise CalendarSourceError(_("time.ir returned no holidays for {0}"), year)
		return out


class FileSource:
	"""JSON: {"holidays": [{"jdate", "title", "holiday_type"?, "status"?}]} or a list of the same.
	CSV: a header row with jdate,title and optionally holiday_type, status."""

	code = "file"

	def __init__(self, content: bytes, filename: str = ""):
		self.rows = self._read(content, filename)

	@staticmethod
	def _read(content: bytes, filename: str) -> list[dict]:
		text = content.decode("utf-8-sig")
		if filename.lower().endswith(".json") or text.lstrip().startswith(("{", "[")):
			try:
				data = json.loads(text)
			except ValueError as e:
				raise CalendarSourceError(_("The holiday file is not valid JSON: {0}"), e)
			rows = data.get("holidays") if isinstance(data, dict) else data
			if not isinstance(rows, list):
				raise CalendarSourceError(_("The holiday file has no holiday list"))
			return rows
		return list(csv.DictReader(io.StringIO(text)))

	def fetch(self, year: int) -> list[SourceHoliday]:
		out = []
		for i, row in enumerate(self.rows, start=1):
			raw_date = to_ascii_digits(str(row.get("jdate") or row.get("date") or "")).strip()
			title = clean_title(str(row.get("title") or ""))
			try:
				jdate = lenient_jdate(raw_date)
			except (InvalidJalaliDate, ValueError):
				raise CalendarSourceError(
					_("Row {0} of the holiday file: {1} is not a Jalali date"), i, raw_date
				)
			if not title:
				raise CalendarSourceError(_("Row {0} of the holiday file has no title"), i)
			if int(jdate[:4]) != year:
				continue
			htype = row.get("holiday_type") or hol.classify_official(jdate, str(row.get("title")))
			if htype not in hol.HOLIDAY_TYPES:
				raise CalendarSourceError(
					_("Row {0} of the holiday file: unknown holiday type {1}"), i, htype
				)
			status = row.get("status") or hol.CONFIRMED
			if status not in (hol.CONFIRMED, hol.PREDICTED):
				raise CalendarSourceError(_("Row {0} of the holiday file: unknown status {1}"), i, status)
			out.append(
				SourceHoliday(
					jdate=jdate, title=title, holiday_type=htype, status=status, key=f"file:{jdate}:{title}"
				)
			)
		return out
