"""Configuration, devices, attendance, periods and reports over HTTP."""

from __future__ import annotations

import pytest
from orgfactory import PASSWORD, TODAY
from sqlalchemy import select

from hozur.api import deps
from hozur.db.models import AuditEntry, Job, LaborRuleSet
from hozur.services import devices


@pytest.fixture(autouse=True)
def fixed_today(app):
	app.dependency_overrides[deps.today] = lambda: TODAY
	yield
	app.dependency_overrides.clear()


def test_operator_manages_branches_and_audit_is_written(client_for, org):
	op = client_for("op")
	province = op.get("/api/admin/provinces").json()[0]["id"]
	r = op.post("/api/admin/branches", json={"name": "شعبه شیراز", "province_id": province})
	assert r.status_code == 200, r.text
	branch = r.json()
	r = op.patch(f"/api/admin/branches/{branch['id']}", json={"city": "شیراز"})
	assert r.json()["city"] == "شیراز"
	assert (
		op.post("/api/admin/branches", json={"name": "شعبه شیراز", "province_id": province}).status_code
		== 409
	)
	entries = org.db.scalars(select(AuditEntry).where(AuditEntry.entity == "branch")).all()
	assert [e.action for e in entries] == ["insert", "update"]


def test_employee_cannot_change_configuration(client_for):
	emp = client_for("emp")
	assert emp.get("/api/admin/branches").status_code == 200  # read for forms
	assert emp.post("/api/admin/branches", json={"name": "x", "province_id": 1}).status_code == 403
	assert emp.get("/api/admin/work-patterns").status_code == 403


def test_manager_sees_only_their_subtree(client_for, org):
	codes = {e["code"] for e in client_for("mgr").get("/api/admin/employees").json()}
	assert codes == {"T-MGR", "T-EMP"}
	assert client_for("mgr").get(f"/api/admin/employees/{org.other.id}").status_code == 404


def test_new_employee_queues_their_calculation(client_for, org):
	r = client_for("op").post(
		"/api/admin/employees",
		json={"code": "T-NEW", "first_name": "علی", "last_name": "نو", "start_date": "۱۴۰۵/۰۷/۰۱"},
	)
	assert r.status_code == 200, r.text
	assert r.json()["start_date"] == "1405/07/01" and r.json()["full_name"] == "علی نو"
	job = org.db.scalars(select(Job).order_by(Job.id.desc())).first()
	assert job.payload["range"] == ["1405/07/01", TODAY] and job.payload["employee_ids"] == [r.json()["id"]]


def test_bad_values_are_reported_by_field(client_for):
	op = client_for("op")
	r = op.post("/api/admin/shifts", json={"name": "S", "start_time": "25:00", "end_time": "16:00"})
	assert r.status_code == 422 and "start_time" in r.json()["message"]
	r = op.post(
		"/api/admin/shifts",
		json={
			"name": "S",
			"start_time": "08:00",
			"end_time": "16:00",
			"break_start_time": "17:00",
			"break_end_time": "17:30",
		},
	)
	assert r.status_code == 422


def test_work_pattern_with_days(client_for, org):
	op = client_for("op")
	days = [{"weekday": d, "shift_id": org.office.id} for d in range(6)] + [{"weekday": 6}]
	r = op.post("/api/admin/work-patterns", json={"name": "شش‌روزه", "days": days})
	assert r.status_code == 200, r.text
	pattern = r.json()
	assert len(pattern["days"]) == 7
	r = op.patch(
		f"/api/admin/work-patterns/{pattern['id']}",
		json={"days": [*days[:5], {"weekday": 5}, {"weekday": 6}]},
	)
	assert r.status_code == 200 and sum(1 for d in r.json()["days"] if d["shift_id"]) == 5
	dup = op.patch(
		f"/api/admin/work-patterns/{pattern['id']}", json={"days": [{"weekday": 1}, {"weekday": 1}]}
	)
	assert dup.status_code == 422


def test_rule_sets_are_admin_only_and_never_worse_than_the_law(client_for, org):
	baseline = org.db.scalar(select(LaborRuleSet).where(LaborRuleSet.is_legal_baseline))
	params = dict(baseline.parameters)
	assert client_for("op").post("/api/admin/rule-sets", json={}).status_code == 403
	admin = client_for("admin")
	worse = {**params, "annual_leave_days": params["annual_leave_days"] - 1}
	r = admin.post(
		"/api/admin/rule-sets", json={"name": "بد", "effective_from": "1405/07/01", "parameters": worse}
	)
	assert r.status_code == 422
	better = {**params, "annual_leave_days": params["annual_leave_days"] + 2}
	r = admin.post(
		"/api/admin/rule-sets",
		json={"name": "سخاوتمند", "effective_from": "1405/07/01", "parameters": better},
	)
	assert r.status_code == 200, r.text
	assert (
		admin.patch(f"/api/admin/rule-sets/{baseline.id}", json={"name": "x", "reason": "r"}).status_code
		== 422
	)
	assert (
		admin.patch(f"/api/admin/rule-sets/{r.json()['id']}", json={"description": "x"}).status_code == 422
	)  # reason


def test_settings_and_users(client_for, org):
	admin = client_for("admin")
	assert (
		admin.put("/api/admin/settings", json={"absence_warning_days": "5"}).json()["absence_warning_days"]
		== 5
	)
	assert admin.put("/api/admin/settings", json={"nope": 1}).status_code == 422
	r = admin.post(
		"/api/admin/users",
		json={
			"username": "New",
			"password": "long-enough-1",
			"roles": ["employee"],
			"employee_id": org.other.id,
		},
	)
	assert r.status_code == 200, r.text
	org.db.refresh(org.other)
	assert org.other.user_id == r.json()["id"]
	r = admin.patch(f"/api/admin/users/{org.users.admin.id}", json={"roles": ["operator"]})
	assert r.status_code == 422  # the last admin stays


def test_device_crud_never_returns_the_comm_key(client_for):
	op = client_for("op")
	r = op.post(
		"/api/devices",
		json={"name": "VF600", "adapter_type": "zkteco", "host": "192.168.1.20", "comm_key": "4321"},
	)
	assert r.status_code == 200, r.text
	assert r.json()["has_comm_key"] and "comm_key_encrypted" not in r.json() and "4321" not in r.text
	assert {a["code"] for a in op.get("/api/devices/adapters").json()} >= {"zkteco", "file_import"}
	assert client_for("emp").get("/api/devices").status_code == 403


def test_attendance_days_and_day_details(client_for, org):
	devices.ingest(
		org.db,
		org.device,
		[{"device_user_id": "77", "jdate": "1405/07/12", "time": t} for t in ("07:59", "16:31")],
		"device",
	)
	op = client_for("op")
	r = op.post("/api/attendance/recalculate", json={"from_date": "1405/07/12", "to_date": "1405/07/12"})
	assert r.json()["created"] == 4
	mine = (
		client_for("emp").get("/api/attendance", params={"from_date": "1405/07/01", "to_date": TODAY}).json()
	)
	assert [(d["jdate"], d["status"], d["first_in"]) for d in mine] == [("1405/07/12", "present", "07:59")]
	assert (
		client_for("emp")
		.get(
			"/api/attendance",
			params={"from_date": "1405/07/01", "to_date": TODAY, "employee_id": org.other.id},
		)
		.status_code
		== 403
	)
	detail = (
		client_for("mgr")
		.get("/api/attendance/day", params={"employee_id": org.employee.id, "jdate": "1405/07/12"})
		.json()
	)
	assert [p["time"] for p in detail["punches"]] == ["07:59:00", "16:31:00"] and detail["schedule"][
		"shift"
	] == "T-Office"


def test_periods_close_and_reopen(client_for, org):
	op = client_for("op")
	assert op.post("/api/periods/1405/7/close", json={}).status_code == 409  # not over yet
	r = op.post("/api/periods/1405/6/close", json={"note": "حقوق شهریور"})
	assert r.status_code == 200 and r.json()["status"] == "closed"
	months = op.get("/api/periods/1405").json()
	assert months[5]["status"] == "closed" and months[6]["status"] == "open"
	assert op.post("/api/periods/1405/6/reopen", json={}).status_code == 422  # needs a reason
	assert op.post("/api/periods/1405/6/reopen", json={"note": "اصلاح"}).json()["status"] == "open"


def test_reports_preview_and_export(client_for, org):
	op = client_for("op")
	op.post("/api/attendance/recalculate", json={"from_date": "1405/07/01", "to_date": TODAY})
	templates = op.get("/api/reports/templates").json()
	payroll = next(t for t in templates if t["source"] == "summary")
	r = op.post(
		"/api/reports/preview",
		json={"template_id": payroll["id"], "filters": {"from_date": "1405/07/01", "to_date": TODAY}},
	)
	assert r.status_code == 200, r.text
	assert r.json()["total_rows"] == 4
	r = op.post(
		"/api/reports/export",
		json={
			"spec": {"source": "daily", "columns": [{"field": "employee"}, {"field": "status"}]},
			"export_format": "csv",
		},
	)
	assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
	assert (
		client_for("emp")
		.post("/api/reports/preview", json={"spec": {"columns": [{"field": "employee"}]}})
		.status_code
		== 403
	)
	mgr_rows = (
		client_for("mgr").post("/api/reports/preview", json={"template_id": payroll["id"]}).json()["rows"]
	)
	assert {row["employee"] for row in mgr_rows} <= {"T-MGR", "T-EMP"}


def test_unknown_report_column_is_rejected(client_for):
	r = client_for("op").post(
		"/api/admin/report-templates", json={"name": "x", "columns": [{"field": "password_hash"}]}
	)
	assert r.status_code == 422


def test_change_own_password_keeps_this_session(client_for):
	emp = client_for("emp")
	bad = emp.post("/api/auth/password", json={"current_password": "wrong", "new_password": "another-long-1"})
	assert bad.status_code == 422
	r = emp.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "another-long-1"})
	assert r.status_code == 200, r.text
	assert emp.get("/api/me").status_code == 200


def test_device_errors_are_messages_not_crashes(client_for, org):
	op = client_for("op")
	r = op.post(
		"/api/devices", json={"name": "X", "adapter_type": "zkteco", "host": "10.0.0.5", "branch_id": 999999}
	)
	assert r.status_code == 422
	assert op.get(f"/api/devices/{org.device.id}").json()["name"] == "T-Device"
	assert op.get("/api/devices/imports").status_code == 200
	assert op.get("/api/attendance/day", params={"employee_id": 999999, "jdate": TODAY}).status_code == 404
