from datetime import date, datetime

import pytest

from hozur.jalali import dates as jd


def test_parse_and_format_round_trip():
	assert jd.parse_jdate("1405/07/14") == (1405, 7, 14)
	assert jd.format_jdate(1405, 7, 4) == "1405/07/04"


def test_persian_and_arabic_digits_are_accepted_and_normalized():
	assert jd.normalize_jdate("۱۴۰۵/۰۷/۱۴") == "1405/07/14"
	assert jd.normalize_jdate("١٤٠٥/٠٧/١٤") == "1405/07/14"
	assert jd.to_persian_digits("1405/07/14") == "۱۴۰۵/۰۷/۱۴"


@pytest.mark.parametrize(
	"bad", ["1405/7/14", "1405-07-14", "1405/13/01", "1405/07/31", "1405/12/30", "", None]
)
def test_invalid_dates_are_rejected(bad):
	assert not jd.is_valid_jdate(bad)
	with pytest.raises(jd.InvalidJalaliDate):
		jd.parse_jdate(bad)


def test_month_lengths_and_leap_years():
	assert [jd.month_length(1405, m) for m in range(1, 13)] == [31] * 6 + [30] * 5 + [29]
	# 1403 is a leap year (Esfand has 30 days); 1405 is not (labor-law file, section 5).
	assert jd.is_leap(1403) and not jd.is_leap(1405)
	assert jd.month_length(1403, 12) == 30


def test_gregorian_conversion_matches_known_days():
	assert jd.to_gregorian("1405/01/01") == date(2026, 3, 21)
	assert jd.from_gregorian(date(2026, 10, 6)) == "1405/07/14"


def test_device_timestamp_converts_to_jalali_day_and_time():
	assert jd.to_jalali(datetime(2026, 10, 6, 7, 58, 11)) == ("1405/07/14", "07:58:11")
	# Just before midnight stays on the same Jalali day.
	assert jd.to_jalali(datetime(2026, 3, 20, 23, 59, 59)) == ("1404/12/29", "23:59:59")


def test_weekday_saturday_is_zero_friday_is_six():
	assert jd.weekday("1405/01/01") == 0  # Saturday 2026-03-21
	assert jd.weekday("1405/07/14") == 3  # Tuesday 2026-10-06
	assert jd.weekday("1405/07/17") == jd.FRIDAY


def test_day_arithmetic_crosses_month_and_year_ends():
	assert jd.add_days("1404/12/29", 1) == "1405/01/01"
	assert jd.add_days("1405/07/01", -1) == "1405/06/31"
	assert jd.days_between("1405/01/01", "1406/01/01") == 365
	days = list(jd.iter_days("1405/06/30", "1405/07/02"))
	assert days == ["1405/06/30", "1405/06/31", "1405/07/01", "1405/07/02"]


def test_string_order_is_chronological():
	days = list(jd.iter_days("1404/11/01", "1405/02/01"))
	assert days == sorted(days)


def test_bounds_and_display():
	assert jd.year_bounds(1405) == ("1405/01/01", "1405/12/29")
	assert jd.month_bounds(1405, 7) == ("1405/07/01", "1405/07/30")
	assert jd.display("1405/07/14") == "۱۴۰۵/۰۷/۱۴"
	assert jd.display_long("1405/07/14") == "سه‌شنبه ۱۴ مهر ۱۴۰۵"
