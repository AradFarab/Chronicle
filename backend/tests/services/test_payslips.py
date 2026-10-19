"""Payslips: matching pages to employees, the SMS links and what the employee can open."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from orgfactory import make_employee
from payslipfactory import slip_pdf
from sqlalchemy import select

from chronicle.clock import now
from chronicle.db.models import Job, Payslip, PayslipLink, PayslipRejection, StoredFile
from chronicle.db.models.payslips import FAILED, MATCH, MISMATCH, PENDING, SENT, UNKNOWN, VOIDED
from chronicle.services import jobs, payslips
from chronicle.services import sms as sms_service
from chronicle.services.errors import PermissionDenied, ValidationError
from chronicle.sms.base import SmsError, SmsGateway, SmsHealth, SmsResult

YEAR, MONTH = 1405, 7
ALI = ("EMP042", "0012345678", "09121234567")  # code, national id, mobile


class FakeGateway(SmsGateway):
	code = "fake"
	batch_size = 2

	def __init__(self):
		self.batches = []
		self.error = None

	def send(self, messages):
		if self.error:
			raise self.error
		self.batches.append(list(messages))
		return [SmsResult(m.mobile, True, f"id-{i}") for i, m in enumerate(messages)]

	def health(self):
		return SmsHealth(True, "", 1000.0)


@pytest.fixture
def gateway(monkeypatch, org):
	fake = FakeGateway()
	monkeypatch.setattr(sms_service, "gateway", lambda session: fake)
	payslips.save_settings(org.db, org.admin, {"base_url": "https://hr.example.ir"})
	return fake


@pytest.fixture
def ali(org):
	code, national, mobile = ALI
	return make_employee(org.db, code, national_id=national, mobile=mobile)[0]


def upload(org, *pages, actor=None):
	return payslips.upload(org.db, actor or org.admin, YEAR, MONTH, [("slips.pdf", slip_pdf(*pages))])


def sent_token(gateway) -> str:
	return re.search(r"/p/(\S+)", gateway.batches[-1][-1].text).group(1)


def send_all(org, gateway, mode="unsent"):
	payslips.queue_send(org.db, org.admin, YEAR, MONTH, mode)
	return payslips.send_pending(org.db)


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


def test_uploading_again_replaces_the_file_and_keeps_the_link(org, gateway, ali):
	upload(org, ("42", "0012345678"))
	send_all(org, gateway)
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


def test_sending_makes_a_pending_link_and_a_job_then_the_worker_texts_it(org, gateway, ali):
	upload(org, ("42", "0012345678"))
	queued = payslips.queue_send(org.db, org.admin, YEAR, MONTH)
	assert queued["queued"] == 1
	link = org.db.scalar(select(PayslipLink))
	assert link.sms_status == PENDING and link.token_encrypted and len(link.token_hash) == 64
	assert org.db.scalar(select(Job.kind)) == jobs.PAYSLIP_SEND

	assert payslips.send_pending(org.db) == {"sent": 1, "failed": 0}
	[[message]] = gateway.batches
	assert message.mobile == "09121234567"
	assert message.text.startswith("کارمند EMP042 عزیز") and "https://hr.example.ir/p/" in message.text
	org.db.refresh(link)
	assert link.sms_status == SENT and link.token_encrypted is None and link.sms_provider_id == "id-0"


def test_messages_go_out_in_batches_of_the_gateways_size(org, gateway):
	for n in range(3):
		make_employee(org.db, f"EMP10{n}", national_id=f"00000000{n}1", mobile=f"0912000000{n}")
	upload(org, ("100", None), ("101", None), ("102", None))
	send_all(org, gateway)
	assert [len(b) for b in gateway.batches] == [2, 1]


def test_the_preview_says_who_is_left_out_and_why(org, gateway, ali):
	make_employee(org.db, "EMP7", national_id="0087654321", mobile="123")
	upload(org, ("42", "0012345678"), ("7", None))
	preview = payslips.preview(org.db, org.admin, YEAR, MONTH)
	assert preview["count"] == 1 and preview["unavailable"] is None
	assert [b["problem"] for b in preview["blocked"]] == ["bad_mobile"]
	assert "https://hr.example.ir/p/" in preview["sample"]


def test_nothing_is_sent_without_the_site_address_or_a_working_connection(org, ali):
	upload(org, ("42", "0012345678"))
	with pytest.raises(ValidationError):  # no site address yet
		payslips.queue_send(org.db, org.admin, YEAR, MONTH)
	payslips.save_settings(org.db, org.admin, {"base_url": "https://hr.example.ir"})
	with pytest.raises(ValidationError):  # no SMS key yet
		payslips.queue_send(org.db, org.admin, YEAR, MONTH)
	assert payslips.preview(org.db, org.admin, YEAR, MONTH)["unavailable"]


def test_sending_to_those_who_already_have_a_link_needs_the_everyone_choice(org, gateway, ali):
	upload(org, ("42", "0012345678"))
	send_all(org, gateway)
	with pytest.raises(ValidationError):
		payslips.queue_send(org.db, org.admin, YEAR, MONTH, "unsent")
	first = org.db.scalar(select(PayslipLink))
	payslips.queue_send(org.db, org.admin, YEAR, MONTH, "all")
	org.db.refresh(first)
	assert first.locked and first.lock_reason == VOIDED  # the old link no longer works
	assert org.db.scalar(select(PayslipLink).where(PayslipLink.locked.is_(False))).sms_status == PENDING


def test_a_failed_sms_is_recorded_and_picked_up_by_the_next_send(org, gateway, ali):
	upload(org, ("42", "0012345678"))
	gateway.error = SmsError("sms.ir refused the API key")
	assert send_all(org, gateway) == {"sent": 0, "failed": 1}
	link = org.db.scalar(select(PayslipLink))
	assert link.sms_status == FAILED and link.sms_error and link.token_encrypted is None
	gateway.error = None
	assert send_all(org, gateway)["sent"] == 1  # "unsent" includes the failed ones


def test_a_mismatched_slip_never_gets_a_link(org, gateway, ali):
	upload(org, ("42", "1111111111"))
	with pytest.raises(ValidationError):
		payslips.queue_send(org.db, org.admin, YEAR, MONTH)


# the employee's side ----------------------------------------------------------------------------


def opened(org, gateway, secret="5678"):
	return payslips.open_payslip(org.db, sent_token(gateway), secret, "10.0.0.5")


@pytest.fixture
def sent(org, gateway, ali):
	upload(org, ("42", "0012345678"))
	send_all(org, gateway)


def test_the_right_last_four_digits_open_the_payslip_and_are_counted(org, gateway, sent):
	content, filename = opened(org, gateway, "۵۶۷۸")  # Persian digits are fine
	assert content.startswith(b"%PDF") and filename == "payslip-1405-07.pdf"
	link = org.db.scalar(select(PayslipLink))
	assert link.view_count == 1


def test_a_wrong_answer_is_counted_and_enough_of_them_lock_the_link(org, gateway, sent):
	payslips.save_settings(org.db, org.admin, {"max_failed_attempts": 2})
	with pytest.raises(payslips.WrongSecret):
		opened(org, gateway, "0000")
	link = org.db.scalar(select(PayslipLink))
	assert link.failed_attempts == 1
	with pytest.raises(payslips.LinkInvalid):
		opened(org, gateway, "1111")
	with pytest.raises(payslips.LinkInvalid):  # locked: even the right answer is refused
		opened(org, gateway, "5678")
	assert link.locked and link.lock_reason == "failed_attempts"


def test_a_link_stops_after_its_views_and_after_its_time(org, gateway, sent):
	payslips.save_settings(org.db, org.admin, {"link_max_views": 1})
	link = org.db.scalar(select(PayslipLink))
	link.max_views = 1
	opened(org, gateway)
	with pytest.raises(payslips.LinkInvalid):
		opened(org, gateway)
	link.max_views, link.view_count = 5, 0
	link.expires_at = now() - timedelta(minutes=1)
	with pytest.raises(payslips.LinkInvalid):
		opened(org, gateway)


def test_an_unknown_token_gets_the_same_answer(org):
	with pytest.raises(payslips.LinkInvalid):
		payslips.open_payslip(org.db, "no-such-token", "5678", None)
	with pytest.raises(payslips.LinkInvalid):
		payslips.link_info(org.db, "")


def test_someone_who_left_cannot_open_an_old_link(org, gateway, sent, ali):
	ali.status = "left"
	org.db.flush()
	with pytest.raises(payslips.LinkInvalid):
		opened(org, gateway)


def test_the_message_must_carry_the_link_and_only_known_fields(org):
	for bad in ("no link here", "{link} {secret}", "{link} {}", "{link"):
		with pytest.raises(ValidationError):
			payslips.save_settings(org.db, org.admin, {"message": bad})
	saved = payslips.save_settings(org.db, org.admin, {"message": "{name}: {link}"})
	assert saved["message"] == "{name}: {link}"
