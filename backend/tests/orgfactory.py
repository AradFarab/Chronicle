"""A small test company: root > فروش (manager M, reports to the CEO) > تیم فروش (no manager):
E works there. Imported by tests/conftest.py (the `org` fixture) and by tests directly."""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

from sqlalchemy import select

from hozur.db.models import (
	AppUser,
	AttendanceDevice,
	Department,
	DeviceUserMap,
	Employee,
	Organization,
	Shift,
	UserRole,
	WorkPattern,
	WorkPatternAssignment,
	WorkPatternDay,
)
from hozur.services.access import actor_for
from hozur.setup import data, install

TODAY = "1405/07/14"  # a Tuesday
PASSWORD = "secret-pass-1405"  # set on test users that log in through the API


def make_user(db, username, *roles):
	user = AppUser(username=username, full_name=username)
	user.roles = [UserRole(role=r) for r in roles]
	db.add(user)
	db.flush()
	return user


def make_employee(db, code, department=None, user=None, **kw):
	e = Employee(
		code=code,
		first_name="کارمند",
		last_name=code,
		start_date="1404/01/15",
		department_id=department.id if department else None,
		user_id=user.id if user else None,
		**kw,
	)
	db.add(e)
	db.flush()
	return e


def build_org(db):
	install.run(db)
	root = db.scalar(select(Department).where(Department.name == data.ROOT_DEPARTMENT))
	ceo_user = make_user(db, "ceo", "ceo", "employee")
	mgr_user = make_user(db, "mgr", "manager", "employee")
	emp_user = make_user(db, "emp", "employee")
	op_user = make_user(db, "op", "operator")
	admin_user = make_user(db, "admin", "admin")
	ceo = make_employee(db, "T-CEO", root, ceo_user)
	sales = Department(name="فروش", parent_id=root.id, is_group=True)
	db.add(sales)
	db.flush()
	team = Department(name="تیم فروش", parent_id=sales.id)
	db.add(team)
	db.flush()
	manager = make_employee(db, "T-MGR", sales, mgr_user, reports_to_id=ceo.id)
	sales.manager_id = manager.id
	employee = make_employee(db, "T-EMP", team, emp_user)
	other = make_employee(db, "T-OTHER", root)
	db.merge(Organization(id=1, name="شرکت آزمایشی", ceo_id=ceo.id))
	# Saturday-Wednesday 08:00-16:30 with a 40-minute lunch (470 minutes), Thursday/Friday off
	office = Shift(
		name="T-Office",
		start_time=time(8),
		end_time=time(16, 30),
		break_start_time=time(12, 30),
		break_end_time=time(13, 10),
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
		name: actor_for(db, u)
		for name, u in (
			("boss", ceo_user),
			("mgr", mgr_user),
			("emp", emp_user),
			("op", op_user),
			("admin", admin_user),
		)
	}
	return SimpleNamespace(
		db=db,
		root=root,
		sales=sales,
		team=team,
		ceo=ceo,
		manager=manager,
		employee=employee,
		other=other,
		office=office,
		week=week,
		device=device,
		users=SimpleNamespace(ceo=ceo_user, mgr=mgr_user, emp=emp_user, op=op_user, admin=admin_user),
		**actors,
	)
