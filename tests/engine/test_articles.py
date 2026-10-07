"""One or more tests per labor-law article (CLAUDE.md rule 3). Names: test_madde_<article>_..."""

from dataclasses import replace

from hozur.engine.daily import (
	W_DAILY_LIMIT,
	W_EMERGENCY_CAP,
	W_HARD_HARMFUL_LIMIT,
	W_JUVENILE_NIGHT,
	W_NO_OVERTIME_HARD_HARMFUL,
	W_NO_OVERTIME_JUVENILE,
	W_OVERTIME_CAP,
	W_SPAN,
	W_UNAPPROVED_EXTRA,
	calculate_day,
)
from hozur.engine.model import (
	ABSENT,
	EMERGENCY,
	EXCEPTIONAL,
	HOLIDAY,
	LEAVE,
	NORMAL,
	REST,
	Absence,
	Day,
	EmployeeFlags,
	OvertimeApproval,
	Shift,
)
from hozur.engine.periodic import (
	EVENING,
	MORNING,
	NIGHT,
	absence_streaks,
	annual_leave_entitlement,
	hourly_leave_days,
	rotating_four_week_excess,
	rotation_premium,
	shift_kind,
	weekly_schedule_excess,
	year_end_carry_over,
)
from hozur.engine.rules import violations
from tests.engine.helpers import OFFICE, SHORT, hm, punches, workday


def test_madde_51_break_is_not_working_time(rules):
	r = calculate_day(workday(), OFFICE, punches("08:00", "16:30"), rules)
	assert r.required_minutes == 470  # 8.5 h minus the 40-minute break
	assert r.worked_minutes == 470
	assert r.absence_minutes == r.late_minutes == r.early_leave_minutes == 0


def test_madde_51_schedule_over_eight_hours_warns(rules):
	long_shift = Shift("Long", start=hm("07:00"), end=hm("16:30"))
	r = calculate_day(workday(), long_shift, punches("07:00", "16:30"), rules)
	assert W_DAILY_LIMIT in r.warnings


def test_madde_51_note_1_weekly_44_hours(rules):
	# Saturday-Wednesday 8 h, Thursday 4 h = 44 h: allowed; one more hour is not.
	assert weekly_schedule_excess([480] * 5 + [240, 0], rules) == 0
	assert weekly_schedule_excess([480] * 5 + [300, 0], rules) == 60


def test_madde_52_hard_harmful_six_hours(rules):
	hard = EmployeeFlags(hard_harmful=True)
	r = calculate_day(workday(), SHORT, punches("08:00", "14:00"), rules, hard)
	assert r.required_minutes == 360
	assert r.absence_minutes == r.early_leave_minutes == 0
	assert W_HARD_HARMFUL_LIMIT in r.warnings  # the 7 h 20 schedule itself is too long
	assert weekly_schedule_excess([360] * 6 + [0], rules, hard_harmful=True) == 0
	assert weekly_schedule_excess([440] * 6 + [0], rules, hard_harmful=True) == 480


def test_madde_53_night_is_22_to_06(rules):
	evening = Shift("Evening", start=hm("15:00"), end=hm("23:00"))
	r = calculate_day(workday(), evening, punches("15:00", "23:00"), rules)
	assert r.night_work_minutes == 60
	night = Shift("Night", start=hm("22:00"), end=hm("22:00") + 480)
	r = calculate_day(workday(), night, punches("22:00", "+06:00"), rules)
	assert r.night_work_minutes == 480
	assert r.required_minutes == 480 and r.absence_minutes == 0


def test_madde_54_span_over_fifteen_hours_warns(rules):
	r = calculate_day(workday(), OFFICE, punches("06:00", "12:00", "16:00", "21:30"), rules)
	assert W_SPAN in r.warnings
	r = calculate_day(workday(), OFFICE, punches("07:00", "12:00", "16:00", "21:30"), rules)
	assert W_SPAN not in r.warnings


def test_madde_55_56_rotation_premium_category(rules):
	assert rotation_premium([MORNING], rules) == (None, 0)
	assert rotation_premium([EVENING, EVENING], rules) == (None, 0)  # fixed evening is not shift work
	assert rotation_premium([MORNING, EVENING], rules) == ("Morning-Evening", 10)
	assert rotation_premium([MORNING, EVENING, NIGHT], rules) == ("Morning-Evening-Night", 15)
	assert rotation_premium([MORNING, NIGHT], rules) == ("With Night", 22.5)
	assert rotation_premium([EVENING, NIGHT], rules) == ("With Night", 22.5)
	assert shift_kind(Shift("m", hm("07:00"), hm("15:00"))) == MORNING
	assert shift_kind(Shift("e", hm("15:00"), hm("23:00"))) == EVENING
	assert shift_kind(Shift("n", hm("23:00"), hm("23:00") + 480)) == NIGHT


def test_madde_57_rotating_176_hours_in_four_weeks(rules):
	days = [(f"d{i:02d}", 480 if i % 4 != 3 else 0) for i in range(28)]  # 21 days x 8 h = 168 h
	assert rotating_four_week_excess(days, rules) == []
	days[3] = ("d03", 600)  # +10 h -> 178 h
	assert rotating_four_week_excess(days, rules) == [("d00", "d27", 178 * 60)]


def test_madde_58_night_premium_only_for_non_rotating(rules):
	evening = Shift("Evening", start=hm("15:00"), end=hm("23:00"))
	r = calculate_day(workday(), evening, punches("15:00", "23:00"), rules, EmployeeFlags(rotating=True))
	assert r.night_work_minutes == 0


def test_madde_59_overtime_needs_the_workers_consent(rules):
	r = calculate_day(workday(), SHORT, punches("08:00", "17:20"), rules)
	assert r.extra_minutes == 120
	assert r.total_overtime_minutes == 0 and r.unapproved_extra_minutes == 120
	assert W_UNAPPROVED_EXTRA in r.warnings
	r = calculate_day(workday(), SHORT, punches("08:00", "17:20"), rules, overtime=[OvertimeApproval(90)])
	assert r.overtime_minutes == {NORMAL: 90} and r.unapproved_extra_minutes == 30


def test_madde_59_standing_written_consent(rules):
	r = calculate_day(
		workday(), SHORT, punches("08:00", "17:20"), rules, EmployeeFlags(standing_overtime_consent=True)
	)
	assert r.overtime_minutes == {NORMAL: 120}


def test_madde_59_overtime_cap_four_hours(rules):
	r = calculate_day(workday(), SHORT, punches("08:00", "21:20"), rules, overtime=[OvertimeApproval(360)])
	assert r.overtime_minutes == {NORMAL: 240}
	assert r.unapproved_extra_minutes == 120
	assert W_OVERTIME_CAP in r.warnings


def test_madde_59_exceptional_overtime_by_agreement(rules):
	approvals = [OvertimeApproval(240), OvertimeApproval(120, EXCEPTIONAL)]
	r = calculate_day(workday(), SHORT, punches("08:00", "21:20"), rules, overtime=approvals)
	assert r.overtime_minutes == {NORMAL: 240, EXCEPTIONAL: 120}
	assert r.unapproved_extra_minutes == 0 and W_OVERTIME_CAP not in r.warnings


def test_madde_60_emergency_overtime_up_to_eight_hours(rules):
	r = calculate_day(
		workday(), SHORT, punches("08:00", "+01:20"), rules, overtime=[OvertimeApproval(600, EMERGENCY)]
	)
	assert r.extra_minutes == 600
	assert r.overtime_minutes == {EMERGENCY: 480}
	assert W_EMERGENCY_CAP in r.warnings


def test_madde_61_no_overtime_for_hard_harmful_work(rules):
	hard_six = Shift("Six", start=hm("08:00"), end=hm("14:00"))
	r = calculate_day(
		workday(),
		hard_six,
		punches("08:00", "16:00"),
		rules,
		EmployeeFlags(hard_harmful=True),
		overtime=[OvertimeApproval(120)],
	)
	assert r.total_overtime_minutes == 0
	assert W_NO_OVERTIME_HARD_HARMFUL in r.warnings


def test_madde_62_work_on_the_weekly_rest_day(rules):
	friday = Day("1405/07/17", weekday=6, day_type="Friday", rest_day=True)
	r = calculate_day(friday, OFFICE, punches("09:00", "13:00"), rules)
	assert r.status == REST
	assert r.rest_day_work_minutes == 240 and r.required_minutes == 0


def test_madde_62_note_1_friday_premium_when_another_day_is_the_rest_day(rules):
	# A cafe worker whose weekly rest is Tuesday works a normal Friday.
	friday = Day("1405/07/17", weekday=6, day_type="Friday", rest_day=False)
	r = calculate_day(friday, SHORT, punches("08:00", "15:20"), rules)
	assert r.friday_premium_minutes == 440 and r.rest_day_work_minutes == 0
	tuesday = Day("1405/07/14", weekday=3, day_type="Workday", rest_day=True)
	r = calculate_day(tuesday, SHORT, punches("08:00", "12:00"), rules)
	assert r.rest_day_work_minutes == 240 and r.friday_premium_minutes == 0


def test_madde_63_official_holiday_work_is_kept_apart_from_friday_work(rules):
	holiday = Day("1405/08/22", weekday=6, day_type="Official Holiday", rest_day=True)
	r = calculate_day(holiday, OFFICE, punches("08:00", "12:00"), rules)
	assert r.status == HOLIDAY
	assert r.holiday_work_minutes == 240 and r.rest_day_work_minutes == 0
	r = calculate_day(holiday, OFFICE, [], rules)
	assert r.required_minutes == 0 and r.absence_minutes == 0  # paid holiday, no absence


def test_madde_64_annual_leave_26_days_proportional(rules):
	assert annual_leave_entitlement(365, 365, rules) == 26
	assert annual_leave_entitlement(180, 365, rules) == round(26 * 180 / 365, 4)


def test_madde_64_holidays_inside_a_leave_are_not_leave(rules):
	holiday = Day("1405/04/03", weekday=3, day_type="Official Holiday")
	r = calculate_day(holiday, OFFICE, [], rules, absences=[Absence("Leave", "Earned")])
	assert r.leave_days == {} and r.status == HOLIDAY
	r = calculate_day(workday(), OFFICE, [], rules, absences=[Absence("Leave", "Earned")])
	assert r.status == LEAVE and r.leave_days == {"Earned": 1.0} and r.absence_minutes == 0


def test_madde_65_hard_harmful_five_weeks_of_leave(rules):
	assert annual_leave_entitlement(365, 365, rules, hard_harmful=True) == 30


def test_madde_66_carry_over_at_most_nine_days(rules):
	assert year_end_carry_over(12.5, rules) == (9, 3.5)
	assert year_end_carry_over(4, rules) == (4, 0)


def test_madde_70_hourly_leave_seven_hours_twenty_is_one_day(rules):
	assert hourly_leave_days(440, rules) == 1
	r = calculate_day(
		workday(),
		SHORT,
		punches("10:00", "15:20"),
		rules,
		absences=[Absence("Leave", "Earned", hm("08:00"), hm("10:00"))],
	)
	assert r.leave_minutes == {"Earned": 120}
	assert r.leave_days == {"Earned": round(120 / 440, 4)}
	assert r.late_minutes == 0 and r.absence_minutes == 0
	generous = replace(rules, hourly_leave_minutes_per_day=480)
	assert hourly_leave_days(240, generous) == 0.5


def test_madde_73_marriage_leave_is_its_own_type(rules):
	r = calculate_day(workday(), OFFICE, [], rules, absences=[Absence("Leave", "Marriage or Bereavement")])
	assert r.leave_days == {"Marriage or Bereavement": 1.0} and r.credited_minutes == r.required_minutes


def test_madde_78_nursing_break_counts_as_work(rules):
	# 440 required: two full 3-hour blocks earn 2 x 30 minutes, so leaving an hour early is fine.
	r = calculate_day(workday(), SHORT, punches("08:00", "14:20"), rules, EmployeeFlags(nursing=True))
	assert r.nursing_minutes == 60
	assert r.early_leave_minutes == 0 and r.absence_minutes == 0


def test_madde_83_young_worker_half_an_hour_less(rules):
	r = calculate_day(workday(), SHORT, punches("08:00", "14:50"), rules, EmployeeFlags(juvenile=True))
	assert r.required_minutes == 410
	assert r.early_leave_minutes == 0 and r.absence_minutes == 0


def test_madde_84_young_worker_no_overtime_no_night_work(rules):
	r = calculate_day(
		workday(),
		SHORT,
		punches("08:00", "23:00"),
		rules,
		EmployeeFlags(juvenile=True),
		overtime=[OvertimeApproval(120)],
	)
	assert r.total_overtime_minutes == 0
	assert W_NO_OVERTIME_JUVENILE in r.warnings and W_JUVENILE_NIGHT in r.warnings


def test_madde_27_absence_only_warns(rules):
	days = [
		("1405/07/01", True),
		("1405/07/02", True),
		("1405/07/03", True),
		("1405/07/04", False),
		("1405/07/05", True),
	]
	assert absence_streaks(days, threshold=3) == [("1405/07/01", "1405/07/03", 3)]
	assert absence_streaks(days, threshold=4) == []
	r = calculate_day(workday(), OFFICE, [], rules)
	assert r.status == ABSENT and r.absent_day  # recorded, nothing else happens


def test_rule_set_worse_than_the_law_is_rejected(rules):
	worse = replace(
		rules,
		max_daily_minutes=540,
		annual_leave_days=20,
		night_start_minute=hm("23:00"),
		hourly_leave_minutes_per_day=420,
	)
	names = {v[0] for v in violations(worse, rules)}
	assert names == {
		"max_daily_minutes",
		"annual_leave_days",
		"night_start_minute",
		"hourly_leave_minutes_per_day",
	}
	better = replace(
		rules,
		max_daily_minutes=450,
		annual_leave_days=30,
		night_start_minute=hm("21:00"),
		hourly_leave_minutes_per_day=480,
	)
	assert violations(better, rules) == []
