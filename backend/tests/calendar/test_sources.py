"""Holiday sources: time.ir (mocked HTTP), the bundled seed and operator files."""

from __future__ import annotations

import json

import httpx
import pytest

from hozur.calendar.sources import (
	BundledSource,
	CalendarSourceError,
	FileSource,
	TimeIrSource,
	clean_title,
	parse_time_ir_month,
)
from hozur.jalali import holidays as hol

URL = "https://api.time.ir/v1/event/fa/events/calendar?year={year}&month={month}&day=0"


def month_payload(year: int, month: int) -> dict:
	"""Shaped like the time.ir calendar API: every event of the month view, holidays flagged."""
	events = [
		# a neighbouring day shown in the month view
		{
			"jalali_year": year,
			"jalali_month": month - 1 or 12,
			"jalali_day": 29,
			"title": "x",
			"is_holiday": True,
		},
		{
			"jalali_year": year,
			"jalali_month": month,
			"jalali_day": 5,
			"title": "روز ملی",
			"is_holiday": False,
		},
	]
	if month == 1:
		events += [
			{
				"jalali_year": year,
				"jalali_month": 1,
				"jalali_day": 1,
				"title": "جشن نوروز/جشن سال نو",
				"is_holiday": True,
			},
			{
				"jalali_year": year,
				"jalali_month": 1,
				"jalali_day": 12,
				"title": "روز جمهوری اسلامی",
				"is_holiday": True,
			},
		]
	if month == 3:
		events.append(
			{
				"jalali_year": year,
				"jalali_month": 3,
				"jalali_day": 4,
				"title": "عید سعيد غدیر خم [ ۱۸ ذوالحجه ]",
				"is_holiday": True,
			}
		)
	return {"data": {"event_list": events}}


def test_parse_time_ir_month_keeps_holidays_of_that_month_only():
	rows = parse_time_ir_month(month_payload(1406, 3), 1406, 3)
	assert [(r.jdate, r.title, r.holiday_type) for r in rows] == [
		("1406/03/04", "عید سعید غدیر خم", hol.OFFICIAL_LUNAR)
	]
	assert rows[0].status == hol.CONFIRMED


def test_time_ir_source_reads_twelve_months_with_the_api_key():
	seen = []

	def handler(request: httpx.Request) -> httpx.Response:
		seen.append((request.url.params["month"], request.headers.get("X-Api-Key")))
		return httpx.Response(200, json=month_payload(1406, int(request.url.params["month"])))

	source = TimeIrSource(URL, "KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))
	rows = source.fetch(1406)
	assert [m for m, _ in seen] == [str(m) for m in range(1, 13)] and {k for _, k in seen} == {"KEY"}
	assert {r.jdate for r in rows} == {"1406/01/01", "1406/01/12", "1406/03/04"}
	types = {r.jdate: r.holiday_type for r in rows}
	assert types["1406/01/12"] == hol.OFFICIAL_SOLAR and types["1406/03/04"] == hol.OFFICIAL_LUNAR


def test_time_ir_errors_are_clear():
	down = TimeIrSource(
		URL, None, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
	)
	with pytest.raises(CalendarSourceError, match=r"Cannot reach time\.ir"):
		down.fetch(1406)
	odd = TimeIrSource(
		URL,
		None,
		client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"x": 1}))),
	)
	with pytest.raises(CalendarSourceError, match="unexpected format"):
		odd.fetch(1406)


def test_clean_title():
	assert clean_title("عيد غدير [ ۱۸ ذوالحجه ]") == "عید غدیر"
	assert clean_title("  نوروز   (روز اول) ") == "نوروز"


def test_bundled_source_inside_and_past_the_seed():
	assert len([r for r in BundledSource().fetch(1405) if r.holiday_type == hol.OFFICIAL_SOLAR]) == 10
	past = BundledSource().fetch(1412)
	assert len(past) == 10 and all(r.holiday_type == hol.OFFICIAL_SOLAR for r in past)


def test_file_source_json_and_csv():
	payload = {
		"holidays": [{"jdate": "۱۴۰۶/۰۱/۰۱", "title": "نوروز"}, {"jdate": "1407/01/01", "title": "نوروز"}]
	}
	rows = FileSource(json.dumps(payload).encode(), "h.json").fetch(1406)
	assert [(r.jdate, r.holiday_type) for r in rows] == [("1406/01/01", hol.OFFICIAL_SOLAR)]
	csv_rows = FileSource("jdate,title,status\n1406/03/04,عید غدیر,predicted\n".encode(), "h.csv").fetch(1406)
	assert (csv_rows[0].holiday_type, csv_rows[0].status) == (hol.OFFICIAL_LUNAR, hol.PREDICTED)


def test_file_source_rejects_bad_rows():
	with pytest.raises(CalendarSourceError, match="Row 1"):
		FileSource(b"jdate,title\n1406/13/01,x\n", "h.csv").fetch(1406)
	with pytest.raises(CalendarSourceError, match="not valid JSON"):
		FileSource(b"{oops", "h.json")
