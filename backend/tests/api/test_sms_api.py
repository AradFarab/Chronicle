"""The SMS section of the admin over HTTP."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from chronicle.db.models import SmsMessage
from chronicle.sms.mock import MockDriver

BODY = {"event": "leave_approved", "provider_code": "mock", "mode": "bulk", "body": "{name} {date}"}


@pytest.fixture(autouse=True)
def clean_mock():
	MockDriver.sent.clear()


@pytest.fixture
def admin(client_for):
	return client_for("op")


def test_only_the_system_admin_reaches_the_sms_section(client_for):
	emp = client_for("emp")
	for path in ("/api/sms/drivers", "/api/sms/providers", "/api/sms/templates", "/api/sms/messages"):
		assert emp.get(path).status_code == 403
	assert emp.put("/api/sms/providers/mock", json={}).status_code == 403


def test_the_drivers_describe_their_own_settings_form(admin):
	drivers = {d["code"]: d for d in admin.get("/api/sms/drivers").json()}
	assert drivers["smsir"]["config_schema"]["api_key"]["type"] == "secret"
	assert drivers["smsir"]["capabilities"] == ["bulk", "pattern"]
	assert drivers["smsir"]["pattern_schema"]["param_style"] == "named"


def test_the_key_is_never_returned(admin):
	saved = admin.put("/api/sms/providers/smsir", json={"config": {"api_key": "key-12345", "sender": "3000"}})
	assert saved.status_code == 200 and saved.json()["config"]["api_key"] == "••••••••"
	listed = next(p for p in admin.get("/api/sms/providers").json() if p["code"] == "smsir")
	assert "key-12345" not in str(listed) and listed["configured"] is True
	assert (
		admin.put("/api/sms/providers/smsir", json={"config": {"api_key": ""}}).status_code == 200
	)  # blank keeps it
	assert (
		admin.put("/api/sms/providers/smsir", json={"config": {"api_key": "", "sender": ""}}).status_code
		== 200
	)
	assert admin.put("/api/sms/providers/nope", json={}).status_code == 422


def test_templates_are_checked_on_save_and_can_be_previewed(admin):
	admin.put("/api/sms/providers/mock", json={"config": {}, "is_primary": True})
	bad = admin.post("/api/sms/templates", json={**BODY, "body": "{name} {nope}"})
	assert bad.status_code == 422 and "nope" in bad.json()["message"]
	preview = admin.post("/api/sms/templates/preview", json=BODY).json()
	assert preview["text"] == "علی رضایی 1405/07/27"
	created = admin.post("/api/sms/templates", json=BODY)
	assert created.status_code == 200 and created.json()["warnings"] == ["leave_type"]
	assert admin.post("/api/sms/templates", json=BODY).status_code == 409  # one active per event and panel
	template_id = created.json()["id"]
	assert (
		admin.patch(f"/api/sms/templates/{template_id}", json={**BODY, "body": "{name}"}).json()["body"]
		== "{name}"
	)
	assert [t["id"] for t in admin.get("/api/sms/templates").json()] == [template_id]
	assert admin.delete(f"/api/sms/templates/{template_id}").status_code == 200


def test_the_test_button_sends_a_real_message_and_it_shows_in_the_history(admin, org):
	admin.put("/api/sms/providers/mock", json={"config": {}, "is_primary": True})
	assert (
		admin.post("/api/sms/test-send", json={"event": "leave_approved", "to": "09121234567"}).status_code
		== 422
	)
	admin.post("/api/sms/templates", json=BODY)
	sent = admin.post("/api/sms/test-send", json={"event": "leave_approved", "to": "09121234567"})
	assert sent.status_code == 200 and sent.json()["status"] == "sent"
	assert sent.json()["raw_request"]["to"] == "09121234567"
	history = admin.get("/api/sms/messages", params={"status": "sent"}).json()
	assert history["total"] == 1 and "raw_request" not in history["items"][0]
	assert (
		admin.get(f"/api/sms/messages/{history['items'][0]['id']}").json()["context"]["name"] == "علی رضایی"
	)
	assert admin.get("/api/sms/messages/999999").status_code == 404


def test_uncertain_messages_are_reviewed_and_settled(admin, org):
	admin.put("/api/sms/providers/mock", json={"config": {"behavior": "timeout"}, "is_primary": True})
	admin.post("/api/sms/templates", json=BODY)
	unknown = admin.post("/api/sms/test-send", json={"event": "leave_approved", "to": "09121234567"}).json()
	assert unknown["status"] == "unknown"
	assert [m["id"] for m in admin.get("/api/sms/review").json()] == [unknown["id"]]
	done = admin.post(
		f"/api/sms/messages/{unknown['id']}/resolve", json={"outcome": "sent", "note": "panel says so"}
	)
	assert done.json()["status"] == "sent" and admin.get("/api/sms/review").json() == []
	assert (
		admin.post(f"/api/sms/messages/{unknown['id']}/resolve", json={"outcome": "failed"}).status_code
		== 422
	)
	assert org.db.scalar(select(SmsMessage.status)) == "sent"


def test_events_opt_outs_and_the_window(admin):
	events = {e["code"]: e for e in admin.get("/api/sms/events").json()}
	assert events["otp"]["bypasses_send_window"] is True and events["birthday"]["category"] == "promotional"
	assert admin.put("/api/sms/events/birthday", json={"is_active": False}).json()["is_active"] is False
	made = admin.post("/api/sms/opt-outs", json={"mobile": "09121234567", "category": "promotional"}).json()
	assert [o["mobile"] for o in admin.get("/api/sms/opt-outs").json()] == ["09121234567"]
	assert admin.delete(f"/api/sms/opt-outs/{made['id']}").status_code == 200
	window = admin.put("/api/sms/settings", json={"window_start_hour": 8, "window_end_hour": 22}).json()
	assert (window["window_start_hour"], window["window_end_hour"]) == (8, 22)
	assert (
		admin.put("/api/sms/settings", json={"window_start_hour": 23, "window_end_hour": 22}).status_code
		== 422
	)
