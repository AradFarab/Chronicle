"""Cleaning values typed into other people's spreadsheets, for the Excel import.

Each function takes what a cell holds (text, a number, an Excel date or time) and returns the
canonical value plus a note when it had to change something, so the column-mapping panel can
show the admin what was standardised before anything is saved. A value that cannot be read
raises ValueError.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from hozur.jalali.dates import InvalidJalaliDate, from_gregorian, normalize_jdate, to_ascii_digits

ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا"})
_ZERO_WIDTH = dict.fromkeys(map(ord, "‌‍‎‏‪‫‬‭‮﻿"), " ")
_PM = ("pm", "p.m", "ب.ظ", "بظ", "بعدازظهر", "بعد از ظهر", "عصر", "شب")
_AM = ("am", "a.m", "ق.ظ", "قظ", "صبح", "قبل از ظهر", "قبلازظهر")
YES = {"1", "true", "yes", "y", "بله", "آری", "اری", "اره", "آره", "اوکی", "دارد", "فعال", "✓", "✔", "x", "*"}
NO = {"0", "false", "no", "n", "خیر", "نه", "ندارد", "غیرفعال", "غیر فعال", "-", "✗", "✘"}


def plain(value: Any) -> str:
	"""Text for comparing: Persian letters, ASCII digits, no zero-width marks, single spaces."""
	text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
	text = to_ascii_digits(text.translate(ARABIC_TO_PERSIAN).translate(_ZERO_WIDTH))
	return re.sub(r"\s+", " ", text).strip()


def key(value: Any) -> str:
	"""A loose matching key: plain, lower case, without spaces and punctuation."""
	return re.sub(r"[\s\-_./:،,()*]+", "", plain(value).lower())


def similarity(a: Any, b: Any) -> float:
	ka, kb = key(a), key(b)
	if not ka or not kb:
		return 0.0
	if ka == kb:
		return 1.0
	if ka in kb or kb in ka:
		return 0.85
	return SequenceMatcher(None, ka, kb).ratio()


def cell_text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return plain(value)


def text(value: Any) -> tuple[str | None, str | None]:
	raw = "" if value is None else str(value)
	if isinstance(value, float) and value.is_integer():
		raw = str(int(value))
	cleaned = plain(raw)
	if not cleaned:
		return None, None
	return cleaned, (f"«{raw.strip()}» → «{cleaned}»" if cleaned != raw.strip() else None)


def number(value: Any) -> tuple[int | float | None, str | None]:
	if value is None or value == "":
		return None, None
	if isinstance(value, bool):
		raise ValueError(value)
	if isinstance(value, int | float):
		n = Decimal(str(value))
	else:
		raw = plain(value).replace("٫", ".").replace("/", ".").replace("،", "").replace(",", "")
		raw = raw.replace(" ", "")
		if not raw:
			return None, None
		try:
			n = Decimal(raw)
		except InvalidOperation:
			raise ValueError(value) from None
	result = int(n) if n == n.to_integral_value() else float(n)
	return result, None


def boolean(value: Any) -> tuple[bool | None, str | None]:
	if value is None or value == "":
		return None, None
	if isinstance(value, bool):
		return value, None
	word = plain(value).lower()
	if word in YES:
		return True, None
	if word in NO:
		return False, None
	raise ValueError(value)


def _clock(hours: int, minutes: int) -> str:
	if not (0 <= hours <= 24 and 0 <= minutes <= 59) or (hours == 24 and minutes):
		raise ValueError((hours, minutes))
	return f"{hours % 24:02d}:{minutes:02d}"


def clock(value: Any) -> tuple[str | None, str | None]:
	"""A time of day -> 'HH:MM'. Reads Excel times, '9', '930', '9.30', '۹:۳۰', '9:30 ب.ظ'."""
	if value is None or value == "":
		return None, None
	if isinstance(value, datetime):
		value = value.time()
	if isinstance(value, time):
		result = f"{value.hour:02d}:{value.minute:02d}"
		return result, None
	if isinstance(value, int | float) and not isinstance(value, bool):
		if 0 <= value < 1:  # an Excel time: a fraction of a day
			total = round(value * 1440)
			result = _clock(total // 60, total % 60)
			return result, f"{value} → {result}"
		value = str(int(value)) if float(value).is_integer() else str(value)
	raw = str(value).strip()
	t = plain(raw).lower().replace("ساعت", "").strip()
	pm = any(t.endswith(m) or t.startswith(m) for m in _PM)
	am = any(t.endswith(m) or t.startswith(m) for m in _AM)
	for marker in (*_PM, *_AM):
		t = t.replace(marker, "")
	t = t.strip()
	m = re.fullmatch(r"(\d{1,2})\s*[:.\-/،,٫ ]\s*(\d{1,2})(?:\s*[:.]\s*\d{1,2})?", t)
	if m:
		hours, minutes = int(m[1]), int(m[2])
		if len(m[2]) == 1:
			minutes *= 10  # 9.3 -> 9:30
	elif re.fullmatch(r"\d{1,2}", t):
		hours, minutes = int(t), 0
	elif re.fullmatch(r"\d{3,4}", t):
		hours, minutes = int(t[:-2]), int(t[-2:])
	else:
		raise ValueError(value)
	if pm and hours < 12:
		hours += 12
	if am and hours == 12:
		hours = 0
	result = _clock(hours, minutes)
	return result, (f"«{raw}» → {result}" if result != raw else None)


def jdate(value: Any) -> tuple[str | None, str | None]:
	"""A Jalali date -> '1405/07/14'. Reads '1405/7/1', '1405-07-01', '14050701', '05/07/01',
	'01/07/1405' and Persian digits. A real Excel date is Gregorian: it is converted once,
	here, and the note says so."""
	if value is None or value == "":
		return None, None
	if isinstance(value, datetime | date):
		g = value.date() if isinstance(value, datetime) else value
		if g.year < 1700:  # Excel showed a Jalali date as a date: 1405-07-14 read as a datetime
			result = normalize_jdate(f"{g.year:04d}/{g.month:02d}/{g.day:02d}")
			return result, None
		result = from_gregorian(g)
		return result, f"{g.isoformat()} → {result}"
	if isinstance(value, int | float) and not isinstance(value, bool):
		value = str(int(value))
	raw = str(value).strip()
	t = plain(raw)
	parts = re.split(r"\s*[/\-.\\،, ]\s*", t)
	if len(parts) == 1 and re.fullmatch(r"\d{8}", t):
		parts = [t[:4], t[4:6], t[6:]]
	elif len(parts) == 1 and re.fullmatch(r"\d{6}", t):
		parts = [t[:2], t[2:4], t[4:]]
	if len(parts) != 3 or not all(p.isdigit() for p in parts):
		raise ValueError(value)
	y, m, d = parts
	if len(d) == 4 and len(y) <= 2:  # day/month/year
		y, d = d, y
	year = int(y)
	if year < 100:
		year += 1400 if year < 50 else 1300
	try:
		result = normalize_jdate(f"{year:04d}/{int(m):02d}/{int(d):02d}")
	except InvalidJalaliDate:
		raise ValueError(value) from None
	return result, (f"«{raw}» → {result}" if result != raw else None)


def time_ranges(value: Any) -> list[tuple[str, str]]:
	"""'12:30-13:10, 15:00-15:15' -> [('12:30', '13:10'), ('15:00', '15:15')]."""
	ranges = []
	for part in re.split(r"[,،;\n]+", plain(value)):
		part = part.strip()
		if not part:
			continue
		pieces = re.split(r"\s*(?:تا|to|–|—|~|-)\s*", part)
		if len(pieces) != 2:
			raise ValueError(part)
		start, _n = clock(pieces[0])
		end, _n = clock(pieces[1])
		ranges.append((start, end))
	return ranges
