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
	r = calculate_day(workday(), OFFICE, [], rules, absences=[Absence("mission", "mission")])
	assert r.status == MISSION and r.mission_minutes == r.required_minutes == r.credited_minutes


def test_hourly_mission_inside_the_day(rules):
	r = calculate_day(
		workday(),
		OFFICE,
		punches("08:00", "10:00", "14:00", "16:30"),
		rules,
		absences=[Absence("mission", "mission", hm("10:00"), hm("14:00"))],
	)
	assert r.mission_minutes == 200  # 4 h minus the 40-minute break
	assert r.absence_minutes == 0 and r.credited_minutes == r.required_minutes


def test_unpaid_leave_is_excused_but_not_credited(rules):
	r = calculate_day(
		workday(),
		SHORT,
		punches("08:00", "12:00"),
		rules,
		absences=[Absence("leave", "Unpaid", hm("12:00"), hm("15:20"), paid=False)],
	)
	assert r.absence_minutes == 0 and r.early_leave_minutes == 0
	assert r.credited_minutes == 240 and r.leave_minutes == {"Unpaid": 200}


def test_overtime_buffer_after_the_shift(rules):
	"""Leaving up to 15 minutes after the end is not extra work; beyond it, all of it is (the
	product owner's choice, 1405/07/19)."""
	buffered = Shift("Buffered", start=hm("08:00"), end=hm("15:20"), overtime_after=15)
	r = calculate_day(workday(), buffered, punches("08:00", "15:30"), rules)
	assert r.extra_minutes == 0 and not r.overtime_intervals
	r = calculate_day(workday(), buffered, punches("08:00", "15:35"), rules)
	assert r.extra_minutes == 0
	r = calculate_day(workday(), buffered, punches("08:00", "16:00"), rules)
	assert r.extra_minutes == 40 and r.overtime_intervals == [(hm("15:20"), hm("16:00"))]


def test_grace_forgives_up_to_the_tolerance_then_counts_everything(rules):
	"""9:00-17:00 with 15 minutes of tolerance each way: 9:10 in and 17:10 out is a clean day;
	9:20 in is 20 minutes late, 17:20 out is 20 minutes of extra work."""
	nine_five = Shift(
		"9-5", start=hm("09:00"), end=hm("17:00"), grace_late=15, grace_early=15, overtime_after=15
	)
	r = calculate_day(workday(), nine_five, punches("09:10", "17:10"), rules)
	assert (r.late_minutes, r.extra_minutes, r.credited_minutes) == (0, 0, 480)
	r = calculate_day(workday(), nine_five, punches("09:20", "17:20"), rules)
	assert (r.late_minutes, r.extra_minutes) == (20, 20)
	r = calculate_day(workday(), nine_five, punches("09:00", "16:50"), rules)
	assert r.early_leave_minutes == 0 and r.credited_minutes == 480


def test_madde_51_several_breaks_are_not_working_time(rules):
	"""Lunch and an afternoon tea break, both unpaid (Article 51)."""
	shift = Shift(
		"Two breaks",
		start=hm("08:00"),
		end=hm("17:00"),
		breaks=((hm("12:00"), hm("12:45")), (hm("15:00"), hm("15:15"))),
	)
	assert shift.scheduled_minutes == 540 - 60
	r = calculate_day(workday(), shift, punches("08:00", "17:00"), rules)
	assert r.worked_minutes == 480 and r.credited_minutes == 480 and r.absence_minutes == 0


def test_madde_59_extra_work_outside_the_overtime_window_stays_unapproved(rules):
	"""Overtime may only come from 17:00-19:00; work until 20:00 with 3 h approved gives
	2 h of overtime and 1 h of unapproved extra work."""
	from hozur.engine.model import OvertimeApproval

	shift = Shift(
		"With window",
		start=hm("08:00"),
		end=hm("17:00"),
		breaks=((hm("12:00"), hm("13:00")),),
		overtime_windows=((hm("17:00"), hm("19:00")),),
	)
	r = calculate_day(
		workday(), shift, punches("08:00", "20:00"), rules, overtime=[OvertimeApproval(minutes=180)]
	)
	assert r.overtime_intervals == [(hm("17:00"), hm("19:00"))]
	assert r.total_overtime_minutes == 120
	assert r.outside_window_minutes == 60 and r.unapproved_extra_minutes == 60
	assert r.extra_minutes == 180
	assert "EXTRA_WORK_OUTSIDE_OVERTIME_WINDOW" in r.warnings


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
