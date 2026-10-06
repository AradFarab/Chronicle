"""General behaviour of the daily calculation (pairing, rounding, lateness, absences)."""

from hozur.engine.daily import W_MISSING_PUNCH, calculate_day, pair_punches
from hozur.engine.model import ABSENT, INCOMPLETE, MISSION, PRESENT, Absence, Shift
from tests.engine.helpers import OFFICE, SHORT, hm, punches, workday


def test_rounding_is_in_the_workers_favour():
	intervals, missing = pair_punches(punches("08:00:59", "16:29:01"))
	assert intervals == [(480, 990)] and not missing


def test_pairing_by_direction_collapses_runs_in_the_workers_favour():
	intervals, missing = pair_punches(
		punches("08:00", "08:03", "12:00", "16:00", "16:05", directions="IIIOO")
	)
	assert intervals == [(480, 965)] and not missing


def test_pairing_by_order_when_directions_are_unknown():
	intervals, missing = pair_punches(punches("08:00", "12:00", "13:00", "16:00", "17:00"))
	assert intervals == [(480, 720), (780, 960)] and missing


def test_late_inside_grace_is_forgiven(rules):
	r = calculate_day(workday(), OFFICE, punches("08:04", "16:30"), rules)
	assert r.late_minutes == 0 and r.absence_minutes == 0 and r.credited_minutes == r.required_minutes


def test_late_beyond_grace_counts_the_real_minutes(rules):
	r = calculate_day(workday(), OFFICE, punches("08:20", "16:30"), rules)
	assert r.late_minutes == 20 and r.absence_minutes == 0
	assert r.credited_minutes == r.required_minutes - 20


def test_early_leave_and_midday_absence(rules):
	r = calculate_day(workday(), OFFICE, punches("08:00", "10:00", "11:00", "16:00"), rules)
	assert r.early_leave_minutes == 30
	assert r.absence_minutes == 60
	assert r.status == PRESENT


def test_absent_day(rules):
	r = calculate_day(workday(), OFFICE, [], rules)
	assert r.status == ABSENT and r.absent_day and r.absence_minutes == r.required_minutes


def test_missing_punch_is_incomplete(rules):
	r = calculate_day(workday(), OFFICE, punches("08:00"), rules)
	assert W_MISSING_PUNCH in r.warnings
	assert r.status == ABSENT  # nothing paired yet; a correction completes the day
	r = calculate_day(workday(), OFFICE, punches("08:00", "12:00", "13:10"), rules)
	assert r.status == INCOMPLETE


def test_daily_mission_counts_as_full_work(rules):
	r = calculate_day(workday(), OFFICE, [], rules, absences=[Absence("Mission", "Mission")])
	assert r.status == MISSION and r.mission_minutes == r.required_minutes == r.credited_minutes


def test_hourly_mission_inside_the_day(rules):
	r = calculate_day(
		workday(),
		OFFICE,
		punches("08:00", "10:00", "14:00", "16:30"),
		rules,
		absences=[Absence("Mission", "Mission", hm("10:00"), hm("14:00"))],
	)
	assert r.mission_minutes == 200  # 4 h minus the 40-minute break
	assert r.absence_minutes == 0 and r.credited_minutes == r.required_minutes


def test_unpaid_leave_is_excused_but_not_credited(rules):
	r = calculate_day(
		workday(),
		SHORT,
		punches("08:00", "12:00"),
		rules,
		absences=[Absence("Leave", "Unpaid", hm("12:00"), hm("15:20"), paid=False)],
	)
	assert r.absence_minutes == 0 and r.early_leave_minutes == 0
	assert r.credited_minutes == 240 and r.leave_minutes == {"Unpaid": 200}


def test_overtime_buffer_after_the_shift(rules):
	buffered = Shift("Buffered", start=hm("08:00"), end=hm("15:20"), overtime_after=15)
	r = calculate_day(workday(), buffered, punches("08:00", "15:30"), rules)
	assert r.extra_minutes == 0
	r = calculate_day(workday(), buffered, punches("08:00", "16:00"), rules)
	assert r.extra_minutes == 25


def test_flexible_shift(rules):
	flex = Shift(
		"Flex",
		start=hm("07:00"),
		end=hm("19:00"),
		flexible=True,
		latest_start=hm("09:00"),
		required_minutes=480,
		grace_late=0,
	)
	r = calculate_day(workday(), flex, punches("08:30", "16:30"), rules)
	assert r.late_minutes == 0 and r.absence_minutes == 0 and r.extra_minutes == 0
	r = calculate_day(workday(), flex, punches("09:30", "17:00"), rules)
	assert r.late_minutes == 30 and r.absence_minutes == 0
	r = calculate_day(workday(), flex, punches("08:00", "15:00"), rules)
	assert r.absence_minutes == 60
	r = calculate_day(workday(), flex, punches("07:00", "17:00"), rules)
	assert r.extra_minutes == 120


def test_day_without_a_shift_is_not_scheduled(rules):
	r = calculate_day(workday(), None, punches("08:00", "12:00"), rules)
	assert r.required_minutes == 0 and r.extra_minutes == 240 and r.absence_minutes == 0
