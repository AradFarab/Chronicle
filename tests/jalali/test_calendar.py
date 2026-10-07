from collections import Counter

from hozur.jalali import calendar as cal
from hozur.jalali import holidays as hol
from hozur.jalali.dates import is_leap, year_bounds

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
	assert occasional["1405/04/15"]["scope"] == "Country"
	assert occasional["1405/04/13"]["scope"] == occasional["1405/04/14"]["scope"] == "Province"
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


def test_generate_days_one_row_per_day_with_types():
	rows = cal.generate_days(1405, 1405, hol.seed_holidays(1405, 1405))
	start, end = year_bounds(1405)
	assert len(rows) == 365 and rows[0]["jdate"] == start and rows[-1]["jdate"] == end
	by_date = {r["jdate"]: r for r in rows}
	assert by_date["1405/07/14"]["day_type"] == cal.WORKDAY
	assert by_date["1405/07/17"]["day_type"] == cal.FRIDAY_TYPE
	assert by_date["1405/01/01"]["day_type"] == cal.OFFICIAL_HOLIDAY
	assert by_date["1405/01/01"]["holiday_title"] == "عید فطر / نوروز"
	assert by_date["1405/04/15"]["day_type"] == cal.OFFICIAL_HOLIDAY  # nationwide occasional
	assert by_date["1405/04/13"]["day_type"] != cal.OFFICIAL_HOLIDAY  # Tehran only
	holidays = {r["jdate"] for r in rows if r["day_type"] == cal.OFFICIAL_HOLIDAY}
	assert holidays == OFFICIAL_1405 | {"1405/04/15"}


def test_generate_days_whole_range_has_no_gaps():
	rows = cal.generate_days(1400, 1410)
	assert len(rows) == len({r["jdate"] for r in rows})
	assert rows[0]["jdate"] == "1400/01/01" and rows[-1]["jdate"] == "1410/12/29"
	assert [y for y in range(1400, 1411) if is_leap(y)] == [1403, 1408]
	assert len(rows) == 11 * 365 + 2


def test_predicted_flag_reaches_calendar_day():
	rows = cal.generate_days(1407, 1407, hol.seed_holidays(1407, 1407))
	flagged = [r for r in rows if r["has_predicted_holiday"]]
	assert flagged and all(r["day_type"] == cal.OFFICIAL_HOLIDAY for r in flagged)


def _day(day_type=cal.WORKDAY):
	return {"day_type": day_type}


def test_resolve_province_and_branch_holidays():
	tehran_only = {
		"title": "t",
		"holiday_type": hol.OFFICIAL_OCCASIONAL,
		"scope": "Province",
		"province": "تهران",
	}
	assert cal.resolve_day_type(_day(), [tehran_only], "B1", "تهران")["day_type"] == cal.OFFICIAL_HOLIDAY
	assert cal.resolve_day_type(_day(), [tehran_only], "B2", "اصفهان")["day_type"] == cal.WORKDAY
	branch = {"title": "b", "holiday_type": hol.COMPANY_INTERNAL, "scope": "Branch", "branch": "B1"}
	assert cal.resolve_day_type(_day(), [branch], "B1", None)["day_type"] == cal.COMPANY_HOLIDAY
	assert cal.resolve_day_type(_day(), [branch], "B2", None)["day_type"] == cal.WORKDAY


def test_office_closure_pay_modes():
	def closure(mode):
		return {
			"title": "c",
			"holiday_type": hol.OFFICE_CLOSURE,
			"scope": "Country",
			"closure_pay_mode": mode,
		}

	assert (
		cal.resolve_day_type(_day(), [closure("Paid Holiday")], None, None)["day_type"]
		== cal.OFFICIAL_HOLIDAY
	)
	assert (
		cal.resolve_day_type(_day(), [closure("Employer Paid")], None, None)["day_type"]
		== cal.COMPANY_HOLIDAY
	)
	assert cal.resolve_day_type(_day(), [closure("Workday")], None, None)["day_type"] == cal.WORKDAY


def test_official_holiday_wins_over_company_holiday():
	official = {"title": "o", "holiday_type": hol.OFFICIAL_SOLAR, "scope": "Country", "status": hol.CONFIRMED}
	company = {"title": "c", "holiday_type": hol.COMPANY_INTERNAL, "scope": "Company"}
	result = cal.resolve_day_type(_day(), [company, official], None, None)
	assert result == {"day_type": cal.OFFICIAL_HOLIDAY, "titles": ["o"], "predicted": False}


def test_solar_holidays_for_years_past_the_seed():
	rows = hol.solar_holidays(1411)
	assert len(rows) == 10 and rows[0]["date"] == "1411/01/01"
	assert all(r["status"] == hol.CONFIRMED for r in rows)
