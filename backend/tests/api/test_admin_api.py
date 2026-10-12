"""Configuration, devices, attendance, periods and reports over HTTP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from orgfactory import PASSWORD, TODAY
from sqlalchemy import select

from chronicle.api import deps
from chronicle.db.models import AuditEntry, DesignationAssignment, Job, LaborRuleSet
from chronicle.services import devices, users


@pytest.fixture(autouse=True)
def fixed_today(app):
	app.dependency_overrides[deps.today] = lambda: TODAY
	yield
	app.dependency_overrides.clear()


def test_admin_manages_work_locations_and_audit_is_written(client_for, org):
	op = client_for("op")
	province = op.get("/api/admin/provinces").json()[0]["id"]
	r = op.post("/api/admin/work-locations", json={"name": "دفتر شیراز", "province_id": province})
	assert r.status_code == 200, r.text
	branch = r.json()
	r = op.patch(f"/api/admin/work-locations/{branch['id']}", json={"city": "شیراز"})
	assert r.json()["city"] == "شیراز"
	assert (
		op.post("/api/admin/work-locations", json={"name": "دفتر شیراز", "province_id": province}).status_code
		== 409
	)
	entries = org.db.scalars(select(AuditEntry).where(AuditEntry.entity == "work_location")).all()
	assert [e.action for e in entries] == ["insert", "update"]


def test_employee_cannot_change_configuration(client_for):
	emp = client_for("emp")
	assert emp.get("/api/admin/work-locations").status_code == 200  # read for forms
	assert emp.post("/api/admin/work-locations", json={"name": "x", "province_id": 1}).status_code == 403
	assert emp.get("/api/admin/work-patterns").status_code == 403


def test_manager_sees_only_their_subtree(client_for, org):
	codes = {e["code"] for e in client_for("mgr").get("/api/admin/employees").json()}
	assert codes == {"T-MGR", "T-EMP"}
	assert client_for("mgr").get(f"/api/admin/employees/{org.other.id}").status_code == 404


def test_new_employee_queues_their_calculation(client_for, org):
	r = client_for("op").post(
		"/api/admin/employees",
		json={
			"code": "T-NEW",
			"first_name": "علی",
			"last_name": "نو",
			"start_date": "۱۴۰۵/۰۷/۰۱",
			"password": "long-enough-1",
		},
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
			"segments": [{"kind": "break", "start_minute": 17 * 60, "end_minute": 17 * 60 + 30}],
		},
	)
	assert r.status_code == 422


def test_shift_with_breaks_and_overtime_window(client_for):
	op = client_for("op")
	segments = [
		{"kind": "break", "start_minute": 12 * 60, "end_minute": 12 * 60 + 45},
		{"kind": "break", "start_minute": 15 * 60, "end_minute": 15 * 60 + 15},
		{"kind": "overtime", "start_minute": 17 * 60, "end_minute": 19 * 60},
	]
	r = op.post(
		"/api/admin/shifts",
		json={"name": "۹ تا ۵", "start_time": "08:00", "end_time": "17:00", "segments": segments},
	)
	assert r.status_code == 200, r.text
	assert [(g["kind"], g["start_minute"]) for g in r.json()["segments"]] == [
		("break", 720),
		("break", 900),
		("overtime", 1020),
	]
	inside = [{"kind": "overtime", "start_minute": 16 * 60, "end_minute": 18 * 60}]
	r = op.patch(f"/api/admin/shifts/{r.json()['id']}", json={"segments": inside})
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
	assert client_for("emp").post("/api/admin/rule-sets", json={}).status_code == 403
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
		json={"username": "New", "password": "long-enough-1", "roles": ["admin"]},
	)
	assert r.status_code == 200, r.text  # a login without an employee record
	assert admin.patch(f"/api/admin/users/{org.users.op.id}", json={"roles": ["employee"]}).status_code == 200
	assert admin.patch(f"/api/admin/users/{r.json()['id']}", json={"roles": ["employee"]}).status_code == 200
	r = admin.patch(f"/api/admin/users/{org.users.admin.id}", json={"roles": ["employee"]})
	assert r.status_code == 422  # the last admin stays
	assert (
		admin.patch(f"/api/admin/users/{org.users.admin.id}", json={"roles": ["operator"]}).status_code == 422
	)


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
		"/api/devices",
		json={"name": "X", "adapter_type": "zkteco", "host": "10.0.0.5", "work_location_id": 999999},
	)
	assert r.status_code == 422
	assert op.get(f"/api/devices/{org.device.id}").json()["name"] == "T-Device"
	assert op.get("/api/devices/imports").status_code == 200
	assert op.get("/api/attendance/day", params={"employee_id": 999999, "jdate": TODAY}).status_code == 404


def test_creating_an_employee_creates_the_login_and_the_first_designation(client_for, org):
	admin = client_for("admin")
	r = admin.post(
		"/api/admin/employees",
		json={
			"code": "T-NEW",
			"detail_code": "10020030",
			"first_name": "نگین",
			"last_name": "نوری",
			"start_date": "1405/07/01",
			"password": "long-enough-1",
			"designation_id": org.expert_designation.id,
			"department_id": org.sales.id,
		},
	)
	assert r.status_code == 200, r.text
	body = r.json()
	assert body["username"] == "t-new" and body["detail_code"] == "10020030" and body["is_active_user"]
	assert [d["designation_id"] for d in body["designations"] if d["current"]] == [org.expert_designation.id]
	# the new person can log in with the password given on creation
	other = TestClient(admin.app, headers={"X-Chronicle": "1"})
	assert (
		other.post("/api/auth/login", json={"username": "t-new", "password": "long-enough-1"}).status_code
		== 200
	)
	assert other.get("/api/me").json()["employee"]["code"] == "T-NEW"
	# the same accounting detail code cannot be given twice
	again = admin.post(
		"/api/admin/employees",
		json={
			"code": "T-NEW2",
			"detail_code": "10020030",
			"first_name": "a",
			"last_name": "b",
			"start_date": "1405/07/01",
			"password": "long-enough-1",
		},
	)
	assert again.status_code == 409
	# a password is needed
	assert (
		admin.post(
			"/api/admin/employees",
			json={"code": "T-X", "first_name": "a", "last_name": "b", "start_date": "1405/07/01"},
		).status_code
		== 422
	)


def test_a_person_who_left_can_no_longer_log_in(client_for, org):
	admin = client_for("admin")
	r = admin.patch(
		f"/api/admin/employees/{org.employee.id}", json={"status": "left", "end_date": "1405/07/10"}
	)
	assert r.status_code == 200 and not r.json()["is_active_user"]
	fresh = TestClient(admin.app, headers={"X-Chronicle": "1"})
	from orgfactory import PASSWORD

	org.users.emp.password_hash = users.hash_password(PASSWORD)
	org.db.flush()
	assert fresh.post("/api/auth/login", json={"username": "t-emp", "password": PASSWORD}).status_code == 401


def test_only_the_admin_changes_employees(client_for, org):
	assert client_for("mgr").post("/api/admin/employees", json={"code": "Z"}).status_code == 403
	assert (
		client_for("mgr").patch(f"/api/admin/employees/{org.employee.id}", json={"mobile": "09"}).status_code
		== 403
	)


def test_designation_tree_rules(client_for, org):
	admin = client_for("admin")
	# nothing can be placed below itself, and the CEO designation stays at the top
	loop = admin.patch(
		f"/api/admin/designations/{org.manager_designation.id}", json={"parent_id": org.expert_designation.id}
	)
	assert loop.status_code == 422
	assert (
		admin.patch(
			f"/api/admin/designations/{org.manager_designation.id}", json={"is_ceo": True}
		).status_code
		== 422
	)
	# taking a designation away keeps the history
	hold = org.db.scalars(
		select(DesignationAssignment).where(DesignationAssignment.employee_id == org.employee.id)
	).one()
	r = admin.patch(f"/api/admin/designation-assignments/{hold.id}", json={"valid_to": "1405/07/10"})
	assert r.status_code == 200 and r.json()["valid_to"] == "1405/07/10"
	job = org.db.scalars(select(Job).order_by(Job.id.desc())).first()
	assert job.payload["employee_ids"] == [org.employee.id]


def test_delegation_over_http(client_for, org):
	mgr = client_for("mgr")
	r = mgr.post("/api/delegations", json={"delegate_id": org.other.id, "valid_to": "1405/07/30"})
	assert r.status_code == 200, r.text
	assert r.json()["delegator_id"] == org.manager.id and r.json()["current"]
	assert [d["id"] for d in client_for("emp").get("/api/delegations").json()] == []
	assert len(mgr.get("/api/delegations").json()) == 1
	assert (
		client_for("emp").post("/api/delegations", json={"delegate_id": org.other.id}).status_code == 422
	)  # nobody below
	assert client_for("emp").delete(f"/api/delegations/{r.json()['id']}").status_code == 403
	assert mgr.delete(f"/api/delegations/{r.json()['id']}").status_code == 200


def test_rotation_offset_is_part_of_the_assignment(client_for, org):
	admin = client_for("admin")
	r = admin.post(
		"/api/admin/work-pattern-assignments",
		json={
			"target_type": "employee",
			"employee_id": org.employee.id,
			"work_pattern_id": org.week.id,
			"valid_from": "1405/07/01",
			"cycle_offset_days": 14,
		},
	)
	assert r.status_code == 200 and r.json()["cycle_offset_days"] == 14
	bad = admin.post(
		"/api/admin/work-pattern-assignments",
		json={
			"target_type": "company",
			"work_pattern_id": org.week.id,
			"valid_from": "1405/07/01",
			"cycle_offset_days": -1,
		},
	)
	assert bad.status_code == 422


def test_excel_import_over_http(client_for, org):
	import io

	from openpyxl import load_workbook

	admin = client_for("admin")
	names = {i["name"] for i in admin.get("/api/import").json()}
	assert {"employees", "work-locations", "designations", "holidays", "devices", "device-users"} <= names
	sample = admin.get("/api/import/departments/template")
	assert sample.status_code == 200 and "spreadsheetml" in sample.headers["content-type"]
	wb = load_workbook(io.BytesIO(sample.content))
	sheet = wb.worksheets[0]
	sheet["A2"] = "لجستیک"
	sheet["A3"] = "لجستیک"  # a duplicate: the second row must be reported and nothing saved
	out = io.BytesIO()
	wb.save(out)
	files = {"file": ("departments.xlsx", out.getvalue(), "application/octet-stream")}
	bad = admin.post("/api/import/departments", files=files).json()
	assert bad["imported"] is False and [e["row"] for e in bad["errors"]] == [3]
	assert "لجستیک" not in {d["name"] for d in admin.get("/api/admin/departments").json()}
	sheet["A3"] = "انبار"
	out = io.BytesIO()
	wb.save(out)
	files = {"file": ("departments.xlsx", out.getvalue(), "application/octet-stream")}
	assert admin.post("/api/import/departments", files=files).json()["created"] == 2
	assert {"لجستیک", "انبار"} <= {d["name"] for d in admin.get("/api/admin/departments").json()}
	assert client_for("mgr").get("/api/import").status_code == 403
	assert admin.get("/api/import/nope/template").status_code == 404


def test_a_manager_can_list_everyone_to_pick_a_delegate(client_for, org):
	people = client_for("mgr").get("/api/people/active").json()
	assert {p["code"] for p in people} >= {"T-CEO", "T-MGR", "T-EMP", "T-OTHER"}  # not only their team
	assert client_for("emp").get("/api/people/active").status_code == 403


def test_one_pattern_for_many_people_at_once(client_for, org):
	op = client_for("op")
	people = [org.employee.id, org.other.id, org.manager.id]
	r = op.post(
		"/api/admin/work-pattern-assignments/bulk",
		json={"employee_ids": people, "work_pattern_id": org.week.id, "valid_from": "1405/07/01"},
	)
	assert r.status_code == 200, r.text
	assert sorted(a["employee_id"] for a in r.json()) == sorted(people)
	assert all(a["target_type"] == "employee" for a in r.json())
	# all or nothing: one unknown person and nobody is assigned
	before = len(op.get("/api/admin/work-pattern-assignments").json())
	r = op.post(
		"/api/admin/work-pattern-assignments/bulk",
		json={
			"employee_ids": [org.employee.id, 999999],
			"work_pattern_id": org.week.id,
			"valid_from": "1405/07/05",
		},
	)
	assert r.status_code == 422
	assert len(op.get("/api/admin/work-pattern-assignments").json()) == before
	assert (
		client_for("emp")
		.post(
			"/api/admin/work-pattern-assignments/bulk",
			json={"employee_ids": people, "work_pattern_id": org.week.id, "valid_from": "1405/07/01"},
		)
		.status_code
		== 403
	)


def test_backups_are_taken_listed_downloaded_and_pruned(client_for, tmp_path, monkeypatch):
	import io
	import zipfile

	from chronicle.config import get_settings
	from chronicle.services import backup
	from tests.conftest import TEST_DATABASE_URL

	if not backup.tools_available():
		pytest.skip("pg_dump is not installed")
	monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
	monkeypatch.setattr(get_settings(), "database_url", TEST_DATABASE_URL)
	op = client_for("op")
	assert client_for("emp").get("/api/admin/backups").status_code == 403
	r = op.post("/api/admin/backups")
	if r.status_code == 422 and "version mismatch" in r.text:
		pytest.skip("pg_dump is older than the database server")
	assert r.status_code == 200, r.text
	name = r.json()["name"]
	assert name.startswith("chronicle-manual-14") and r.json()["jdate"].startswith("14")
	listing = op.get("/api/admin/backups").json()
	assert [b["name"] for b in listing["backups"]] == [name] and listing["schedule"]["keep"] == 14
	download = op.get(f"/api/admin/backups/{name}")
	assert download.status_code == 200
	with zipfile.ZipFile(io.BytesIO(download.content)) as z:
		assert {"database.dump", "manifest.json"} <= set(z.namelist())
	assert op.get("/api/admin/backups/..%2F..%2Fetc%2Fpasswd").status_code == 404
	assert op.put("/api/admin/backups/schedule", json={"hour": 30}).status_code == 422
	assert op.put("/api/admin/backups/schedule", json={"hour": 3, "keep": 2}).json()["keep"] == 2
	assert op.delete(f"/api/admin/backups/{name}").json() == {"ok": True}
	assert op.get("/api/admin/backups").json()["backups"] == []
