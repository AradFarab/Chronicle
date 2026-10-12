"""Suggested requests: what the day's punches and work pattern say the employee should ask for."""

from __future__ import annotations

from sqlalchemy import select

from chronicle.db.models import LeaveType, RequestSuggestion
from chronicle.services import leave, requests, suggestions
from tests.services.test_attendance import SUNDAY, calc, punch


def open_ones(org):
	return {
		s.request_type: s
		for s in org.db.scalars(
			select(RequestSuggestion).where(
				RequestSuggestion.employee_id == org.employee.id, RequestSuggestion.status == "open"
			)
		)
	}


def test_overtime_and_late_arrival_are_proposed_from_the_punches(org):
	"""08:00-16:30 office shift: in at 08:20 and out at 18:30."""
	punch(org, SUNDAY, "08:20")
	punch(org, SUNDAY, "18:30")
	calc(org, SUNDAY)
	found = {k: suggestions.view(v) for k, v in open_ones(org).items()}
	assert (found["overtime"]["from_time"], found["overtime"]["to_time"], found["overtime"]["minutes"]) == (
		"16:30",
		"18:30",
		120,
	)
	assert (found["hourly_leave"]["from_time"], found["hourly_leave"]["to_time"]) == ("08:00", "08:20")


def test_a_dismissed_suggestion_is_not_proposed_again(org):
	punch(org, SUNDAY, "08:00")
	punch(org, SUNDAY, "18:00")
	calc(org, SUNDAY)
	actor = org.emp
	overtime = open_ones(org)["overtime"]
	suggestions.dismiss(org.db, actor, overtime.id)
	calc(org, SUNDAY)
	assert "overtime" not in open_ones(org)
	assert org.db.get(RequestSuggestion, overtime.id).status == "dismissed"


def test_sending_a_suggestion_makes_a_real_request(org):
	punch(org, SUNDAY, "08:30")
	punch(org, SUNDAY, "16:30")
	calc(org, SUNDAY)
	late = open_ones(org)["hourly_leave"]
	earned = org.db.scalar(select(LeaveType).where(LeaveType.name == "استحقاقی"))
	leave.add_entry(org.db, org.employee.id, earned.id, leave.ALLOCATION, "1405/01/01", 5)
	actor = org.emp
	request = requests.submit(
		org.db,
		actor,
		"leave",
		{
			"leave_type_id": earned.id,
			"unit": "hourly",
			"jdate": SUNDAY,
			"from_time": "08:00",
			"to_time": "08:30",
			"suggestion_id": late.id,
		},
		SUNDAY,
	)
	org.db.refresh(late)
	assert late.status == "sent" and late.request_id == request.id


def test_a_missing_punch_proposes_a_correction(org):
	punch(org, SUNDAY, "08:00")
	calc(org, SUNDAY)
	assert "attendance_correction" in open_ones(org)


def test_someone_else_cannot_dismiss_my_suggestion(org):
	import pytest

	from chronicle.services.errors import PermissionDenied

	punch(org, SUNDAY, "08:00")
	calc(org, SUNDAY)
	other = org.anyone
	with pytest.raises(PermissionDenied):
		suggestions.dismiss(org.db, other, open_ones(org)["attendance_correction"].id)


def test_two_overtime_windows_give_two_suggestions_of_exactly_the_time_worked():
	from chronicle.engine.daily import calculate_day
	from chronicle.engine.model import Day, EmployeeFlags, Punch, Shift
	from chronicle.engine.rules import baseline_rule_set

	shift = Shift(
		"9-5",
		start=9 * 60,
		end=17 * 60,
		overtime_windows=((7 * 60, 8 * 60 + 30), (17 * 60, 19 * 60)),
	)
	punches = [Punch(7 * 60 * 60), Punch(18 * 60 * 60)]
	result = calculate_day(Day("1405/07/12", 1, "workday"), shift, punches, baseline_rule_set())
	found = [
		(p["from_minute"], p["to_minute"], p["minutes"])
		for p in suggestions.proposals(result, shift, EmployeeFlags())
		if p["request_type"] == "overtime"
	]
	assert found == [(420, 510, 90), (1020, 1080, 60)]
