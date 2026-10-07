"""Rules that look at more than one day. Pure Python: must not import frappe."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from hozur.engine.model import Shift
from hozur.engine.rules import RuleSet

MORNING, EVENING, NIGHT = "Morning", "Evening", "Night"


def shift_kind(shift: Shift) -> str:
	"""Morning starts 06-14, evening 14-22, night 22-06 (by start time)."""
	start = shift.start % 1440
	if 360 <= start < 840:
		return MORNING
	if 840 <= start < 1320:
		return EVENING
	return NIGHT


def rotation_premium(kinds: Iterable[str], rules: RuleSet) -> tuple[str | None, float]:
	"""Articles 55-56: the shift-work category of a month from the kinds of shifts worked.
	A fixed shift (one kind) is not shift work, even a fixed evening shift."""
	kinds = set(kinds)
	if len(kinds) < 2:
		return None, 0
	if kinds == {MORNING, EVENING}:
		return "Morning-Evening", rules.shift_premium_two_percent
	if kinds == {MORNING, EVENING, NIGHT}:
		return "Morning-Evening-Night", rules.shift_premium_three_percent
	return "With Night", rules.shift_premium_night_percent  # morning+night or evening+night


def rotating_four_week_excess(days: Sequence[tuple[str, int]], rules: RuleSet) -> list[tuple[str, str, int]]:
	"""Article 57: for consecutive days [(jdate, worked minutes), ...] in order, every 28-day
	window whose total exceeds the limit: (first day, last day, minutes)."""
	out = []
	for i in range(0, max(0, len(days) - 27)):
		window = days[i : i + 28]
		minutes = sum(m for _, m in window)
		if minutes > rules.rotating_four_week_minutes:
			out.append((window[0][0], window[-1][0], minutes))
	return out


def weekly_schedule_excess(daily_minutes: Sequence[int], rules: RuleSet, hard_harmful: bool = False) -> int:
	"""Article 51 note 1 / Article 52: minutes a 7-day schedule exceeds the weekly limit by."""
	limit = rules.hard_harmful_weekly_minutes if hard_harmful else rules.max_weekly_minutes
	return max(0, sum(daily_minutes) - limit)


def annual_leave_entitlement(
	service_days: int, year_days: int, rules: RuleSet, hard_harmful: bool = False
) -> float:
	"""Article 64 (and 65 for hard and harmful work): leave days earned for the days worked in
	a year; less than a full year earns a proportional share."""
	# LEGAL-CHECK: Article 65 - 5 weeks counted as 6 working days per week.
	full = rules.hard_harmful_annual_leave_weeks * 6 if hard_harmful else rules.annual_leave_days
	if year_days <= 0:
		return 0.0
	return round(full * min(service_days, year_days) / year_days, 4)


def hourly_leave_days(minutes: int, rules: RuleSet) -> float:
	"""Article 70: hourly leave is earned leave; this many minutes make one day."""
	return round(minutes / rules.hourly_leave_minutes_per_day, 4)


def year_end_carry_over(balance_days: float, rules: RuleSet) -> tuple[float, float]:
	"""Article 66: at year end at most this many days carry over; the rest expires.
	Returns (carried, expired)."""
	carried = min(max(balance_days, 0.0), rules.leave_carry_over_days)
	return carried, round(max(balance_days, 0.0) - carried, 4)


def absence_streaks(days: Sequence[tuple[str, bool]], threshold: int) -> list[tuple[str, str, int]]:
	"""Consecutive unexcused absent days of at least `threshold` days: (first, last, count).

	Only ever used for a disciplinary *warning*. Article 27 contains no number of absent days
	that ends a contract, so nothing here dismisses anyone (CLAUDE.md rule 7)."""
	out, run = [], []
	for jdate, absent in [*days, ("", False)]:
		if absent:
			run.append(jdate)
			continue
		if threshold > 0 and len(run) >= threshold:
			out.append((run[0], run[-1], len(run)))
		run = []
	return out
