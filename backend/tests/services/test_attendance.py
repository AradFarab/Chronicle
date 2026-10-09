"""Daily attendance: inputs gathered from the database, engine result stored, audit on change."""

from __future__ import annotations

from datetime import time

from orgfactory import TODAY
from sqlalchemy import func, select

from hozur.db.models import (
	AttendancePeriod,
	AuditEntry,
	DailyAttendance,
	Holiday,
	LeaveType,
	RawPunch,
)
from hozur.services import attendance, devices, leave, requests, settings

SUNDAY = "1405/07/12"
MONDAY = "1405/07/13"


def punch(org, jdate, clock, user="77"):
	devices.ingest(org.db, org.device, [{"device_user_id": user, "jdate": jdate, "time": clock}], "device")


def day(org, jdate, employee=None):
	return org.db.scalar(
		select(DailyAttendance).where(
			DailyAttendance.employee_id == (employee or org.employee).id, DailyAttendance.jdate == jdate
		)
	)


def calc(org, *dates, ids=None):
	return attendance.recalculate(org.db, dates, TODAY, "test", ids or [org.employee.id])


def test_a_full_day_is_present(org):
	punch(org, SUNDAY, "07:58")
	punch(org, SUNDAY, "16:35")
	assert calc(org, SUNDAY).created == 1
	row = day(org, SUNDAY)
	assert (row.status, row.worked_minutes, row.credited_minutes) == ("present", 477, 470)
	assert (row.first_in, row.last_out, row.punch_count) == (time(7, 58), time(16, 35), 2)
	assert (row.shift_id, row.work_pattern_id, row.department_id, row.designation_id) == (
		org.office.id,
		org.week.id,
		org.sales.id,
		org.expert_designation.id,
	)
	assert row.rule_set_id is not None and row.weekday == 1


def test_no_punches_on_a_workday_is_absent_and_thursday_is_a_rest_day(org):
	calc(org, SUNDAY, "1405/07/10")  # Sunday, Thursday
	assert (day(org, SUNDAY).status, day(org, SUNDAY).absent_day) == ("absent", True)
	thursday = day(org, "1405/07/10")
	assert thursday.status in ("rest_day", "not_scheduled") and not thursday.absent_day


def test_company_holiday_is_a_holiday(org):
	org.db.add(
		Holiday(
			jdate=MONDAY,
			title="تعطیلی شرکت",
			holiday_type="company_internal",
			scope="company",
			source="manual",
		)
	)
	org.db.flush()
	calc(org, MONDAY)
	row = day(org, MONDAY)
	assert (row.day_type, row.holiday_title, row.absent_day) == ("company_holiday", "تعطیلی شرکت", False)


def test_approved_daily_leave_is_stored_per_leave_type(org):
	earned = org.db.scalar(select(LeaveType).where(LeaveType.name == "استحقاقی"))
	leave.add_entry(org.db, org.employee.id, earned.id, leave.ALLOCATION, "1405/01/01", 10)
	r = requests.submit(
		org.db,
		org.op,
		"leave",
		{
			"employee_id": org.employee.id,
			"leave_type_id": earned.id,
			"unit": "daily",
			"from_date": SUNDAY,
			"to_date": SUNDAY,
		},
		TODAY,
	)
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)  # admin entries: the parent approves
	assert r.status == "approved"
	calc(org, SUNDAY)
	row = day(org, SUNDAY)
	assert (row.status, row.leave_days, row.credited_minutes) == ("leave", 1, 470)
	assert [(lv.leave_type_id, lv.minutes) for lv in row.leaves] == [(earned.id, 470)]


def test_recalculation_writes_audit_only_when_something_changed(org):
	calc(org, SUNDAY)
	assert day(org, SUNDAY).status == "absent"
	assert calc(org, SUNDAY).unchanged == 1
	punch(org, SUNDAY, "08:00")
	punch(org, SUNDAY, "16:30")
	outcome = calc(org, SUNDAY)
	assert outcome.updated == 1
	entry = org.db.scalar(select(AuditEntry).where(AuditEntry.entity == "daily_attendance"))
	assert entry.action == "update" and "status" in entry.changed_fields
	assert (entry.before["status"], entry.after["status"]) == ("absent", "present")


def test_closed_period_and_future_days_are_not_touched(org):
	org.db.add(AttendancePeriod(jyear=1405, jmonth=6, status="closed", closed_at=func.now()))
	org.db.flush()
	outcome = calc(org, "1405/06/30", "1405/07/20")
	assert (outcome.skipped, outcome.created) == (1, 0)
	assert day(org, "1405/06/30") is None


def test_days_outside_employment_are_removed(org):
	calc(org, SUNDAY)
	org.employee.end_date = "1405/07/01"
	org.db.flush()
	assert calc(org, SUNDAY).removed == 1
	assert day(org, SUNDAY) is None


def test_everyone_employed_is_calculated_when_no_one_is_named(org):
	attendance.recalculate(org.db, [SUNDAY], TODAY, "test")
	count = org.db.scalar(
		select(func.count()).select_from(DailyAttendance).where(DailyAttendance.jdate == SUNDAY)
	)
	assert count == 4  # ceo, manager, employee, other


def test_overnight_shift_keeps_the_next_morning_punch(org):
	from hozur.db.models import Shift, ShiftOverride

	night = Shift(name="T-Night", start_time=time(22), end_time=time(6))
	org.db.add(night)
	org.db.flush()
	org.db.add(ShiftOverride(employee_id=org.employee.id, jdate=SUNDAY, shift_id=night.id, reason="شب‌کاری"))
	org.db.flush()
	punch(org, SUNDAY, "21:55")
	punch(org, MONDAY, "06:05")
	calc(org, SUNDAY)
	row = day(org, SUNDAY)
	assert (row.status, row.worked_minutes, row.last_out) == ("present", 490, time(6, 5))
	assert row.night_work_minutes > 0


def test_absence_warning_after_consecutive_absent_days(org):
	settings.set_value(org.db, "absence_warning_days", 3)
	calc(org, "1405/07/08", "1405/07/09", "1405/07/10", "1405/07/11", "1405/07/12", "1405/07/13")
	# Tue 08, Wed 09 absent; Thu 10 / Fri 11 off; Sat 12 (Sunday is 07/12)... all absent
	warnings = attendance.absence_warnings(org.db, TODAY, [org.employee.id])
	assert warnings and warnings[0]["employee_id"] == org.employee.id and warnings[0]["days"] >= 3
	assert org.db.scalar(select(func.count()).select_from(RawPunch)) == 0
