#!/usr/bin/env python3
"""Build backend/chronicle/jalali/data/holidays.json: Iranian official holidays for 1400-1410.

Dev tool, not used at runtime. Run from the repository root:

    python3 -m venv .venv-tools && .venv-tools/bin/pip install -r tools/requirements.txt
    .venv-tools/bin/python tools/build_holiday_seed.py

Sources and status:
- Solar holidays (10 per year) have fixed Jalali dates: always "confirmed".
- 1405 comes verbatim from attendance-software-iran-labor-law-rules.md (section 5),
  plus the government-declared Tir 1405 holidays listed there. "confirmed".
- Lunar holidays 1400-1404 use Iran's official AH month starts (roozbehp/qamari,
  CC0, vendored in tools/data). "confirmed".
- Lunar holidays 1406-1410 are astronomical predictions for Tehran: "predicted"
  (پیش‌بینی), to be confirmed by the operator each year. The visibility rule was
  tuned on official months AH 1400-1429 and matches 87% of AH 1430-1447.
"""

from __future__ import annotations

import datetime
import json
import math
import sys
from pathlib import Path

import ephem
import jdatetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from chronicle.jalali.holidays import LUNAR, SOLAR

QAMARI = ROOT / "tools" / "data" / "qamari-1440-1447.txt"
OUTPUT = ROOT / "backend" / "chronicle" / "jalali" / "data" / "holidays.json"
FIRST_YEAR, LAST_YEAR = 1400, 1410

# Labor-law file, section 5: "فروردین ۱، ۲، ۳، ۴، ۱۲، ۱۳؛ خرداد ۶، ۱۴، ۱۵؛ تیر ۳، ۴؛ ..."
LIST_1405 = {
	1: [1, 2, 3, 4, 12, 13],
	3: [6, 14, 15],
	4: [3, 4],
	5: [13, 21, 22, 30],
	6: [8],
	8: [22],
	10: [2, 16],
	11: [4, 22],
	12: [9, 19, 20, 29],
}

# Same section: government-declared public holidays in Tir 1405 (Article 63 applies).
OCCASIONAL_1405 = [
	("1405/04/13", "province", "تهران"),
	("1405/04/14", "province", "تهران"),
	("1405/04/15", "country", None),
]
OCCASIONAL_TITLE = "تعطیل عمومی اعلامی هیئت دولت (مراسم تشییع)"

# AH month starts implied by the official 1405 list above (e.g. Ashura on 1405/04/04
# puts 1 Muharram 1448 on 2026-06-16). They extend the official data past AH 1447/10.
STARTS_FROM_1405_LIST = {
	(1447, 12): "2026-05-18",
	(1448, 1): "2026-06-16",
	(1448, 2): "2026-07-16",
	(1448, 3): "2026-08-14",
	(1448, 6): "2026-11-11",
	(1448, 7): "2026-12-11",
	(1448, 8): "2027-01-10",
	(1448, 9): "2027-02-08",
	(1448, 10): "2027-03-10",
}

TEHRAN = ("35.6892", "51.3890", 1190)
IRST = datetime.timedelta(hours=3, minutes=30)
# Crescent considered visible from Tehran at sunset when all hold:
MIN_LAG_MINUTES, MIN_ELONGATION_DEG, MIN_AGE_HOURS = 26, 8, 18


def jdate(g: datetime.date) -> str:
	j = jdatetime.date.fromgregorian(date=g)
	return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def load_official() -> dict[tuple[int, int], datetime.date]:
	starts = {}
	for line in QAMARI.read_text().splitlines():
		line = line.split("#")[0].strip()
		if not line:
			continue
		ym, g = line.split()
		y, m = (int(x) for x in ym.replace("*", "").split("/"))
		starts[(y, m)] = datetime.date.fromisoformat(g)
	starts.update({k: datetime.date.fromisoformat(v) for k, v in STARTS_FROM_1405_LIST.items()})
	return starts


def crescent_visible(day: datetime.date) -> bool:
	obs = ephem.Observer()
	obs.lat, obs.lon, obs.elevation = TEHRAN
	obs.pressure, obs.horizon = 0, "-0:34"
	obs.date = ephem.Date(datetime.datetime.combine(day, datetime.time(12)) - IRST)
	sun, moon = ephem.Sun(), ephem.Moon()
	sunset = obs.next_setting(sun)
	obs.date = sunset
	try:
		moonset = obs.next_setting(moon)
	except (ephem.AlwaysUpError, ephem.NeverUpError):
		return False
	sun.compute(obs)
	moon.compute(obs)
	lag = (moonset - sunset) * 24 * 60
	elongation = math.degrees(ephem.separation(sun, moon))
	age = (sunset - ephem.previous_new_moon(sunset)) * 24
	return lag >= MIN_LAG_MINUTES and elongation >= MIN_ELONGATION_DEG and age >= MIN_AGE_HOURS


def predict_start(previous_start: datetime.date) -> datetime.date:
	"""First day of the month after the one starting on previous_start."""
	nm = ephem.next_new_moon(
		ephem.Date(datetime.datetime.combine(previous_start, datetime.time()) + datetime.timedelta(days=20))
	)
	day = (nm.datetime() + IRST).date()
	while not crescent_visible(day):
		day += datetime.timedelta(days=1)
	return day + datetime.timedelta(days=1)


def month_starts(official: dict) -> dict[tuple[int, int], tuple[datetime.date, bool]]:
	"""(AH year, month) -> (first day, predicted?) for AH 1440..1454."""
	out = {k: (v, False) for k, v in official.items()}
	y, m = max(official)
	start = official[(y, m)]
	while y < 1454:
		start = predict_start(start)
		y, m = (y, m + 1) if m < 12 else (y + 1, 1)
		out[(y, m)] = (start, True)
	return out


def lunar_events(starts) -> list[dict]:
	events = []
	for (y, m), (start, predicted) in sorted(starts.items()):
		for hm, day, code, title in LUNAR:
			if hm != m:
				continue
			if day == "end":
				nxt = starts.get((y, m + 1) if m < 12 else (y + 1, 1))
				if not nxt:
					continue
				g = nxt[0] - datetime.timedelta(days=1)
				predicted = predicted or nxt[1]
			else:
				g = start + datetime.timedelta(days=day - 1)
			events.append({"date": jdate(g), "code": code, "title": title, "predicted": predicted})
	return events


def record(date, code, title, htype, status, scope="country", province=None, note=""):
	return {
		"key": f"{date}:{code}",
		"date": date,
		"title": title,
		"holiday_type": htype,
		"status": status,
		"scope": scope,
		"province": province,
		"note": note,
	}


def build() -> tuple[list[dict], list[str]]:
	warnings = []
	lunar = [
		e
		for e in lunar_events(month_starts(load_official()))
		if FIRST_YEAR <= int(e["date"][:4]) <= LAST_YEAR
	]
	holidays = []
	for year in range(FIRST_YEAR, LAST_YEAR + 1):
		solar = [
			record(f"{year}/{m:02d}/{d:02d}", code, title, "official_solar", "confirmed")
			for m, d, code, title in SOLAR
		]
		year_lunar = [e for e in lunar if e["date"].startswith(f"{year}/")]
		if year == 1405:
			allowed = {f"1405/{m:02d}/{d:02d}" for m, days in LIST_1405.items() for d in days}
			lunar_recs = []
			for e in year_lunar:
				if e["date"] in allowed:
					lunar_recs.append(record(e["date"], e["code"], e["title"], "official_lunar", "confirmed"))
				else:
					warnings.append(
						f"{e['date']} {e['title']}: computed, but not in the labor-law 1405 list; left out"
					)
			covered = {r["date"] for r in solar + lunar_recs}
			for missing in sorted(allowed - covered):
				warnings.append(f"{missing}: in the labor-law 1405 list but matched no event; added untitled")
				lunar_recs.append(
					record(missing, "labor-law-list", "تعطیل رسمی", "official_lunar", "confirmed")
				)
			occasional = [
				record(
					d,
					f"occasional-{scope.lower()}",
					OCCASIONAL_TITLE,
					"official_occasional",
					"confirmed",
					scope,
					prov,
				)
				for d, scope, prov in OCCASIONAL_1405
			]
			holidays += solar + lunar_recs + occasional
		else:
			predicted = year > 1405
			holidays += solar + [
				record(
					e["date"],
					e["code"],
					e["title"],
					"official_lunar",
					"predicted" if predicted else "confirmed",
				)
				for e in year_lunar
			]
	holidays.sort(key=lambda r: (r["date"], r["key"]))
	return holidays, warnings


def main() -> int:
	holidays, warnings = build()
	payload = {
		"generated_by": "tools/build_holiday_seed.py",
		"years": [FIRST_YEAR, LAST_YEAR],
		"sources": {
			"solar": "fixed dates",
			"1405": "attendance-software-iran-labor-law-rules.md, section 5",
			"lunar_1400_1404": "https://github.com/roozbehp/qamari (CC0), Iran calendar center data",
			"lunar_1406_1410": "astronomical crescent prediction for Tehran (Predicted)",
		},
		"holidays": holidays,
	}
	OUTPUT.parent.mkdir(parents=True, exist_ok=True)
	OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
	for w in warnings:
		print("WARNING:", w, file=sys.stderr)
	print(f"wrote {len(holidays)} holidays to {OUTPUT.relative_to(ROOT)}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
