"""When an SMS is sent: leave and correction decisions, requests waiting for a manager, and the
hourly checks. Without an active template for an event nothing is sent."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from orgfactory import TODAY
from sqlalchemy import select

from chronicle.db.models import LeaveType, SmsEvent, SmsMessage
from chronicle.services import attendance, leave, requests, sms, sms_dispatch, sms_triggers
from chronicle.sms.mock import MockDriver

TEHRAN = ZoneInfo("Asia/Tehran")


def at(hour, minute=0):
	return datetime(2026, 10, 19, hour, minute, tzinfo=TEHRAN)


@pytest.fixture(autouse=True)
def clean_mock(monkeypatch):
	MockDriver.sent.clear()
	monkeypatch.setattr(sms_dispatch, "now", lambda: at(12))
	monkeypatch.setattr(sms_triggers, "now", lambda: at(12))


@pytest.fixture
def panel(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {}, "is_primary": True})
	for person, number in (
		(org.employee, "09120000003"),
		(org.manager, "09120000001"),
		(org.ceo, "09120000002"),
	):
		person.mobile = number
	org.db.flush()


def template(org, event, body="{name} {date}"):
	sms.save_template(
		org.db, org.admin, {"event": event, "provider_code": "mock", "mode": "bulk", "body": body}
	)


def numbers(org, event):
	return [
		to
		for (to,) in org.db.execute(
			select(SmsMessage.to_number)
			.join(SmsEvent, SmsEvent.id == SmsMessage.event_id)
			.where(SmsEvent.code == event)
			.order_by(SmsMessage.id)
		)
	]


def daily_leave(org):
	earned = org.db.scalar(select(LeaveType).where(LeaveType.name == "استحقاقی"))
	leave.add_entry(org.db, org.employee.id, earned.id, leave.ALLOCATION, "1405/01/01", 10)
	values = {"leave_type_id": earned.id, "unit": "daily", "from_date": "1405/07/12", "to_date": "1405/07/12"}
	return requests.submit(org.db, org.emp, "leave", values, TODAY)


# requests -----------------------------------------------------------------------------------------


def test_a_leave_request_tells_each_step_in_turn_and_the_employee_the_result(org, panel):
	for event in ("leave_requested", "leave_approved", "leave_rejected"):
		template(org, event, "{name} {date} {leave_type}")
	r = daily_leave(org)  # manager, then CEO
	assert numbers(org, "leave_requested") == ["09120000001"]  # the manager first
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)
	assert numbers(org, "leave_requested") == ["09120000001", "09120000002"]  # then the CEO
	assert numbers(org, "leave_approved") == []
	requests.act(org.db, org.boss, r.id, "approve", None, TODAY)
	assert numbers(org, "leave_approved") == ["09120000003"]  # the employee


def test_a_rejection_tells_the_employee(org, panel):
	template(org, "leave_rejected", "{name} {leave_type}")
	r = daily_leave(org)
	requests.act(org.db, org.mgr, r.id, "reject", "no", TODAY)
	assert numbers(org, "leave_rejected") == ["09120000003"]


def test_a_punch_correction_result_goes_to_the_employee(org, panel):
	template(org, "correction_decided", "{name} {date} {status}")
	r = requests.submit(
		org.db,
		org.emp,
		"correction",
		{"jdate": "1405/07/13", "reason": "x", "items": [{"time": "08:00"}]},
		TODAY,
	)
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)
	assert numbers(org, "correction_decided") == ["09120000003"]
	msg = org.db.scalar(select(SmsMessage))
	assert msg.context["status"] == "تأیید شد"


def test_nothing_is_sent_without_a_template_or_a_number(org, panel):
	r = daily_leave(org)  # no template for any event
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)
	assert org.db.scalar(select(SmsMessage)) is None
	template(org, "leave_approved")
	org.employee.mobile = None
	org.db.flush()
	requests.act(org.db, org.boss, r.id, "approve", None, TODAY)
	assert org.db.scalar(select(SmsMessage)) is None


def test_a_decision_is_texted_once(org, panel):
	template(org, "leave_approved")
	r = daily_leave(org)
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)
	requests.act(org.db, org.boss, r.id, "approve", None, TODAY)
	sms_triggers.on_decided(org.db, r)  # asked again
	assert numbers(org, "leave_approved") == ["09120000003"]


# the hourly checks --------------------------------------------------------------------------------


def test_the_shift_of_tomorrow_is_reminded_in_the_evening_only(org, panel, monkeypatch):
	template(org, "shift_reminder", "{name} {date} {time} {shift}")
	monkeypatch.setattr(sms_triggers, "now", lambda: at(10))
	assert sms_triggers.shift_reminders(org.db, TODAY) == 0  # too early
	monkeypatch.setattr(sms_triggers, "now", lambda: at(18))
	assert sms_triggers.shift_reminders(org.db, TODAY) >= 1  # tomorrow (Wednesday) is a working day
	assert "09120000003" in numbers(org, "shift_reminder")
	before = len(numbers(org, "shift_reminder"))
	sms_triggers.shift_reminders(org.db, TODAY)
	assert len(numbers(org, "shift_reminder")) == before  # once per person and day
	text = next(m for m in org.db.scalars(select(SmsMessage)) if m.to_number == "09120000003")
	assert text.context["time"] == "۰۸:۰۰" and text.context["shift"] == "T-Office"


def test_a_forgotten_entry_is_noticed_an_hour_into_the_shift(org, panel, monkeypatch):
	template(org, "missed_check_in", "{name} {time}")
	monkeypatch.setattr(sms_triggers, "now", lambda: at(8, 30))
	assert sms_triggers.missed_check_in(org.db, TODAY) == 0  # only half an hour in
	monkeypatch.setattr(sms_triggers, "now", lambda: at(10))
	sms_triggers.missed_check_in(org.db, TODAY)
	assert "09120000003" in numbers(org, "missed_check_in")


def test_yesterdays_absence_goes_to_the_manager(org, panel):
	template(org, "absence_notice", "{name} {date}")
	attendance.recalculate(org.db, ["1405/07/13"], TODAY, "t", [org.employee.id])
	sms_triggers.previous_day_notices(org.db, TODAY)
	assert numbers(org, "absence_notice") == ["09120000001"]  # the employee's manager
	sms_triggers.previous_day_notices(org.db, TODAY)
	assert numbers(org, "absence_notice") == ["09120000001"]


def test_birthdays_are_congratulated_once_a_year(org, panel):
	template(org, "birthday", "{name}")
	org.employee.birth_date = "1380/07/14"
	org.db.flush()
	assert sms_triggers.birthdays(org.db, TODAY) == 1
	assert sms_triggers.birthdays(org.db, TODAY) == 0
	assert numbers(org, "birthday") == ["09120000003"]


def test_the_monthly_summary_links_to_the_month_page(org, panel):
	template(org, "monthly_summary", "{name} {month} {hours} {link_path}")
	attendance.recalculate(org.db, ["1405/07/12", "1405/07/13"], TODAY, "t", [org.employee.id])
	assert sms_triggers.monthly_summaries(org.db, "1405/08/02") == 1
	msg = org.db.scalar(select(SmsMessage))
	assert msg.context["month"].startswith("مهر") and msg.context["link_path"].startswith("l/")
	assert sms_triggers.monthly_summaries(org.db, "1405/08/10") == 0  # only in the first days


def test_one_failing_check_does_not_stop_the_others(org, panel, monkeypatch):
	template(org, "birthday", "{name}")
	org.employee.birth_date = "1380/07/14"
	org.db.flush()

	def boom(session, today):
		raise RuntimeError("bug")

	monkeypatch.setattr(sms_triggers, "shift_reminders", boom)
	result = sms_triggers.run_periodic(org.db, TODAY)
	assert result["boom"] == -1 and result["birthdays"] == 1
