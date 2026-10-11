"""Excel import of the admin's own sheet: columns in any order, connected in a panel, cleaned
and previewed before anything is saved."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from hozur.db.models import Shift, WorkLocation
from hozur.services import cleaning, excel
from hozur.services.errors import ValidationError
from tests.services.test_excel import ctx, workbook


@pytest.mark.parametrize(
	("raw", "expected"),
	[
		("9", "09:00"),
		("930", "09:30"),
		("9.30", "09:30"),
		("9.3", "09:30"),
		("۹:۳۰", "09:30"),
		("17:05:00", "17:05"),
		("5:30 ب.ظ", "17:30"),
		("5:30 PM", "17:30"),
		("ساعت 8", "08:00"),
		(0.375, "09:00"),
		(datetime.time(7, 45), "07:45"),
	],
)
def test_times_are_standardised(raw, expected):
	assert cleaning.clock(raw)[0] == expected


@pytest.mark.parametrize(
	("raw", "expected"),
	[
		("1405/7/1", "1405/07/01"),
		("1405-07-01", "1405/07/01"),
		("14050701", "1405/07/01"),
		("۱۴۰۵/۰۷/۰۱", "1405/07/01"),
		("05/07/01", "1405/07/01"),
		("01/07/1405", "1405/07/01"),
		(datetime.date(2026, 9, 23), "1405/07/01"),
	],
)
def test_dates_are_read_in_many_shapes(raw, expected):
	assert cleaning.jdate(raw)[0] == expected


def test_bad_values_are_refused():
	for bad in ("25:00", "abc", "9:75"):
		with pytest.raises(ValueError):
			cleaning.clock(bad)
	with pytest.raises(ValueError):
		cleaning.jdate("1405/13/01")


def test_arabic_letters_and_zero_width_marks_are_cleaned():
	assert cleaning.text("علي‌كريمي ")[0] == "علی کریمی"
	assert cleaning.key("کارشناس‌فروش") == cleaning.key("كارشناس فروش")


def test_the_panel_suggests_columns_in_any_order(org):
	content = workbook(["توضیحات", "شهر", "نام محل", "استان"], ("x", "اصفهان", "کارگاه", "اصفهان"))
	info = excel.inspect_file(org.db, "work-locations", content, "places.xlsx", "fa")
	assert [c["header"] for c in info["columns"]] == ["توضیحات", "شهر", "نام محل", "استان"]
	assert info["suggested"]["province_id"] == 4 and info["suggested"]["city"] == 2
	assert info["columns"][2]["samples"] == ["کارگاه"]
	assert {f["key"] for f in info["fields"]} >= {"name", "province_id"}


def test_mapped_columns_and_a_value_for_every_row(org):
	content = workbook(
		["عنوان", "ردیف", "شهرستان"],
		("انبار شرقي", 1, "تهران"),
		("انبار غربی", 2, "کرج"),
	)
	mapping = {"name": 1, "city": 3, "province_id": {"value": "تهران"}, "is_active": {"value": "بله"}}
	preview = excel.run(ctx(org), "work-locations", content, filename="x.xlsx", mapping=mapping, dry_run=True)
	assert preview.dry_run and not preview.errors and preview.checked == 2
	assert preview.rows[0].values["name"] == "انبار شرقی"  # Arabic ya cleaned, and shown
	assert org.db.scalar(select(WorkLocation).where(WorkLocation.name == "انبار شرقی")) is None
	done = excel.run(ctx(org), "work-locations", content, filename="x.xlsx", mapping=mapping)
	assert done.imported and done.created == 2
	assert org.db.scalar(select(WorkLocation.city).where(WorkLocation.name == "انبار غربی")) == "کرج"


def test_a_required_field_must_be_connected(org):
	content = workbook(["عنوان"], ("x",))
	with pytest.raises(ValidationError, match="استان"):
		excel.run(ctx(org), "work-locations", content, mapping={"name": 1})


def test_csv_files_are_read_too(org):
	content = "name,shift_type,start,end,breaks,windows\n۹ تا ۵,ثابت,9,17,12:00-12:45، 15:00-15:15,17-19\n"
	mapping = {
		"name": 1,
		"shift_type": 2,
		"start_time": 3,
		"end_time": 4,
		"breaks": 5,
		"overtime_windows": 6,
	}
	result = excel.run(ctx(org), "shifts", content.encode(), filename="s.csv", mapping=mapping)
	assert result.imported, result.errors
	shift = org.db.scalar(select(Shift).where(Shift.name == "9 تا 5"))  # digits stored as ASCII
	assert [(g.kind, g.start_minute, g.end_minute) for g in shift.segments] == [
		("break", 720, 765),
		("break", 900, 915),
		("overtime", 1020, 1140),
	]


def test_a_night_shift_break_after_midnight_is_the_next_day(org):
	content = workbook(
		["نام", "نوع", "شروع", "پایان", "استراحت"], ("شب", "ثابت", "18:00", "06:00", "01:00-01:30")
	)
	mapping = {"name": 1, "shift_type": 2, "start_time": 3, "end_time": 4, "breaks": 5}
	assert excel.run(ctx(org), "shifts", content, mapping=mapping).imported
	shift = org.db.scalar(select(Shift).where(Shift.name == "شب"))
	assert [(g.start_minute, g.end_minute) for g in shift.segments] == [(1500, 1530)]
