"""Daily attendance calculation. Pure Python: no database or web imports.

calculate_day(day, shift, punches, rules, employee, absences, overtime) -> DailyResult

The engine only classifies time; it never computes money. Every legal number comes from
the RuleSet. Rounding is always in the worker's favour: a work interval starts at the
minute the punch fell in and ends at the next full minute.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from hozur.engine.model import (
	ABSENT,
	COMPANY_HOLIDAY,
	EMERGENCY,
	EXCEPTIONAL,
	HOLIDAY,
	INCOMPLETE,
	LEAVE,
	MISSION,
	NORMAL,
	OFF,
	OFFICIAL_HOLIDAY,
	PRESENT,
	REST,
	Absence,
	DailyResult,
	Day,
	EmployeeFlags,
	OvertimeApproval,
	Punch,
	Shift,
)
from hozur.engine.rules import RuleSet

FRIDAY_WEEKDAY = 6
IN, OUT = "in", "out"
NO_FLAGS = EmployeeFlags()

# Warning codes (Daily Attendance.warnings). The article is in the name where there is one.
W_MISSING_PUNCH = "MISSING_PUNCH"
W_SPAN = "ARTICLE_54_SPAN_EXCEEDED"
W_DAILY_LIMIT = "ARTICLE_51_SCHEDULE_OVER_DAILY_LIMIT"
W_HARD_HARMFUL_LIMIT = "ARTICLE_52_SCHEDULE_OVER_HARD_HARMFUL_LIMIT"
W_OVERTIME_CAP = "ARTICLE_59_OVERTIME_CAP"
W_EMERGENCY_CAP = "ARTICLE_60_EMERGENCY_CAP"
W_NO_OVERTIME_HARD_HARMFUL = "ARTICLE_61_NO_OVERTIME_HARD_HARMFUL"
W_NO_OVERTIME_JUVENILE = "ARTICLE_84_NO_OVERTIME_JUVENILE"
W_JUVENILE_NIGHT = "ARTICLE_84_NO_NIGHT_WORK_JUVENILE"
W_UNAPPROVED_EXTRA = "UNAPPROVED_EXTRA_WORK"
W_OUTSIDE_OVERTIME_WINDOW = "EXTRA_WORK_OUTSIDE_OVERTIME_WINDOW"
LATER = 10**6  # an open end for "after the shift" windows

Interval = tuple[int, int]


# interval arithmetic --------------------------------------------------------------


def merge(intervals: Iterable[Interval]) -> list[Interval]:
	out: list[list[int]] = []
	for a, b in sorted(i for i in intervals if i[1] > i[0]):
		if out and a <= out[-1][1]:
			out[-1][1] = max(out[-1][1], b)
		else:
			out.append([a, b])
	return [(a, b) for a, b in out]


def total(intervals: Iterable[Interval]) -> int:
	return sum(b - a for a, b in intervals)


def clip(intervals: Iterable[Interval], window: Interval | None) -> list[Interval]:
	if window is None:
		return []
	lo, hi = window
	return [(max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo)]


def subtract(intervals: Iterable[Interval], removed: Iterable[Interval]) -> list[Interval]:
	result = merge(intervals)
	for r_lo, r_hi in merge(removed):
		nxt = []
		for a, b in result:
			if r_hi <= a or r_lo >= b:
				nxt.append((a, b))
				continue
			if a < r_lo:
				nxt.append((a, r_lo))
			if r_hi < b:
				nxt.append((r_hi, b))
		result = nxt
	return result


def overlap(intervals: Iterable[Interval], window: Interval | None) -> int:
	return total(clip(intervals, window))


# punches ----------------------------------------------------------------------------


def _minute_interval(start_second: int, end_second: int) -> Interval:
	"""In the worker's favour: floor the start, ceil the end."""
	return (start_second // 60, -(-end_second // 60))


def pair_punches(punches: Sequence[Punch]) -> tuple[list[Interval], bool]:
	"""Work intervals from punches, and whether a punch was left without its pair.

	When every punch has a direction, runs are collapsed in the worker's favour (the
	earliest of consecutive Ins, the latest of consecutive Outs). Otherwise punches are
	paired in order: 1st-2nd, 3rd-4th, ..."""
	ordered = sorted(punches, key=lambda p: p.second)
	intervals: list[Interval] = []
	missing = False
	if ordered and all(p.direction in (IN, OUT) for p in ordered):
		open_at = None
		for p in ordered:
			if p.direction == IN:
				if open_at is None:
					open_at = p.second
			elif open_at is not None:
				intervals.append(_minute_interval(open_at, p.second))
				open_at = None
			elif intervals:
				a, _ = intervals[-1]
				intervals[-1] = (a, -(-p.second // 60))  # a later Out extends the last interval
			else:
				missing = True  # an Out with no In before it
		missing = missing or open_at is not None
	else:
		for i in range(0, len(ordered) - 1, 2):
			intervals.append(_minute_interval(ordered[i].second, ordered[i + 1].second))
		missing = len(ordered) % 2 == 1
	return merge(intervals), missing


# the day ----------------------------------------------------------------------------


def _night_windows(rules: RuleSet) -> list[Interval]:
	start, end = rules.night_start_minute, rules.night_end_minute
	return [(start - 1440, end), (start, end + 1440), (start + 1440, end + 2880)]


def _allocate_overtime(
	result: DailyResult, extra: int, rules: RuleSet, employee: EmployeeFlags, approvals
) -> None:
	authorized = {NORMAL: 0, EXCEPTIONAL: 0, EMERGENCY: 0}
	for a in approvals:
		authorized[a.kind] = authorized.get(a.kind, 0) + a.minutes
	if employee.standing_overtime_consent:
		authorized[NORMAL] = max(authorized[NORMAL], rules.overtime_daily_cap_minutes)
	result.extra_minutes = extra
	if extra <= 0:
		return
	if employee.hard_harmful or employee.juvenile:
		# Article 61 (hard and harmful work) and Article 84 (young workers): no overtime at all.
		if any(authorized.values()):
			result.warnings.append(
				W_NO_OVERTIME_HARD_HARMFUL if employee.hard_harmful else W_NO_OVERTIME_JUVENILE
			)
		result.unapproved_extra_minutes = extra
		return
	remaining = extra
	cap = rules.overtime_daily_cap_minutes
	normal = min(remaining, authorized[NORMAL], cap)
	if authorized[NORMAL] > cap and remaining > cap and not authorized[EXCEPTIONAL]:
		result.warnings.append(W_OVERTIME_CAP)
	remaining -= normal
	exceptional = min(remaining, authorized[EXCEPTIONAL])
	remaining -= exceptional
	emergency = min(remaining, authorized[EMERGENCY], rules.emergency_overtime_cap_minutes)
	if (
		authorized[EMERGENCY] > rules.emergency_overtime_cap_minutes
		and remaining > rules.emergency_overtime_cap_minutes
	):
		result.warnings.append(W_EMERGENCY_CAP)
	remaining -= emergency
	result.overtime_minutes = {
		k: v for k, v in ((NORMAL, normal), (EXCEPTIONAL, exceptional), (EMERGENCY, emergency)) if v
	}
	result.unapproved_extra_minutes = remaining
	if remaining:
		result.warnings.append(W_UNAPPROVED_EXTRA)


def calculate_day(
	day: Day,
	shift: Shift | None,
	punches: Sequence[Punch],
	rules: RuleSet,
	employee: EmployeeFlags = NO_FLAGS,
	absences: Sequence[Absence] = (),
	overtime: Sequence[OvertimeApproval] = (),
) -> DailyResult:
	intervals, missing = pair_punches(punches)
	holiday = day.day_type in (OFFICIAL_HOLIDAY, COMPANY_HOLIDAY)
	scheduled = shift is not None and not holiday and not day.rest_day
	result = DailyResult(jdate=day.jdate, status=OFF, shift=shift.name if shift else None)
	if missing:
		result.warnings.append(W_MISSING_PUNCH)

	breaks = shift.break_list if shift else []
	work = subtract(intervals, breaks if scheduled else [])
	worked = total(work)
	if scheduled and shift.flexible and not breaks and shift.break_minutes and worked > shift.break_minutes:
		worked -= shift.break_minutes
	result.worked_minutes = worked
	if intervals:
		result.first_in, result.last_out = intervals[0][0], intervals[-1][1]
		if result.last_out - result.first_in > rules.intermittent_span_minutes:
			result.warnings.append(W_SPAN)  # Article 54

	# Night work (Articles 53, 58): non-rotating workers only; rotating workers get the shift premium.
	night = sum(overlap(work, w) for w in _night_windows(rules))
	if night and employee.juvenile:
		result.warnings.append(W_JUVENILE_NIGHT)  # Article 84
	if not employee.rotating:
		result.night_work_minutes = night

	if not scheduled:
		result.status = HOLIDAY if holiday else (REST if day.rest_day else OFF)
		if day.day_type == OFFICIAL_HOLIDAY:
			result.holiday_work_minutes = worked  # Article 63
		elif day.day_type == COMPANY_HOLIDAY:
			result.company_holiday_work_minutes = worked
		elif day.rest_day:
			result.rest_day_work_minutes = worked  # Article 62
		result.overtime_intervals = work
		_allocate_overtime(result, worked, rules, employee, overtime)
		return result

	# Scheduled workday --------------------------------------------------------------
	if day.weekday == FRIDAY_WEEKDAY:
		# LEGAL-CHECK: Article 62 note 1 - when another day is the weekly rest day, work on
		# Friday earns the Friday premium.
		result.friday_premium_minutes = worked

	shift_required = shift.scheduled_minutes
	required = shift_required
	if employee.hard_harmful:
		if shift_required > rules.hard_harmful_daily_minutes:
			result.warnings.append(W_HARD_HARMFUL_LIMIT)  # Article 52
		required = min(required, rules.hard_harmful_daily_minutes)
	elif shift_required > rules.max_daily_minutes:
		result.warnings.append(W_DAILY_LIMIT)  # Article 51
	if employee.juvenile:
		required = max(0, required - rules.juvenile_daily_reduction_minutes)  # Article 83
	result.required_minutes = required

	reduction = shift_required - required
	start = shift.start
	end = shift.end - (0 if shift.flexible else reduction)
	window = (start, end)

	nursing = 0
	if employee.nursing and rules.nursing_every_minutes:
		nursing = (required // rules.nursing_every_minutes) * rules.nursing_break_minutes  # Article 78
	result.nursing_minutes = nursing

	daily = [a for a in absences if a.daily]
	if daily:
		absence = next((a for a in daily if a.kind == "mission"), daily[0])
		if absence.kind == "mission":
			result.status, result.mission_minutes = MISSION, required
		else:
			result.status = LEAVE
			result.leave_minutes[absence.type] = required
			result.leave_days[absence.type] = 1.0
		result.credited_minutes = required if absence.paid or absence.kind == "mission" else 0
		result.overtime_intervals = work
		_allocate_overtime(result, worked, rules, employee, overtime)
		return result

	work_in = clip(work, window)
	excused: list[Interval] = []
	paid_minutes = unpaid_minutes = 0
	for a in absences:
		piece = subtract(clip([(a.start, a.end)], window), work_in + breaks)
		minutes = total(piece)
		if not minutes:
			continue
		excused += piece
		if a.kind == "mission":
			result.mission_minutes += minutes
			paid_minutes += minutes
		else:
			result.leave_minutes[a.type] = result.leave_minutes.get(a.type, 0) + minutes
			result.leave_days[a.type] = round(
				result.leave_minutes[a.type] / rules.hourly_leave_minutes_per_day, 4
			)  # Article 70
			if a.paid:
				paid_minutes += minutes
			else:
				unpaid_minutes += minutes
	covered = merge(work_in + excused)
	worked_in = total(work_in)
	if shift.flexible and not breaks and shift.break_minutes and worked_in > shift.break_minutes:
		worked_in -= shift.break_minutes

	if not covered:
		result.status = ABSENT
		result.absent_day = True
		result.absence_minutes = required
		result.nursing_minutes = 0
		_extra_work(result, shift, work, [], rules, employee, overtime)
		return result

	# Lateness and early leave: uncovered time at the edges of the schedule.
	late_anchor = shift.latest_start if (shift.flexible and shift.latest_start is not None) else start
	late_raw = max(0, covered[0][0] - late_anchor)
	forgiven = 0
	if late_raw <= shift.grace_late:
		forgiven += late_raw
		late_raw = 0
	result.late_minutes = late_raw
	if shift.flexible:
		early_raw = 0
	else:
		early_raw = max(0, end - covered[-1][1])
		if early_raw <= shift.grace_early:
			forgiven += early_raw
			early_raw = 0
	result.early_leave_minutes = early_raw

	credited = worked_in + paid_minutes + nursing + forgiven
	deficit = max(0, required - credited - unpaid_minutes)
	# Credits that are not at the edges (nursing breaks) offset late arrival / early leave:
	# late + early + absence always equals the real shortfall.
	excess = result.late_minutes + result.early_leave_minutes - deficit
	if excess > 0:
		cut = min(result.early_leave_minutes, excess)
		result.early_leave_minutes -= cut
		result.late_minutes -= min(result.late_minutes, excess - cut)
	result.absence_minutes = max(0, deficit - result.late_minutes - result.early_leave_minutes)
	result.credited_minutes = min(required, credited)
	result.status = INCOMPLETE if missing else PRESENT

	surplus = max(0, worked_in - required) if shift.flexible else 0
	_extra_work(result, shift, subtract(work, [window]), _tail(work_in, surplus), rules, employee, overtime)
	return result


def _tail(intervals: list[Interval], minutes: int) -> list[Interval]:
	"""The last `minutes` of the intervals (a flexible shift's work beyond the required time)."""
	out: list[Interval] = []
	for a, b in reversed(intervals):
		if minutes <= 0:
			break
		take = min(minutes, b - a)
		out.append((b - take, b))
		minutes -= take
	return sorted(out)


def _extra_work(
	result: DailyResult,
	shift: Shift,
	outside: list[Interval],
	surplus: list[Interval],
	rules: RuleSet,
	employee: EmployeeFlags,
	overtime: Sequence[OvertimeApproval],
) -> None:
	"""Work outside the schedule on a scheduled day.

	Work after the end that is no longer than the shift's tolerance is ignored; longer, and the
	whole of it counts. When the shift has overtime windows, only extra work inside them can
	become overtime (still only with approval); the rest stays unapproved extra work."""
	after = clip(outside, (shift.end, LATER))
	if after and total(after) <= shift.overtime_after:
		outside = subtract(outside, [(shift.end, LATER)])
	extra = merge(outside + surplus)
	if shift.overtime_windows:
		eligible = merge(p for w in shift.overtime_windows for p in clip(extra, w))
	else:
		eligible = extra
	beyond = total(extra) - total(eligible)
	result.overtime_intervals = eligible
	_allocate_overtime(result, total(eligible), rules, employee, overtime)
	if beyond:
		result.extra_minutes += beyond
		result.unapproved_extra_minutes += beyond
		result.outside_window_minutes = beyond
		result.warnings.append(W_OUTSIDE_OVERTIME_WINDOW)
		if W_UNAPPROVED_EXTRA not in result.warnings:
			result.warnings.append(W_UNAPPROVED_EXTRA)
