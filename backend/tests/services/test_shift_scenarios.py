"""Real-life schedules: 12-hour night shifts that end the next morning, and guards who
rotate two weeks on mornings and two weeks on nights."""

from __future__ import annotations

from datetime import time

from orgfactory import TODAY
from sqlalchemy import select

from hozur.db.models import DailyAttendance, Shift, WorkPattern, WorkPatternAssignment, WorkPatternDay
from hozur.jalali.dates import add_days
from hozur.services import attendance, devices
from hozur.services.schedules import resolve


def punch(org, jdate, clock):
	devices.ingest(org.db, org.device, [{"device_user_id": "77", "jdate": jdate, "time": clock}], "device")


def row(org, jdate):
	return org.db.scalar(
		select(DailyAttendance).where(
			DailyAttendance.employee_id == org.employee.id, DailyAttendance.jdate == jdate
		)
	)


def assign(org, pattern, valid_from):
	org.db.add(
		WorkPatternAssignment(
			target_type="employee",
			employee_id=org.employee.id,
			work_pattern_id=pattern.id,
			valid_from=valid_from,
		)
	)
	org.db.flush()


def test_18_to_06_shift_on_consecutive_nights_counts_each_night_once(org):
	night = Shift(name="T-12h-night", start_time=time(18), end_time=time(6))
	org.db.add(night)
	org.db.flush()
	every_night = WorkPattern(name="T-Nights")  # Friday is the weekly rest day
	every_night.days = [WorkPatternDay(weekday=d, shift_id=night.id) for d in range(7)]
	org.db.add(every_night)
	org.db.flush()
	assign(org, every_night, "1405/07/01")
	# Saturday 18:00 -> Sunday 06:00, Sunday 18:00 -> Monday 06:00
	punch(org, "1405/07/11", "18:00")
	punch(org, "1405/07/12", "06:00")
	punch(org, "1405/07/12", "18:00")
	punch(org, "1405/07/13", "06:00")
	attendance.recalculate(org.db, ["1405/07/11", "1405/07/12"], TODAY, "test", [org.employee.id])
	first, second = row(org, "1405/07/11"), row(org, "1405/07/12")
	for day in (first, second):
		assert (day.status, day.worked_minutes, day.first_in, day.last_out) == (
			"present",
			720,
			time(18),
			time(6),
		)
		assert day.night_work_minutes == 480  # 22:00-06:00 (Article 53)
		assert day.absence_minutes == 0


def test_two_weeks_mornings_then_two_weeks_nights(org):
	morning = Shift(name="T-Guard-AM", start_time=time(6), end_time=time(18))
	night = Shift(name="T-Guard-PM", start_time=time(18), end_time=time(6))
	org.db.add_all([morning, night])
	org.db.flush()
	guard = WorkPattern(name="T-Guard-28", pattern_type="rotating", cycle_start_date="1405/07/01")
	guard.days = [WorkPatternDay(cycle_day=i, shift_id=morning.id) for i in range(1, 15)] + [
		WorkPatternDay(cycle_day=i, shift_id=night.id) for i in range(15, 29)
	]
	org.db.add(guard)
	org.db.flush()
	assign(org, guard, "1405/07/01")
	shifts = [resolve(org.db, org.employee.id, add_days("1405/07/01", n)).shift.name for n in range(56)]
	assert shifts[:14] == ["T-Guard-AM"] * 14 and shifts[14:28] == ["T-Guard-PM"] * 14
	assert shifts[28:56] == shifts[:28]  # the cycle repeats
	assert resolve(org.db, org.employee.id, "1405/07/01").rotating
