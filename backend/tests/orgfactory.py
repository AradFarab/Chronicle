"""A small test company: CEO > sales manager > sales expert, and an accountant under the CEO.
Every employee is also a user. Imported by tests/conftest.py (the `org` fixture) and by tests."""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

from sqlalchemy import select

from chronicle.db.models import (
	AppUser,
	AttendanceDevice,
	Department,
	Designation,
	DesignationAssignment,
	DeviceUserMap,
	Employee,
	Organization,
	Shift,
	ShiftSegment,
	UserRole,
	WorkPattern,
	WorkPatternAssignment,
	WorkPatternDay,
)
from chronicle.services.access import actor_for
from chronicle.setup import install

TODAY = "1405/07/14"  # a Tuesday
PASSWORD = "secret-pass-1405"  # set on test users that log in through the API


def make_user(db, username, *roles):
	user = AppUser(username=username, full_name=username)
	user.roles = [UserRole(role=r) for r in roles]
	db.add(user)
	db.flush()
	return user


def make_employee(db, code, designation=None, department=None, roles=("employee",), **kw):
	"""An employee is also a user (username = lower-case code); optionally holds a designation."""
	user = make_user(db, code.lower(), *roles)
	e = Employee(
		code=code,
		first_name="کارمند",
		last_name=code,
		start_date="1404/01/15",
		department_id=department.id if department else None,
		user_id=user.id,
		**kw,
	)
	db.add(e)
	db.flush()
	if designation:
		db.add(
			DesignationAssignment(employee_id=e.id, designation_id=designation.id, valid_from=e.start_date)
		)
		db.flush()
	return e, user


def build_org(db):
	"""CEO > sales manager > sales expert; the accountant sits right under the CEO."""
	install.run(db)
	ceo_d = db.scalar(select(Designation).where(Designation.is_ceo))
	mgr_d = Designation(name="مدیر فروش", parent_id=ceo_d.id)
	db.add(mgr_d)
	db.flush()
	expert_d = Designation(name="کارشناس فروش", parent_id=mgr_d.id)
	acct_d = Designation(name="حسابدار", parent_id=ceo_d.id)
	db.add_all([expert_d, acct_d])
	db.flush()
	sales = Department(name="فروش")
	finance = Department(name="مالی")
	db.add_all([sales, finance])
	db.flush()
	ceo, ceo_user = make_employee(db, "T-CEO", ceo_d, finance)
	manager, mgr_user = make_employee(db, "T-MGR", mgr_d, sales)
	employee, emp_user = make_employee(db, "T-EMP", expert_d, sales)
	other, other_user = make_employee(db, "T-OTHER", acct_d, finance)
	db.merge(Organization(id=1, name="شرکت آزمایشی"))
	op_user = make_user(db, "op", "admin")  # a system admin without an employee record
	admin_user = make_user(db, "admin", "admin")
	# Saturday-Wednesday 08:00-16:30 with a 40-minute lunch (470 minutes), Thursday/Friday off
	office = Shift(
		name="T-Office",
		start_time=time(8),
		end_time=time(16, 30),
		segments=[ShiftSegment(kind="break", start_minute=12 * 60 + 30, end_minute=13 * 60 + 10)],
		grace_late_minutes=5,
		grace_early_minutes=5,
	)
	db.add(office)
	db.flush()
	week = WorkPattern(name="T-Week", weekly_rest_day=6)
	week.days = [WorkPatternDay(weekday=d, shift_id=office.id) for d in range(5)] + [
		WorkPatternDay(weekday=5),
		WorkPatternDay(weekday=6),
	]
	db.add(week)
	db.flush()
	db.add(WorkPatternAssignment(target_type="company", work_pattern_id=week.id, valid_from="1405/01/01"))
	device = AttendanceDevice(name="T-Device", adapter_type="zkteco", host="10.0.0.1")
	db.add(device)
	db.flush()
	db.add(DeviceUserMap(device_id=device.id, device_user_id="77", employee_id=employee.id))
	db.flush()
	# actors: boss (the CEO's login), mgr, emp, op, admin; org.ceo / org.manager / org.employee are employees
	actors = {
		name: actor_for(db, u, TODAY)
		for name, u in (
			("boss", ceo_user),
			("mgr", mgr_user),
			("emp", emp_user),
			("op", op_user),
			("admin", admin_user),
			("anyone", other_user),
		)
	}
	return SimpleNamespace(
		db=db,
		ceo_designation=ceo_d,
		manager_designation=mgr_d,
		expert_designation=expert_d,
		accountant_designation=acct_d,
		sales=sales,
		finance=finance,
		ceo=ceo,
		manager=manager,
		employee=employee,
		other=other,
		office=office,
		week=week,
		device=device,
		users=SimpleNamespace(
			ceo=ceo_user, mgr=mgr_user, emp=emp_user, op=op_user, admin=admin_user, other=other_user
		),
		**actors,
	)
