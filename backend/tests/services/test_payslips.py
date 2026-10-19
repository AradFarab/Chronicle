"""Payslips: matching pages to employees, the SMS links and what the employee can open."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from orgfactory import make_employee
from payslipfactory import slip_pdf
from sqlalchemy import select

from chronicle.clock import now
from chronicle.db.models import Payslip, PayslipLink, PayslipRejection, ShortLink, SmsMessage, StoredFile
from chronicle.db.models.payslips import MATCH, MISMATCH, UNKNOWN, VOIDED
from chronicle.services import payslips, sms, sms_dispatch
from chronicle.services.errors import PermissionDenied, ValidationError
from chronicle.sms.mock import MockDriver

YEAR, MONTH = 1405, 7
ALI = ("EMP042", "0012345678", "09121234567")  # code, national id, mobile
BODY = "{name}|{month}|{expires}|{link_path}"


@pytest.fixture(autouse=True)
def clean_mock():
	MockDriver.sent.clear()


@pytest.fixture
def panel(org):
	"""A working mock panel and a template for the payslip event: what the admin sets up in the SMS section."""
	sms.save_provider(org.db, org.admin, "mock", {"config": {}, "is_primary": True})
	sms.save_template(
		org.db, org.admin, {"event": "payslip_link", "provider_code": "mock", "mode": "bulk", "body": BODY}
	)


@pytest.fixture
def ali(org):
	code, national, mobile = ALI
	return make_employee(org.db, code, national_id=national, mobile=mobile)[0]


def upload(org, *pages, actor=None):
	return payslips.upload(org.db, actor or org.admin, YEAR, MONTH, [("slips.pdf", slip_pdf(*pages))])


def queue(org, mode="unsent"):
	return payslips.queue_send(org.db, org.admin, YEAR, MONTH, mode)


def messages(org):
	return list(org.db.scalars(select(SmsMessage).order_by(SmsMessage.id)))


def deliver(org):
	"""What the worker does: send every queued message."""
	for m in messages(org):
		sms_dispatch.send_message(org.db, m.id)


def sent_token(org) -> str:
	"""The token as the employee gets it: the SMS carries a short path, which leads to /p/<token>."""
	short = MockDriver.sent[-1]["text"].split("|")[3]
	return sms_dispatch.resolve_short_link(org.db, short.removeprefix("l/")).removeprefix("/p/")


def send_all(org, mode="unsent"):
	queue(org, mode)
	deliver(org)


# uploading --------------------------------------------------------------------------------------


def test_pages_are_matched_to_employees_by_personnel_code(org, ali):
	reza = make_employee(org.db, "EMP7", national_id="0087654321", mobile="09127654321")[0]
	counts = upload(org, ("42", "0012345678"), ("7", None), ("99", "0000000001"))
	assert counts == {"created": 2, "replaced": 0, "rejected": 1, "mismatch": 0}
	rows = {p.employee_id: p for p in org.db.scalars(select(Payslip))}
	assert rows[ali.id].national_status == MATCH and rows[reza.id].national_status == UNKNOWN
	assert rows[ali.id].jyear == YEAR and rows[ali.id].jmonth == MONTH
	[rejection] = org.db.scalars(select(PayslipRejection))
	assert "99" in rejection.reason and rejection.page_no == 3


def test_a_national_id_that_is_not_the_employees_is_a_mismatch(org, ali):
	assert upload(org, ("42", "1111111111"))["mismatch"] == 1
	assert org.db.scalar(select(Payslip.national_status)) == MISMATCH


def test_the_same_person_twice_in_one_upload_keeps_the_first_page(org, ali):
	counts = upload(org, ("42", "0012345678"), ("42", "0012345678"))
	assert counts["created"] == 1 and counts["rejected"] == 1


def test_a_file_that_is_not_a_pdf_is_listed_not_fatal(org, ali):
	counts = payslips.upload(org.db, org.admin, YEAR, MONTH, [("x.pdf", b"nope")])
	assert counts["rejected"] == 1 and counts["created"] == 0


def test_uploading_again_replaces_the_file_and_keeps_the_link(org, panel, ali):
	upload(org, ("42", "0012345678"))
	send_all(org)
	first = org.db.scalar(select(Payslip))
	old_file = first.file_id
	assert upload(org, ("42", "0012345678"))["replaced"] == 1
	org.db.refresh(first)
	assert first.file_id != old_file and org.db.get(StoredFile, old_file) is None
	link = org.db.scalar(select(PayslipLink))
	assert not link.locked and link.payslip_id == first.id


def test_only_the_system_admin_may_upload(org, ali):
	with pytest.raises(PermissionDenied):
		upload(org, ("42", "0012345678"), actor=org.emp)


# sending ----------------------------------------------------------------------------------------


def test_sending_makes_a_link_and_a_message_that_carries_only_a_short_path(org, panel, ali):
	upload(org, ("42", "0012345678"))
	assert queue(org) == {"queued": 1}
	link = org.db.scalar(select(PayslipLink))
	[message] = messages(org)
	assert link.sms_message_id == message.id and message.entity_key == f"payslip_link:{link.id}"
	assert message.status == "queued" and message.to_number == "09121234567"
	assert set(message.context) == {"name", "month", "expires", "link_path"}  # the full link is not kept
	deliver(org)
	text = MockDriver.sent[0]["text"]
	assert text.startswith("کارمند EMP042|مهر 1405|") and text.split("|")[3].startswith("l/")
	token = sent_token(org)
	assert link.token_hash == hashlib.sha256(token.encode()).hexdigest()
	assert org.db.scalar(select(ShortLink.target_path)) == f"/p/{token}"


def test_the_preview_says_who_is_left_out_and_what_the_first_sms_would_be(org, panel, ali):
	make_employee(org.db, "EMP7", national_id="0087654321", mobile="123")
	upload(org, ("42", "0012345678"), ("7", None))
	preview = payslips.preview(org.db, org.admin, YEAR, MONTH)
	assert preview["count"] == 1 and preview["unavailable"] is None
	assert [b["problem"] for b in preview["blocked"]] == ["bad_mobile"]
	assert preview["sample"]["text"].startswith("کارمند EMP042|مهر 1405|")
	assert "l/xxxxxxxx" in preview["sample"]["text"]


def test_a_pattern_template_is_previewed_as_the_request_the_panel_gets(org, ali):
	sms.save_provider(org.db, org.admin, "mock", {"config": {}, "is_primary": True})
	sms.save_template(
		org.db,
		org.admin,
		{
			"event": "payslip_link",
			"provider_code": "mock",
			"mode": "pattern",
			"pattern_code": "55",
			"param_map": {"NAME": "name", "LINK": "link_path"},
		},
	)
	upload(org, ("42", "0012345678"))
	sample = payslips.preview(org.db, org.admin, YEAR, MONTH)["sample"]
	assert sample["request"]["pattern_code"] == "55"
	assert sample["request"]["params"] == {"NAME": "کارمند‌EMP042", "LINK": "l/xxxxxxxx"}


def test_nothing_is_sent_without_a_panel_and_a_template(org, ali):
	upload(org, ("42", "0012345678"))
	assert payslips.preview(org.db, org.admin, YEAR, MONTH)["unavailable"]
	with pytest.raises(ValidationError):  # no panel yet
		queue(org)
	sms.save_provider(org.db, org.admin, "mock", {"config": {}, "is_primary": True})
	with pytest.raises(ValidationError):  # a panel but no template
		queue(org)


def test_sending_to_those_who_already_have_a_link_needs_the_everyone_choice(org, panel, ali):
	upload(org, ("42", "0012345678"))
	send_all(org)
	with pytest.raises(ValidationError):
		queue(org, "unsent")
	first = org.db.scalar(select(PayslipLink))
	assert payslips.preview(org.db, org.admin, YEAR, MONTH, "all")["replacing"] == 1
	queue(org, "all")
	org.db.refresh(first)
	assert first.locked and first.lock_reason == VOIDED  # the old link no longer works
	assert (
		org.db.scalar(select(PayslipLink).where(PayslipLink.locked.is_(False))).sms_message_id
		!= first.sms_message_id
	)


def test_a_message_still_on_its_way_is_not_sent_twice(org, panel, ali):
	upload(org, ("42", "0012345678"))
	queue(org)  # queued, not yet sent by the worker
	for mode in ("unsent", "all"):
		with pytest.raises(ValidationError):
			queue(org, mode)


def test_a_failed_sms_is_picked_up_by_the_next_send(org, ali):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "fatal"}, "is_primary": True})
	sms.save_template(
		org.db, org.admin, {"event": "payslip_link", "provider_code": "mock", "mode": "bulk", "body": BODY}
	)
	upload(org, ("42", "0012345678"))
	send_all(org)
	[failed] = messages(org)
	assert failed.status == "failed"
	overview = payslips.overview(org.db, org.admin, YEAR, MONTH)
	row = next(r for r in overview["rows"] if r["code"] == "EMP042")
	assert (
		row["link"]["sms_status"] == "failed"
		and row["link"]["sms_error"]
		and overview["counts"]["failed"] == 1
	)
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "ok"}})
	send_all(org)  # "unsent" includes the failed ones
	assert [m.status for m in messages(org)] == ["failed", "sent"]


def test_a_message_of_unknown_outcome_waits_for_the_admin(org, ali):
	sms.save_provider(org.db, org.admin, "mock", {"config": {"behavior": "timeout"}, "is_primary": True})
	sms.save_template(
		org.db, org.admin, {"event": "payslip_link", "provider_code": "mock", "mode": "bulk", "body": BODY}
	)
	upload(org, ("42", "0012345678"))
	send_all(org)
	assert messages(org)[0].status == "unknown"
	with pytest.raises(ValidationError):  # it may have been delivered: never resent by itself
		queue(org, "unsent")
	assert payslips.overview(org.db, org.admin, YEAR, MONTH)["counts"]["unknown"] == 1
	queue(org, "all")  # the admin can choose to send again


def test_a_mismatched_slip_never_gets_a_link(org, panel, ali):
	upload(org, ("42", "1111111111"))
	with pytest.raises(ValidationError):
		queue(org)


# the employee's side ----------------------------------------------------------------------------


def opened(org, secret="5678"):
	return payslips.open_payslip(org.db, sent_token(org), secret, "10.0.0.5")


@pytest.fixture
def sent(org, panel, ali):
	upload(org, ("42", "0012345678"))
	send_all(org)


def test_the_right_last_four_digits_open_the_payslip_and_are_counted(org, sent):
	content, filename = opened(org, "۵۶۷۸")  # Persian digits are fine
	assert content.startswith(b"%PDF") and filename == "payslip-1405-07.pdf"
	assert org.db.scalar(select(PayslipLink)).view_count == 1


def test_a_wrong_answer_is_counted_and_enough_of_them_lock_the_link(org, sent):
	payslips.save_settings(org.db, org.admin, {"max_failed_attempts": 2})
	with pytest.raises(payslips.WrongSecret):
		opened(org, "0000")
	link = org.db.scalar(select(PayslipLink))
	assert link.failed_attempts == 1
	with pytest.raises(payslips.LinkInvalid):
		opened(org, "1111")
	with pytest.raises(payslips.LinkInvalid):  # locked: even the right answer is refused
		opened(org, "5678")
	assert link.locked and link.lock_reason == "failed_attempts"


def test_a_link_stops_after_its_views_and_after_its_time(org, sent):
	link = org.db.scalar(select(PayslipLink))
	link.max_views = 1
	opened(org)
	with pytest.raises(payslips.LinkInvalid):
		opened(org)
	link.max_views, link.view_count = 5, 0
	link.expires_at = now() - timedelta(minutes=1)
	with pytest.raises(payslips.LinkInvalid):
		opened(org)


def test_an_unknown_token_gets_the_same_answer(org):
	with pytest.raises(payslips.LinkInvalid):
		payslips.open_payslip(org.db, "no-such-token", "5678", None)
	with pytest.raises(payslips.LinkInvalid):
		payslips.link_info(org.db, "")


def test_someone_who_left_cannot_open_an_old_link(org, sent, ali):
	ali.status = "left"
	org.db.flush()
	with pytest.raises(payslips.LinkInvalid):
		opened(org)


def test_the_link_settings_are_checked(org):
	saved = payslips.save_settings(org.db, org.admin, {"link_expiry_days": "30", "link_max_views": 3})
	assert (saved["link_expiry_days"], saved["link_max_views"]) == (30, 3)
	for bad in ({"link_expiry_days": 0}, {"link_max_views": 1000}, {"max_failed_attempts": "x"}):
		with pytest.raises(ValidationError):
			payslips.save_settings(org.db, org.admin, bad)
