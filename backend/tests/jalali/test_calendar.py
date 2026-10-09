from collections import Counter

from hozur.jalali import calendar as cal
from hozur.jalali import holidays as hol
from hozur.jalali.dates import is_leap, iter_days, year_bounds

# Labor-law file, section 5: the 25 official holidays of 1405.
OFFICIAL_1405 = {
	"1405/01/01", "1405/01/02", "1405/01/03", "1405/01/04", "1405/01/12", "1405/01/13",
	"1405/03/06", "1405/03/14", "1405/03/15",
	"1405/04/03", "1405/04/04",
	"1405/05/13", "1405/05/21", "1405/05/22", "1405/05/30",
	"1405/06/08",
	"1405/08/22",
	"1405/10/02", "1405/10/16",
	"1405/11/04", "1405/11/22",
	"1405/12/09", "1405/12/19", "1405/12/20", "1405/12/29",
}  # fmt: skip


def test_seed_covers_1400_to_1410():
	assert hol.seed_years() == (1400, 1410)
	years = {int(h["date"][:4]) for h in hol.seed_holidays()}
	assert years == set(range(1400, 1411))


def test_1405_official_holidays_match_the_labor_law_list_exactly():
	official = {
		h["date"]
		for h in hol.seed_holidays(1405, 1405)
		if h["holiday_type"] in (hol.OFFICIAL_SOLAR, hol.OFFICIAL_LUNAR)
	}
	assert official == OFFICIAL_1405
	assert all(h["status"] == hol.CONFIRMED for h in hol.seed_holidays(1405, 1405))


def test_1405_government_declared_tir_holidays_are_seeded_with_scope():
	occasional = {
		h["date"]: h for h in hol.seed_holidays(1405, 1405) if h["holiday_type"] == hol.OFFICIAL_OCCASIONAL
	}
	assert occasional["1405/04/15"]["scope"] == hol.COUNTRY
	assert occasional["1405/04/13"]["scope"] == occasional["1405/04/14"]["scope"] == hol.PROVINCE
	assert occasional["1405/04/13"]["province"] == "تهران"


def test_lunar_holidays_after_1405_are_predicted_solar_are_confirmed():
	for h in hol.seed_holidays(1406, 1410):
		expected = hol.CONFIRMED if h["holiday_type"] == hol.OFFICIAL_SOLAR else hol.PREDICTED
		assert h["status"] == expected, h


def test_every_year_has_all_solar_and_lunar_holidays():
	for year in range(1400, 1411):
		codes = Counter(h["key"].split(":")[1] for h in hol.seed_holidays(year, year))
		assert all(codes[code] == 1 for _, _, code, _ in hol.SOLAR), year
		lunar = sum(codes[code] for _, _, code, _ in hol.LUNAR)
		# A lunar year is ~11 days shorter, so some events can appear twice or (in 1405,
		# where the official list wins) be left out.
		assert 15 <= lunar <= 19, (year, lunar)


def test_seed_keys_are_unique():
	keys = [h["key"] for h in hol.seed_holidays()]
	assert len(keys) == len(set(keys))


def _seed_rows(year):
	"""Seed rows shaped like `holiday` rows (province by id: Tehran = 1 here)."""
	rows = []
	for h in hol.seed_holidays(year, year):
		rows.append({**h, "province_id": 1 if h["province"] == "تهران" else None})
	return rows


def _by_date(rows):
	out = {}
	for r in rows:
		out.setdefault(r["date"], []).append(r)
	return out


def test_whole_year_day_types_from_the_seed():
	by_date = _by_date(_seed_rows(1405))
	start, end = year_bounds(1405)
	days = [cal.resolve_day(d, by_date.get(d, ())) for d in iter_days(start, end)]
	assert len(days) == 365
	info = {d.jdate: d for d in days}
	assert info["1405/07/14"].day_type == cal.WORKDAY
	assert info["1405/07/17"].day_type == cal.FRIDAY_TYPE
	assert info["1405/01/01"].day_type == cal.OFFICIAL_HOLIDAY
	assert info["1405/01/01"].title == "عید فطر / نوروز"
	assert info["1405/04/15"].day_type == cal.OFFICIAL_HOLIDAY  # nationwide occasional
	assert info["1405/04/13"].day_type != cal.OFFICIAL_HOLIDAY  # Tehran only, person not in Tehran
	holidays = {d.jdate for d in days if d.day_type == cal.OFFICIAL_HOLIDAY}
	assert holidays == OFFICIAL_1405 | {"1405/04/15"}


def test_provincial_holiday_applies_in_that_province():
	rows = _by_date(_seed_rows(1405))["1405/04/13"]
	assert cal.resolve_day("1405/04/13", rows, province_id=1).day_type == cal.OFFICIAL_HOLIDAY
	assert cal.resolve_day("1405/04/13", rows, province_id=2).day_type == cal.WORKDAY


def test_leap_years():
	assert [y for y in range(1400, 1411) if is_leap(y)] == [1403, 1408]


def test_predicted_flag():
	by_date = _by_date(_seed_rows(1407))
	predicted = [
		cal.resolve_day(d, rows)
		for d, rows in by_date.items()
		if any(r["status"] == hol.PREDICTED for r in rows)
	]
	assert predicted and all(d.predicted and d.day_type == cal.OFFICIAL_HOLIDAY for d in predicted)


def test_resolve_province_and_work_location_holidays():
	tehran_only = {
		"title": "t",
		"holiday_type": hol.OFFICIAL_OCCASIONAL,
		"scope": hol.PROVINCE,
		"province_id": 8,
	}
	assert cal.resolve_day("1405/07/14", [tehran_only], 1, 8).day_type == cal.OFFICIAL_HOLIDAY
	assert cal.resolve_day("1405/07/14", [tehran_only], 2, 4).day_type == cal.WORKDAY
	location = {
		"title": "b",
		"holiday_type": hol.COMPANY_INTERNAL,
		"scope": hol.WORK_LOCATION,
		"work_location_id": 1,
	}
	assert cal.resolve_day("1405/07/14", [location], 1, None).day_type == cal.COMPANY_HOLIDAY
	assert cal.resolve_day("1405/07/14", [location], 2, None).day_type == cal.WORKDAY


def test_office_closure_pay_modes():
	def closure(mode):
		return {
			"title": "c",
			"holiday_type": hol.OFFICE_CLOSURE,
			"scope": hol.COUNTRY,
			"closure_pay_mode": mode,
		}

	assert cal.resolve_day("1405/07/14", [closure("paid_holiday")]).day_type == cal.OFFICIAL_HOLIDAY
	assert cal.resolve_day("1405/07/14", [closure("employer_paid")]).day_type == cal.COMPANY_HOLIDAY
	assert cal.resolve_day("1405/07/14", [closure("workday")]).day_type == cal.WORKDAY


def test_official_holiday_wins_over_company_holiday():
	official = {
		"title": "o",
		"holiday_type": hol.OFFICIAL_SOLAR,
		"scope": hol.COUNTRY,
		"status": hol.CONFIRMED,
	}
	company = {"title": "c", "holiday_type": hol.COMPANY_INTERNAL, "scope": hol.COMPANY}
	day = cal.resolve_day("1405/07/14", [company, official])
	assert (day.day_type, day.titles, day.predicted) == (cal.OFFICIAL_HOLIDAY, ("o",), False)


def test_classify_official_holidays_from_outside_sources():
	assert hol.classify_official("1405/11/22", "پیروزی انقلاب اسلامی") == hol.OFFICIAL_SOLAR
	assert hol.classify_official("1405/03/14", "عید غدیر [ ۱۸ ذوالحجه ]") == hol.OFFICIAL_LUNAR
	assert hol.classify_official("1405/03/14", "رحلت امام خمینی") == hol.OFFICIAL_SOLAR
	assert hol.classify_official("1406/02/10", "عید فطر") == hol.OFFICIAL_LUNAR


def test_solar_holidays_for_years_past_the_seed():
	rows = hol.solar_holidays(1411)
	assert len(rows) == 10 and rows[0]["date"] == "1411/01/01"
	assert all(r["status"] == hol.CONFIRMED for r in rows)
