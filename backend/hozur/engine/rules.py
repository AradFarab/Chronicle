"""Labor rule parameters (CLAUDE.md rule 2). Pure Python: must not import frappe.

The legal values themselves are data (data/labor_law_1369.json, seeded as the read-only
baseline Labor Rule Set). This module only knows, for each parameter, in which direction a
change is better for the worker, so that a company rule set can be checked against the
baseline: a "max" parameter may only go down, a "min" parameter may only go up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

BASELINE_FILE = Path(__file__).parent / "data" / "labor_law_1369.json"

MAX, MIN = "max", "min"  # value may only decrease / only increase relative to the law


@dataclass(frozen=True)
class Parameter:
	name: str
	direction: str
	article: str
	unit: str
	legal_check: bool = False  # † in the labor-law file: not yet verified against the official text


PARAMETERS: tuple[Parameter, ...] = (
	Parameter("max_daily_minutes", MAX, "51", "minutes"),
	Parameter("max_weekly_minutes", MAX, "51 note 1", "minutes"),
	Parameter("hard_harmful_daily_minutes", MAX, "52", "minutes"),
	Parameter("hard_harmful_weekly_minutes", MAX, "52", "minutes"),
	Parameter("intermittent_span_minutes", MAX, "54", "minutes"),
	Parameter("rotating_four_week_minutes", MAX, "57", "minutes"),
	Parameter("night_start_minute", MAX, "53", "minute of day", legal_check=True),
	Parameter("night_end_minute", MIN, "53", "minute of day", legal_check=True),
	Parameter("overtime_daily_cap_minutes", MAX, "59 note", "minutes"),
	Parameter("emergency_overtime_cap_minutes", MAX, "60", "minutes"),
	Parameter("overtime_premium_percent", MIN, "59", "percent"),
	Parameter("night_premium_percent", MIN, "58", "percent"),
	Parameter("rest_day_premium_percent", MIN, "62 note 1", "percent"),
	Parameter("shift_premium_two_percent", MIN, "55", "percent"),
	Parameter("shift_premium_three_percent", MIN, "55", "percent"),
	Parameter("shift_premium_night_percent", MIN, "55", "percent"),
	Parameter("annual_leave_days", MIN, "64", "working days"),
	Parameter("hard_harmful_annual_leave_weeks", MIN, "65", "weeks"),
	Parameter("leave_carry_over_days", MIN, "66", "working days"),
	Parameter("hajj_leave_days", MIN, "67", "days"),
	Parameter("hourly_leave_minutes_per_day", MIN, "70", "minutes"),
	Parameter("marriage_bereavement_leave_days", MIN, "73", "days"),
	Parameter("maternity_leave_days", MIN, "76", "days"),
	Parameter("maternity_multiple_birth_extra_days", MIN, "76", "days"),
	Parameter("paternity_leave_days", MIN, "population laws", "days", legal_check=True),
	Parameter("nursing_break_minutes", MIN, "78", "minutes", legal_check=True),
	Parameter("nursing_every_minutes", MAX, "78", "minutes", legal_check=True),
	Parameter("nursing_child_max_months", MIN, "78", "months", legal_check=True),
	Parameter("juvenile_daily_reduction_minutes", MIN, "83", "minutes", legal_check=True),
	Parameter("juvenile_max_age_years", MIN, "79-84", "years", legal_check=True),
)
PARAMETER_BY_NAME = {p.name: p for p in PARAMETERS}


@dataclass(frozen=True)
class RuleSet:
	max_daily_minutes: int
	max_weekly_minutes: int
	hard_harmful_daily_minutes: int
	hard_harmful_weekly_minutes: int
	intermittent_span_minutes: int
	rotating_four_week_minutes: int
	night_start_minute: int
	night_end_minute: int
	overtime_daily_cap_minutes: int
	emergency_overtime_cap_minutes: int
	overtime_premium_percent: float
	night_premium_percent: float
	rest_day_premium_percent: float
	shift_premium_two_percent: float
	shift_premium_three_percent: float
	shift_premium_night_percent: float
	annual_leave_days: float
	hard_harmful_annual_leave_weeks: float
	leave_carry_over_days: float
	hajj_leave_days: int
	hourly_leave_minutes_per_day: int
	marriage_bereavement_leave_days: int
	maternity_leave_days: int
	maternity_multiple_birth_extra_days: int
	paternity_leave_days: int
	nursing_break_minutes: int
	nursing_every_minutes: int
	nursing_child_max_months: int
	juvenile_daily_reduction_minutes: int
	juvenile_max_age_years: int

	@classmethod
	def from_mapping(cls, data: dict) -> RuleSet:
		missing = [f.name for f in fields(cls) if data.get(f.name) is None]
		if missing:
			raise ValueError(f"rule set is missing: {', '.join(missing)}")
		return cls(**{f.name: data[f.name] for f in fields(cls)})

	def as_dict(self) -> dict:
		return {f.name: getattr(self, f.name) for f in fields(self)}


assert {f.name for f in fields(RuleSet)} == set(PARAMETER_BY_NAME), "RuleSet and PARAMETERS must match"


def load_baseline() -> dict:
	"""The Iranian Labor Law 1369 values with their articles (see the JSON file)."""
	return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def baseline_rule_set() -> RuleSet:
	return RuleSet.from_mapping({k: v["value"] for k, v in load_baseline()["parameters"].items()})


def violations(company: RuleSet, legal: RuleSet) -> list[tuple[str, object, object]]:
	"""Parameters where the company value is worse for the worker than the law:
	(name, company value, legal value)."""
	out = []
	for p in PARAMETERS:
		value, floor = getattr(company, p.name), getattr(legal, p.name)
		if (p.direction == MAX and value > floor) or (p.direction == MIN and value < floor):
			out.append((p.name, value, floor))
	return out
