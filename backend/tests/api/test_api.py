"""The HTTP layer: login, CSRF guard, translated errors, requests and calendar endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from orgfactory import TODAY
from sqlalchemy import select

from hozur.db.models import LeaveType
from hozur.services import leave


def test_login_errors_are_translated(app, org):
	client = TestClient(app, headers={"X-Hozur": "1"})
	r = client.post("/api/auth/login", json={"username": "emp", "password": "nope-nope"})
	assert r.status_code == 401
	assert r.json()["message"] == "نام کاربری یا رمز عبور اشتباه است"
	assert client.get("/api/me").status_code == 401


def test_unsafe_requests_need_the_custom_header(client_for):
	client = client_for("emp")
	del client.headers["X-Hozur"]
	assert client.post("/api/requests/overtime", json={"jdate": TODAY, "minutes": 30}).status_code == 403


def test_me_describes_the_user(client_for, org):
	me = client_for("mgr").get("/api/me").json()
	assert me["employee"]["id"] == org.manager.id and me["is_manager"] and not me["is_operator"]
	assert me["roles"] == ["employee", "manager"]


def test_leave_request_through_the_api(client_for, org):
	earned = org.db.scalar(select(LeaveType).where(LeaveType.name == "استحقاقی"))
	leave.add_entry(org.db, org.employee.id, earned.id, leave.ALLOCATION, "1405/01/01", 5)
	emp, mgr, boss = client_for("emp"), client_for("mgr"), client_for("ceo")
	r = emp.post(
		"/api/requests/leave",
		json={
			"leave_type_id": earned.id,
			"unit": "daily",
			"from_date": "1405/07/12",
			"to_date": "1405/07/12",
		},
	)
	assert r.status_code == 200, r.text
	body = r.json()
	assert (
		body["number"].startswith("LV-")
		and body["status"] == "pending"
		and body["waiting_for"] == org.manager.full_name
	)
	inbox = mgr.get("/api/inbox").json()
	assert [x["id"] for x in inbox] == [body["id"]] and inbox[0]["can_act"]
	assert boss.post(f"/api/requests/{body['id']}/approve", json={}).status_code == 403
	assert (
		mgr.post(f"/api/requests/{body['id']}/approve", json={"comment": "ok"}).json()["status"] == "pending"
	)
	assert boss.post(f"/api/requests/{body['id']}/approve", json={}).json()["status"] == "approved"
	assert emp.get("/api/leave/balance").json()["balance"] == 4.0
	assert [x["id"] for x in emp.get("/api/requests").json()] == [body["id"]]


def test_validation_errors_come_back_in_persian(client_for):
	r = client_for("emp").post(
		"/api/requests/mission", json={"unit": "daily", "from_date": TODAY, "to_date": TODAY}
	)
	assert r.status_code == 422
	assert "مأموریت" in r.json()["message"]


def test_calendar_is_for_operators(client_for):
	assert (
		client_for("emp")
		.post(
			"/api/calendar/holidays",
			json={"jdate": "1405/09/01", "title": "x", "holiday_type": "company_internal"},
		)
		.status_code
		== 403
	)
	op = client_for("op")
	created = op.post(
		"/api/calendar/holidays",
		json={
			"jdate": "1405/09/01",
			"title": "تعطیلی شرکت",
			"holiday_type": "company_internal",
			"scope": "company",
		},
	)
	assert created.status_code == 200, created.text
	assert any(
		h["title"] == "تعطیلی شرکت" for h in op.get("/api/calendar/holidays", params={"year": 1405}).json()
	)


def test_calendar_refresh_from_an_uploaded_file(client_for):
	op = client_for("op")
	payload = json.dumps({"holidays": [{"jdate": "1406/02/02", "title": "تعطیلی تازه"}]}).encode()
	files = {"file": ("h.json", payload, "application/json")}
	preview = op.post("/api/calendar/refresh/preview", data={"year": 1406, "source": "file"}, files=files)
	assert preview.status_code == 200, preview.text
	items = preview.json()["items"]
	add = next(i for i in items if i["action"] == "add")
	assert add["jdate"] == "1406/02/02"
	# keep only the addition: skip every removal
	skip = [i["key"] for i in items if i["action"] != "add"]
	applied = op.post(
		"/api/calendar/refresh/apply", data={"year": 1406, "source": "file", "skip": skip}, files=files
	)
	assert applied.status_code == 200, applied.text
	assert applied.json()["added"] == 1 and applied.json()["removed"] == 0
	years = {y["jyear"]: y for y in op.get("/api/calendar/years").json()}
	assert years[1406]["source"] == "file" and years[1406]["refreshed_at"]
