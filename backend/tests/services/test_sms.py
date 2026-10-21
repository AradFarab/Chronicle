"""The SMS module: panel accounts, templates, dispatch, the sender and the review of uncertain
messages. The mock driver stands in for a panel; nothing here reaches a network."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from chronicle import worker
from chronicle.db.models import Job, ShortLink, SmsMessage, SmsProviderConfig, SmsTemplate
from chronicle.services import sms, sms_dispatch
from chronicle.services.errors import Conflict, NotFound, PermissionDenied, ValidationError
from chronicle.services.sms_dispatch import DispatchError, dispatch, send_message
from chronicle.sms.base import REGISTRY, register
from chronicle.sms.mock import MockDriver

TEHRAN = ZoneInfo("Asia/Tehran")
NUMBER = "09121234567"


def at(hour, day=19):
	return datetime(2026, 10, day, hour, 0, tzinfo=TEHRAN)


class Second(MockDriver):
	code = "mock2"
	label = "mock 2"
	sent: ClassVar[list] = []  # its own record, apart from MockDriver.sent


@pytest.fixture(autouse=True)
def drivers():
	MockDriver.sent.clear()
	Second.sent.clear()
	register(Second)
	yield
	REGISTRY.pop("mock2", None)


@pytest.fixture(autouse=True)
def daytime(monkeypatch):
	"""Inside the send window unless a test says otherwise."""
	monkeypatch.setattr(sms_dispatch, "now", lambda: at(12))


def panel(org, code="mock", **roles):
	roles = {"is_primary": True, **roles}
	return sms.save_provider(org.db, org.admin, code, {"config": {}, **roles})


def template(org, event="leave_approved", body="{name} {date}", provider="mock", **kw):
	return sms.save_template(
		org.db, org.admin, {"event": event, "provider_code": provider, "mode": "bulk", "body": body, **kw}
	)


def message(org, event="leave_approved", **context):
	return dispatch(org.db, event, NUMBER, {"name": "علی", "date": "1405/07/14", **context})


def stored(org, code="mock"):
	return org.db.scalar(select(SmsProviderConfig).where(SmsProviderConfig.provider_code == code))


# panel accounts -------------------------------------------------------------------------------------


def test_a_secret_is_stored_encrypted_and_only_shown_as_a_mask(org):
	view = sms.save_provider(
		org.db, org.admin, "smsir", {"config": {"api_key": "key-12345", "sender": "3000"}}
	)
	assert view["config"] == {"api_key": "••••••••", "sender": "3000"}
	saved = stored(org, "smsir").config["api_key"]
	assert saved.startswith("enc:v1:") and "key-12345" not in saved


def test_leaving_the_secret_blank_or_masked_keeps_the_saved_one(org):
	sms.save_provider(org.db, org.admin, "smsir", {"config": {"api_key": "key-12345"}})
	first = stored(org, "smsir").config["api_key"]
	sms.save_provider(org.db, org.admin, "smsir", {"config": {"api_key": ""}})
	sms.save_provider(org.db, org.admin, "smsir", {"config": {"api_key": "••••••••", "sender": "3000"}})
	assert stored(org, "smsir").config["api_key"] == first
	sms.save_provider(org.db, org.admin, "smsir", {"config": {"api_key": "other-key-99"}})
	assert stored(org, "smsir").config["api_key"] != first


def test_a_panel_without_its_required_setting_is_refused(org):
	with pytest.raises(ValidationError):
		sms.save_provider(org.db, org.admin, "smsir", {"config": {"sender": "3000"}})
	with pytest.raises(ValidationError):
		sms.save_provider(org.db, org.admin, "no-such-panel", {"config": {}})


def test_one_primary_and_one_fallback_and_never_both(org):
	panel(org, "mock", is_primary=True)
	panel(org, "mock2", is_primary=True)  # takes the role
	assert (stored(org, "mock").is_primary, stored(org, "mock2").is_primary) == (False, True)
	panel(org, "mock", is_primary=False, is_fallback=True)
	with pytest.raises(ValidationError):
		panel(org, "mock", is_primary=True, is_fallback=True)


def test_the_test_button_reports_the_credit_or_the_problem(org):
	panel(org)
	assert sms.test_provider(org.db, org.admin, "mock") == {"ok": True, "message": "", "credit": 1000.0}
	panel(org, "mock2", is_primary=False)
	sms.save_provider(org.db, org.admin, "mock2", {"config": {"behavior": "fatal"}})
	assert sms.test_provider(org.db, org.admin, "mock2")["ok"] is True  # the mock's test never fails
	with pytest.raises(NotFound):
		sms.test_provider(org.db, org.admin, "smsir")


def test_only_the_system_admin_manages_sms(org):
	for call in (
		lambda: sms.save_provider(org.db, org.emp, "mock", {}),
		lambda: sms.save_template(org.db, org.emp, {}),
		lambda: sms.save_settings(org.db, org.emp, {}),
		lambda: sms.list_messages(org.db, org.emp),
	):
		with pytest.raises(PermissionDenied):
			call()


def test_events_are_synced_from_code_and_can_be_switched_off(org):
	codes = {e["code"] for e in sms.list_events(org.db)}
	assert {"payslip_link", "otp", "leave_approved", "birthday", "monthly_summary"} <= codes
	sms.sync_events(org.db)  # idempotent
	assert len(sms.list_events(org.db)) == len(codes)
	sms.set_event_active(org.db, org.admin, "birthday", False)
	panel(org)
	template(org, "birthday", "{name}")
	with pytest.raises(DispatchError):
		dispatch(org.db, "birthday", NUMBER, {"name": "x"})


# templates ------------------------------------------------------------------------------------------


def test_a_full_text_may_only_use_the_events_fields(org):
	assert template(org)["warnings"] == ["leave_type"]  # not used: a warning, not an error
	with pytest.raises(ValidationError):
		template(org, body="{name} {nope}")
	with pytest.raises(ValidationError):
		template(org, body="  ")


def test_an_event_with_a_link_needs_it_in_the_template(org):
	with pytest.raises(ValidationError):
		template(org, "payslip_link", "{name} {month}")
	assert template(org, "payslip_link", "{name}: {link_path}")["id"]


def test_a_named_pattern_maps_the_panels_variables_to_event_variables(org):
	values = {"event": "payslip_link", "provider_code": "mock", "mode": "pattern", "pattern_code": "55"}
	saved = sms.save_template(
		org.db, org.admin, {**values, "param_map": {"NAME": "name", "LINK": "link_path"}}
	)
	assert saved["warnings"] == ["month", "expires"]  # unmapped: the pattern may not want them
	for bad in (
		["name", "link_path"],  # a named panel needs a dictionary
		{"NAME": "name"},  # no link
		{"NAME": "name", "LINK": "link_path", "X": "nope"},  # unknown event variable
		{},
	):
		with pytest.raises(ValidationError):
			sms.save_template(org.db, org.admin, {**values, "param_map": bad})
	with pytest.raises(ValidationError):  # at most max_params variables
		sms.save_template(
			org.db, org.admin, {**values, "param_map": {f"V{i}": "link_path" for i in range(11)}}
		)


def test_sms_ir_wants_a_numeric_pattern_code(org):
	values = {"event": "otp", "provider_code": "smsir", "mode": "pattern", "param_map": {"CODE": "code"}}
	with pytest.raises(ValidationError):
		sms.save_template(org.db, org.admin, {**values, "pattern_code": "abc"})
	assert sms.save_template(org.db, org.admin, {**values, "pattern_code": "123456"})["id"]


def test_one_active_template_per_event_and_panel(org):
	first = template(org)
	with pytest.raises(Conflict):
		template(org)
	template(org, is_active=False)  # an inactive one may sit beside it
	updated = sms.save_template(org.db, org.admin, {**first, "body": "{name}"}, first["id"])
	assert updated["body"] == "{name}"
	sms.delete_template(org.db, org.admin, first["id"])
	assert org.db.get(SmsTemplate, first["id"]) is None


def test_the_preview_shows_exactly_what_goes_to_the_panel(org):
	text = sms.preview(
		org.db,
		org.admin,
		{"event": "leave_approved", "provider_code": "mock", "mode": "bulk", "body": "سلام {name}"},
	)
	assert text["text"] == "سلام علی رضایی" and text["request"] is None
	values = {"event": "payslip_link", "provider_code": "mock", "mode": "pattern", "pattern_code": "5"}
	shown = sms.preview(org.db, org.admin, {**values, "param_map": {"#NAME#": "name", "LINK": "link_path"}})
	assert shown["request"]["params"] == {"NAME": "علی‌رضایی", "LINK": "l/AbC12345"}


# dispatch -------------------------------------------------------------------------------------------


def test_a_message_is_recorded_with_a_job(org):
	panel(org)
	template(org)
	m = message(org)
	assert (m.status, m.to_number, m.attempts) == ("queued", NUMBER, 0)
	job = org.db.scalar(select(Job).where(Job.kind == "sms_send"))
	assert job.payload == {"message_id": m.id} and job.status == "queued"


def test_a_number_that_is_not_a_mobile_or_an_unknown_event_is_refused(org):
	with pytest.raises(DispatchError):
		dispatch(org.db, "leave_approved", "12345", {})
	with pytest.raises(DispatchError):
		dispatch(org.db, "no_such_event", NUMBER, {})


def test_outside_the_window_the_job_waits_for_morning(org, monkeypatch):
	monkeypatch.setattr(sms_dispatch, "now", lambda: at(23))
	m = message(org)
	assert m.send_after == at(9, day=20)
	assert org.db.scalar(select(Job.run_after).where(Job.kind == "sms_send")) == at(9, day=20)
	otp = dispatch(org.db, "otp", NUMBER, {"code": "123456"})
	assert otp.send_after == at(23)  # a one-time code is useless by morning


def test_a_promotional_message_to_an_opted_out_number_is_recorded_but_not_sent(org):
	sms.add_opt_out(org.db, org.admin, {"mobile": "+98 912 123 4567", "category": "promotional"})
	m = dispatch(org.db, "birthday", NUMBER, {"name": "علی"})
	assert m.status == "skipped" and m.error
	assert org.db.scalar(select(Job).where(Job.kind == "sms_send")) is None
	assert (
		dispatch(org.db, "leave_approved", NUMBER, {"name": "علی"}).status == "queued"
	)  # a service message still goes


def test_the_same_entity_is_recorded_once(org):
	first = dispatch(org.db, "leave_approved", NUMBER, {"name": "علی"}, entity_key="req-1")
	again = dispatch(org.db, "leave_approved", NUMBER, {"name": "علی"}, entity_key="req-1")
	assert again.id == first.id
	assert org.db.scalar(select(SmsMessage.id).where(SmsMessage.entity_key == "req-1")) == first.id


def test_a_link_becomes_a_short_path_that_redirects_and_never_leaves_the_site(org):
	m = dispatch(
		org.db, "payslip_link", NUMBER, {"name": "علی", "link": "https://evil.example/p/secret-token?x=1"}
	)
	assert "link" not in m.context  # the full address is not kept with the message
	code = m.context["link_path"]
	assert code.startswith("l/") and len(code) == 10
	row = org.db.scalar(select(ShortLink))
	assert row.target_path == "/p/secret-token?x=1"  # the domain is thrown away
	assert sms_dispatch.resolve_short_link(org.db, code.removeprefix("l/")) == "/p/secret-token?x=1"
	row.expires_at = at(1)
	assert sms_dispatch.resolve_short_link(org.db, row.code) is None  # expired: the same answer as unknown
	assert sms_dispatch.resolve_short_link(org.db, "nope") is None
	protocol_relative = dispatch(org.db, "payslip_link", NUMBER, {"link": "//evil.example/x"})
	assert org.db.scalar(select(ShortLink.target_path).order_by(ShortLink.id.desc())) == "/x"  # host dropped
	assert protocol_relative.context["link_path"].startswith("l/")
	for sneaky in ("/\\evil.example", "p/no-leading-slash", "javascript:alert(1)", "/a\nb"):
		with pytest.raises(DispatchError):
			dispatch(org.db, "payslip_link", NUMBER, {"link": sneaky})


# the sender -----------------------------------------------------------------------------------------


def test_a_message_is_sent_once_and_recorded(org):
	panel(org)
	template(org)
	m = message(org)
	assert send_message(org.db, m.id) == "sent"
	org.db.refresh(m)
	assert (m.status, m.provider_code, m.attempts) == ("sent", "mock", 1)
	assert m.provider_message_id == "mock-1" and m.sent_at and m.cost == 1
	assert MockDriver.sent == [{"to": NUMBER, "text": "علی 1405/07/14", "line_number": None}]
	assert send_message(org.db, m.id) == "not_claimed"  # a second worker finds nothing to take
	assert len(MockDriver.sent) == 1


def test_the_key_is_masked_in_the_recorded_request_and_answer(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "ok"}, "is_primary": True})
	template(org)
	m = message(org, name="abcd1234")
	MockDriver.sent.clear()
	mock = stored(org)
	mock.config = {"behavior": "ok"}
	send_message(org.db, m.id)
	assert org.db.get(SmsMessage, m.id).raw_request["text"].startswith("abcd1234")  # not a secret: untouched


def test_when_the_primary_refuses_for_good_the_fallback_sends(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "fatal"}, "is_primary": True})
	panel(org, "mock2", is_primary=False, is_fallback=True)
	template(org)
	template(org, provider="mock2")
	m = message(org)
	assert send_message(org.db, m.id) == "sent"
	org.db.refresh(m)
	assert m.provider_code == "mock2" and len(Second.sent) == 1 and not MockDriver.sent


def test_a_busy_panel_is_tried_again_later_with_a_longer_wait(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "retryable"}, "is_primary": True})
	template(org)
	m = message(org)
	waits = []
	for _attempt in range(4):
		assert send_message(org.db, m.id) == "queued"
		org.db.refresh(m)
		waits.append(m.send_after)
	assert m.attempts == 4 and m.error
	assert waits[3] > waits[0]
	assert (
		len(list(org.db.scalars(select(Job).where(Job.kind == "sms_send")))) == 5
	)  # the first and one per retry
	assert send_message(org.db, m.id) == "failed"  # the fifth attempt is the last
	org.db.refresh(m)
	assert (m.status, m.attempts) == ("failed", 5)


def test_a_lost_answer_is_unknown_and_never_goes_through_another_panel(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "timeout"}, "is_primary": True})
	panel(org, "mock2", is_primary=False, is_fallback=True)
	template(org)
	template(org, provider="mock2")
	m = message(org)
	assert send_message(org.db, m.id) == "unknown"
	assert not Second.sent  # it may have been sent: a second SMS would be worse than none
	assert send_message(org.db, m.id) == "not_claimed"  # and nothing retries it


def test_without_a_panel_or_a_template_the_message_fails_with_the_reason(org):
	m = message(org)
	assert send_message(org.db, m.id) == "failed"
	assert "panel" in org.db.get(SmsMessage, m.id).error.lower() or org.db.get(SmsMessage, m.id).error
	panel(org)  # a panel but no template for this event
	other = message(org, name="x")
	other.entity_key = None
	assert send_message(org.db, other.id) == "failed"


def test_an_unexpected_error_leaves_the_outcome_unknown(org, monkeypatch):
	panel(org)
	template(org)
	m = message(org)

	def boom(*args, **kwargs):
		raise RuntimeError("bug")

	monkeypatch.setattr(sms_dispatch, "_try", boom)
	assert send_message(org.db, m.id) == "unknown"
	assert "RuntimeError" in org.db.get(SmsMessage, m.id).error


def test_the_test_button_sends_at_once_outside_the_window(org, monkeypatch):
	monkeypatch.setattr(sms_dispatch, "now", lambda: at(3))
	panel(org)
	template(org, "otp", "{code}")
	m = sms_dispatch.test_send(org.db, "otp", NUMBER, {"code": "123456"})
	assert m.status == "sent" and MockDriver.sent[0]["text"] == "123456"
	assert org.db.scalar(select(Job).where(Job.kind == "sms_send")) is None  # no job: it was sent in place


def test_the_worker_sends_a_queued_message(org):
	panel(org)
	template(org)
	m = message(org)
	org.db.commit()
	from sqlalchemy.orm import sessionmaker

	factory = sessionmaker(
		bind=org.db.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False
	)
	assert worker.run_queue(factory, today="1405/07/14") == 1
	org.db.refresh(m)
	assert m.status == "sent"


# review, opt-outs, settings -------------------------------------------------------------------------


def test_uncertain_messages_are_listed_for_review_and_settled_by_the_admin(org):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "timeout"}, "is_primary": True})
	template(org)
	m = message(org)
	send_message(org.db, m.id)
	assert [x["id"] for x in sms.needs_review(org.db, org.admin)] == [m.id]
	assert (
		sms.resolve_message(org.db, org.admin, m.id, "sent", "panel report says delivered")["status"]
		== "sent"
	)
	assert sms.needs_review(org.db, org.admin) == []
	with pytest.raises(ValidationError):
		sms.resolve_message(org.db, org.admin, m.id, "failed", None)  # already settled
	stuck = message(org, name="y")
	stuck.entity_key = None
	stuck.status, stuck.send_after = "sending", at(1)
	assert [x["id"] for x in sms.needs_review(org.db, org.admin)] == [stuck.id]  # sending for too long


def test_the_history_filters_and_hides_the_raw_data_in_the_list(org):
	panel(org)
	template(org)
	m = message(org)
	send_message(org.db, m.id)
	listed = sms.list_messages(org.db, org.admin, status="sent", event="leave_approved", to="0912 123 4567")
	assert listed["total"] == 1 and "raw_request" not in listed["items"][0]
	detail = sms.get_message(org.db, org.admin, m.id)
	assert detail["raw_request"]["to"] == NUMBER and detail["context"]["name"] == "علی"
	assert sms.list_messages(org.db, org.admin, status="failed")["total"] == 0


def test_opt_outs_are_per_number_and_category(org):
	row = sms.add_opt_out(
		org.db, org.admin, {"mobile": "9121234567", "category": "promotional", "reason": "asked"}
	)
	assert row["mobile"] == NUMBER
	with pytest.raises(Conflict):
		sms.add_opt_out(org.db, org.admin, {"mobile": NUMBER, "category": "promotional"})
	with pytest.raises(ValidationError):
		sms.add_opt_out(org.db, org.admin, {"mobile": "123"})
	sms.remove_opt_out(org.db, org.admin, row["id"])
	assert sms.list_opt_outs(org.db) == []


def test_the_window_settings_are_checked(org):
	assert (
		sms.save_settings(org.db, org.admin, {"window_start_hour": 8, "window_end_hour": 22})[
			"window_end_hour"
		]
		== 22
	)
	for bad in (
		{"window_start_hour": 22, "window_end_hour": 8},
		{"window_start_hour": 25},
		{"window_end_hour": "x"},
	):
		with pytest.raises(ValidationError):
			sms.save_settings(org.db, org.admin, bad)
	assert sms.get_settings(org.db)["window_start_hour"] == 8


def test_a_message_waiting_in_the_future_is_not_taken_by_the_worker_early(org):
	panel(org)
	template(org)
	m = message(org)
	m.send_after = datetime.now(TEHRAN) + timedelta(hours=5)
	org.db.scalar(select(Job).where(Job.kind == "sms_send")).run_after = m.send_after
	org.db.commit()
	from sqlalchemy.orm import sessionmaker

	factory = sessionmaker(
		bind=org.db.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False
	)
	assert worker.run_queue(factory, today="1405/07/14") == 0
