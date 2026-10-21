"""Payslips over HTTP: the system admin's screens and the employee's link, which needs no login."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from orgfactory import make_employee
from payslipfactory import slip_pdf
from sqlalchemy import select

from chronicle.db.models import PayslipLink, SmsMessage
from chronicle.services import sms_dispatch
from chronicle.sms.mock import MockDriver


@pytest.fixture(autouse=True)
def clean_mock():
	MockDriver.sent.clear()


@pytest.fixture
def ali(org):
	return make_employee(org.db, "EMP042", national_id="0012345678", mobile="09121234567")[0]


@pytest.fixture
def admin(client_for):
	return client_for("op")


def upload(client, pdf=None):
	pdf = pdf or slip_pdf(("42", "0012345678"))
	files = [("files", ("slips.pdf", pdf, "application/pdf"))]
	return client.post("/api/payslips/1405/7/upload", files=files)


def configure(admin):
	assert admin.put("/api/sms/providers/mock", json={"config": {}, "is_primary": True}).status_code == 200
	template = {
		"event": "payslip_link",
		"provider_code": "mock",
		"mode": "bulk",
		"body": "{name}|{month}|{expires}|{link_path}",
	}
	assert admin.post("/api/sms/templates", json=template).status_code == 200


def test_only_the_system_admin_reaches_the_screens(client_for):
	emp = client_for("emp")
	assert emp.get("/api/payslips/1405/7").status_code == 403
	assert emp.get("/api/payslips/settings").status_code == 403
	assert emp.post("/api/payslips/1405/7/send", json={}).status_code == 403


def test_upload_then_the_month_lists_the_employee(admin, ali):
	assert upload(admin).json() == {"created": 1, "replaced": 0, "rejected": 0, "mismatch": 0}
	month = admin.get("/api/payslips/1405/7").json()
	row = next(r for r in month["rows"] if r["code"] == "EMP042")
	assert row["payslip"]["national_status"] == "match" and row["problem"] is None and row["link"] is None
	assert month["counts"]["payslips"] == 1 and month["month_label"] == "مهر 1405"
	file = admin.get(f"/api/payslips/item/{row['payslip']['id']}")
	assert file.headers["content-type"] == "application/pdf"


def test_a_bad_month_is_refused(admin):
	assert admin.get("/api/payslips/1405/13").status_code == 422


def test_the_whole_way_from_upload_to_the_employee_opening_it(admin, app, org, ali):
	upload(admin)
	configure(admin)
	preview = admin.post("/api/payslips/1405/7/send-preview", json={}).json()
	assert preview["count"] == 1 and preview["unavailable"] is None
	assert preview["sample"]["text"].startswith("کارمند EMP042|مهر 1405|")
	assert admin.post("/api/payslips/1405/7/send", json={}).json()["queued"] == 1

	# the worker's part: send the queued message; the SMS carries a short path
	message = org.db.scalar(select(SmsMessage))
	assert sms_dispatch.send_message(org.db, message.id) == "sent"
	short = MockDriver.sent[0]["text"].split("|")[3]
	visitor = TestClient(app, headers={"X-Chronicle": "1"})  # no login
	redirect = visitor.get(f"/{short}", follow_redirects=False)
	assert redirect.status_code == 302 and redirect.headers["location"].startswith("/p/")
	token = redirect.headers["location"].removeprefix("/p/")

	month = admin.get("/api/payslips/1405/7").json()
	assert month["counts"]["sent"] == 1
	info = visitor.get(f"/api/payslip-link/{token}")
	assert info.status_code == 200 and info.json()["month_label"] == "مهر 1405"
	assert visitor.post(f"/api/payslip-link/{token}", json={"secret": "0000"}).status_code == 403
	right = visitor.post(f"/api/payslip-link/{token}", json={"secret": "5678"})
	assert right.status_code == 200 and right.headers["content-type"] == "application/pdf"
	assert right.content.startswith(b"%PDF") and "no-store" in right.headers["cache-control"]
	assert org.db.scalar(select(PayslipLink)).view_count == 1


def test_a_wrong_or_unknown_link_gets_one_answer(app):
	visitor = TestClient(app, headers={"X-Chronicle": "1"})
	assert visitor.get("/api/payslip-link/not-a-real-token").status_code == 404
	assert visitor.post("/api/payslip-link/not-a-real-token", json={"secret": "1234"}).status_code == 404
	assert visitor.get("/l/nosuchcode", follow_redirects=False).status_code == 404


def test_sending_without_the_sms_section_set_up_says_what_is_missing(admin, ali):
	upload(admin)
	r = admin.post("/api/payslips/1405/7/send", json={})
	assert r.status_code == 422 and r.json()["message"].strip()


def test_deleting_a_payslip_removes_it_and_its_link(admin, org, ali):
	upload(admin)
	configure(admin)
	admin.post("/api/payslips/1405/7/send", json={})
	row = next(r for r in admin.get("/api/payslips/1405/7").json()["rows"] if r["code"] == "EMP042")
	assert admin.delete(f"/api/payslips/item/{row['payslip']['id']}").status_code == 200
	assert org.db.scalar(select(PayslipLink)) is None
