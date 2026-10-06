"""File-based punch sources: USB exports, Excel/CSV files, old software exports (e.g. Paliz).

The operator describes a file once (Punch Import Template: which column holds the user id,
the date and the time, and in which calendar) and every later file of that kind is read the
same way. No frappe import here: hozur.devices.service turns ParsedPunch rows into Raw Punches.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

from hozur.devices.base import IN, OUT, UNKNOWN, DeviceAdapter, DeviceError, register
from hozur.jalali.dates import InvalidJalaliDate, from_gregorian, normalize_jdate, to_ascii_digits

ZKTECO_USB = "ZKTeco USB (attlog.dat)"
# Windows-1256 has no Persian yeh/kaf: older Persian software writes the Arabic letters.
_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
CSV, EXCEL = "CSV", "Excel"
DELIMITERS = {"Comma": ",", "Tab": "\t", "Semicolon": ";", "Pipe": "|"}


@dataclass(frozen=True)
class ParsedPunch:
	device_user_id: str
	jdate: str
	time: str  # HH:MM:SS
	device_timestamp: datetime | None  # only when the file carries a Gregorian device time
	direction: str = UNKNOWN
	raw: dict = field(default_factory=dict)


@dataclass
class ParseResult:
	punches: list[ParsedPunch] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)  # "row 12: ..." messages for the operator


@register
class FileImportAdapter(DeviceAdapter):
	"""Placeholder for devices whose punches arrive as files: nothing to poll."""

	code = "File Import"
	label = "File Import (USB, Excel, CSV)"
	network = False

	def _not_available(self):
		raise DeviceError("This device receives punches by file import; there is nothing to connect to")

	def fetch_since(self, since):
		self._not_available()

	def list_users(self):
		self._not_available()

	def sync_time(self, now):
		self._not_available()

	def health(self):
		self._not_available()


def normalize_text(value: str) -> str:
	return value.translate(_ARABIC_TO_PERSIAN)


def read_table(
	content: bytes, file_format: str, delimiter: str = "Comma", encoding: str = "UTF-8"
) -> list[list[str]]:
	"""Raw file bytes -> rows of cell strings (Arabic yeh/kaf normalized to Persian)."""
	if file_format == EXCEL:
		from openpyxl import load_workbook

		wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
		ws = wb.worksheets[0]
		rows = [["" if c is None else _cell_text(c) for c in row] for row in ws.iter_rows(values_only=True)]
	else:
		text = content.decode("cp1256" if encoding == "Windows-1256" else "utf-8-sig", errors="replace")
		if file_format == ZKTECO_USB:
			rows = [re.split(r"\t", line.strip()) for line in text.splitlines() if line.strip()]
		else:
			rows = list(csv.reader(io.StringIO(text), delimiter=DELIMITERS.get(delimiter, ",")))
	return [[normalize_text(c) for c in row] for row in rows]


def _cell_text(value) -> str:
	if isinstance(value, datetime):
		return value.strftime("%Y-%m-%d %H:%M:%S")
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value)


def _column(header: list[str] | None, spec: str | None) -> int | None:
	"""Column by 1-based number, Excel letter, or header text."""
	if not spec:
		return None
	spec = spec.strip()
	if spec.isdigit():
		return int(spec) - 1
	if re.fullmatch(r"[A-Za-z]{1,2}", spec):
		n = 0
		for ch in spec.upper():
			n = n * 26 + (ord(ch) - 64)
		return n - 1
	if header:
		wanted = normalize_text(spec)
		for i, name in enumerate(header):
			if normalize_text(name.strip()) == wanted:
				return i
	raise DeviceError(f"Column {spec!r} not found in the file")


def _time(value: str) -> str:
	value = to_ascii_digits(value.strip())
	m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", value)
	if not m:
		raise ValueError(f"time {value!r}")
	h, mi, s = int(m[1]), int(m[2]), int(m[3] or 0)
	if not (0 <= h < 24 and 0 <= mi < 60 and 0 <= s < 60):
		raise ValueError(f"time {value!r}")
	return f"{h:02d}:{mi:02d}:{s:02d}"


def _gregorian(value: str, date_format: str) -> datetime:
	value = to_ascii_digits(value.strip()).replace("/", "-")
	fmt = {"YYYY-MM-DD": "%Y-%m-%d", "DD-MM-YYYY": "%d-%m-%Y", "MM-DD-YYYY": "%m-%d-%Y"}.get(
		date_format.replace("/", "-"), "%Y-%m-%d"
	)
	return datetime.strptime(value, fmt)


def _jalali(value: str) -> str:
	value = to_ascii_digits(value.strip()).replace("-", "/")
	parts = value.split("/")
	if len(parts) != 3:
		raise ValueError(f"date {value!r}")
	return normalize_jdate("/".join((parts[0].zfill(4), parts[1].zfill(2), parts[2].zfill(2))))


def _direction(value: str, in_values: set[str], out_values: set[str]) -> str:
	v = to_ascii_digits(str(value).strip()).lower()
	if v in in_values:
		return IN
	if v in out_values:
		return OUT
	return UNKNOWN


def _values(spec: str | None) -> set[str]:
	return {to_ascii_digits(v.strip()).lower() for v in (spec or "").split(",") if v.strip()}


def parse_rows(rows: list[list[str]], template: dict) -> ParseResult:
	"""Apply a Punch Import Template (dict of its fields) to table rows."""
	result = ParseResult()
	file_format = template.get("file_format")
	if file_format == ZKTECO_USB:
		template = {
			**template,
			"has_header": 0,
			"skip_rows": 0,
			"user_id_column": "1",
			"datetime_column": "2",
			"date_column": None,
			"time_column": None,
			"date_calendar": "Gregorian",
			"date_format": "YYYY-MM-DD",
			"direction_column": "4",
			"in_values": "0,3,4",
			"out_values": "1,2,5",
		}
	skip = int(template.get("skip_rows") or 0)
	rows = rows[skip:]
	header = None
	if template.get("has_header") and rows:
		header, rows = [str(c) for c in rows[0]], rows[1:]
		first_data_row = skip + 2
	else:
		first_data_row = skip + 1

	col_user = _column(header, template.get("user_id_column"))
	col_dt = _column(header, template.get("datetime_column"))
	col_date = _column(header, template.get("date_column"))
	col_time = _column(header, template.get("time_column"))
	col_dir = _column(header, template.get("direction_column"))
	if col_user is None or (col_dt is None and (col_date is None or col_time is None)):
		raise DeviceError(
			"The template needs a user id column and either a date-time column or date and time columns"
		)
	calendar = template.get("date_calendar") or "Jalali"
	date_format = template.get("date_format") or ("YYYY/MM/DD" if calendar == "Jalali" else "YYYY-MM-DD")
	in_values, out_values = _values(template.get("in_values")), _values(template.get("out_values"))

	for offset, row in enumerate(rows):
		line = first_data_row + offset
		cells = [str(c).strip() for c in row]
		if not any(cells):
			continue
		try:
			user = to_ascii_digits(cells[col_user])
			if not user:
				raise ValueError("empty user id")
			if col_dt is not None:
				date_part, _, time_part = to_ascii_digits(cells[col_dt]).strip().partition(" ")
			else:
				date_part, time_part = cells[col_date], cells[col_time]
			time = _time(time_part)
			if calendar == "Gregorian":
				day = _gregorian(date_part, date_format)
				hh, mm, ss = (int(x) for x in time.split(":"))
				ts = day.replace(hour=hh, minute=mm, second=ss)
				jdate = from_gregorian(ts.date())
			else:
				ts = None
				jdate = _jalali(date_part)
			direction = (
				_direction(cells[col_dir], in_values, out_values)
				if col_dir is not None and col_dir < len(cells)
				else UNKNOWN
			)
		except (IndexError, ValueError, InvalidJalaliDate) as e:
			result.errors.append(f"row {line}: {e}")
			continue
		result.punches.append(
			ParsedPunch(
				device_user_id=user,
				jdate=jdate,
				time=time,
				device_timestamp=ts,
				direction=direction,
				raw={"row": line, "cells": cells},
			)
		)
	return result
