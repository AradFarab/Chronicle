"""The business triggers that send SMS: leave and correction decisions, requests waiting for a
manager, and the hourly checks (shift reminders, missed punches, lateness, absence, the monthly
summary, birthdays).

A trigger decides *when* and *to whom*; a template (in the SMS section) decides *how*. Without an
active template for an event nothing is sent. Every trigger goes through `send_once`: no number,
no template, or a message already recorded for the same entity means nothing happens, and a
failure here never breaks the operation that caused it.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chronicle.clock import now
from chronicle.db.models import DailyAttendance, Employee, LeaveType, Request, SmsEvent, SmsMessage
from chronicle.db.models.org import ACTIVE
from chronicle.db.models.requests import APPROVED, CORRECTION, LEAVE, MISSION, PENDING, REJECTED
from chronicle.engine.daily import W_MISSING_PUNCH
from chronicle.jalali.dates import add_days, display, parse_jdate, to_persian_digits
from chronicle.services import access, approvals, sms_dispatch
from chronicle.services.punches import effective_punches
from chronicle.services.schedules import ScheduleResolver
from chronicle.services.sms_dispatch import DispatchError

log = logging.getLogger("chronicle.sms")

REMINDER_FROM_HOUR = 17  # the evening before, so an early shift is not reminded at dawn
SUMMARY_FROM_HOUR = 9
MISSED_CHECK_IN_AFTER = 60  # minutes after the shift starts


def send_once(
	session: Session, event_code: str, employee: Employee | None, context: dict[str, Any], entity_key: str
) -> SmsMessage | None:
	"""Dispatch unless there is no number, no template or already a message for this entity."""
	if employee is None or not employee.mobile:
		return None
	event = session.scalar(select(SmsEvent).where(SmsEvent.code == event_code))
	if event is None:
		return None
	if session.scalar(
		select(SmsMessage.id).where(SmsMessage.event_id == event.id, SmsMessage.entity_key == entity_key)
	):
		return None
	if sms_dispatch.readiness(session, event_code) is not None:
		return None
	try:
		with session.begin_nested():
			return sms_dispatch.dispatch(session, event_code, employee.mobile, context, entity_key=entity_key)
	except (DispatchError, IntegrityError):
		log.warning("sms %s for %s was not recorded", event_code, entity_key, exc_info=True)
		return None


def _has_template(session: Session, event_code: str) -> bool:
	return sms_dispatch.readiness(session, event_code) is None


# requests ----------------------------------------------------------------------------------------


def on_waiting(session: Session, request: Request) -> None:
	"""A leave request is waiting for a manager: tell the people the current step waits for."""
	if request.kind != LEAVE or request.status != PENDING:
		return
	requester = session.get(Employee, request.employee_id)
	leave_type = session.get(LeaveType, request.leave.leave_type_id)
	context = {
		"name": requester.full_name,
		"date": display(request.start_jdate),
		"leave_type": leave_type.name,
	}
	for employee_id in approvals.waiting_for(request):
		send_once(
			session,
			"leave_requested",
			session.get(Employee, employee_id),
			context,
			f"{request.id}:{employee_id}",
		)


def on_decided(session: Session, request: Request) -> None:
	"""A request reached its final answer: tell the employee (leave and punch corrections)."""
	if request.status not in (APPROVED, REJECTED):
		return
	employee = session.get(Employee, request.employee_id)
	if request.kind == LEAVE:
		leave_type = session.get(LeaveType, request.leave.leave_type_id)
		event = "leave_approved" if request.status == APPROVED else "leave_rejected"
		context = {
			"name": employee.full_name,
			"date": display(request.start_jdate),
			"leave_type": leave_type.name,
		}
		send_once(session, event, employee, context, f"{request.id}")
	elif request.kind == CORRECTION:
		status = "تأیید شد" if request.status == APPROVED else "رد شد"
		context = {"name": employee.full_name, "date": display(request.start_jdate), "status": status}
		send_once(session, "correction_decided", employee, context, f"{request.id}")


# the hourly checks -------------------------------------------------------------------------------


def _active_employees(session: Session, jdate: str) -> list[Employee]:
	return [
		e
		for e in session.scalars(select(Employee).where(Employee.status == ACTIVE).order_by(Employee.id))
		if e.start_date <= jdate and (not e.end_date or jdate <= e.end_date)
	]


def _away(session: Session, employee_id: int, jdate: str) -> bool:
	"""An approved leave or mission covers the day."""
	return (
		session.scalar(
			select(Request.id).where(
				Request.employee_id == employee_id,
				Request.kind.in_((LEAVE, MISSION)),
				Request.status == APPROVED,
				Request.start_jdate <= jdate,
				Request.end_jdate >= jdate,
			)
		)
		is not None
	)


def _clock(minute: int) -> str:
	return to_persian_digits(f"{minute % 1440 // 60:02d}:{minute % 60:02d}")


def shift_reminders(session: Session, today: str) -> int:
	"""In the evening: tomorrow's shift for everyone who works tomorrow."""
	if now().hour < REMINDER_FROM_HOUR or not _has_template(session, "shift_reminder"):
		return 0
	from chronicle.services.leave import working_days

	tomorrow = add_days(today, 1)
	resolver, sent = ScheduleResolver(session), 0
	for employee in _active_employees(session, tomorrow):
		if tomorrow not in working_days(session, employee.id, tomorrow, tomorrow, resolver):
			continue
		if _away(session, employee.id, tomorrow):
			continue
		shift = resolver.resolve(employee.id, tomorrow).shift
		if shift is None:
			continue
		context = {
			"name": employee.full_name,
			"date": display(tomorrow),
			"time": _clock(shift.start),
			"shift": shift.name,
		}
		sent += (
			send_once(session, "shift_reminder", employee, context, f"{employee.id}:{tomorrow}") is not None
		)
	return sent


def missed_check_in(session: Session, today: str) -> int:
	"""Today's shift began over an hour ago and the employee has not punched."""
	if not _has_template(session, "missed_check_in"):
		return 0
	from chronicle.services.leave import working_days

	at = now()
	minute_now = at.hour * 60 + at.minute
	resolver, sent = ScheduleResolver(session), 0
	for employee in _active_employees(session, today):
		shift = resolver.resolve(employee.id, today).shift
		if shift is None or minute_now < shift.start + MISSED_CHECK_IN_AFTER or minute_now >= shift.end:
			continue
		if today not in working_days(session, employee.id, today, today, resolver) or _away(
			session, employee.id, today
		):
			continue
		if effective_punches(session, employee.id, today):
			continue
		context = {"name": employee.full_name, "date": display(today), "time": _clock(shift.start)}
		sent += send_once(session, "missed_check_in", employee, context, f"{employee.id}:{today}") is not None
	return sent


def _yesterday_rows(session: Session, today: str) -> list[tuple[DailyAttendance, Employee]]:
	yesterday = add_days(today, -1)
	return list(
		session.execute(
			select(DailyAttendance, Employee)
			.join(Employee, Employee.id == DailyAttendance.employee_id)
			.where(DailyAttendance.jdate == yesterday, Employee.status == ACTIVE)
			.order_by(DailyAttendance.employee_id)
		).all()
	)


def previous_day_notices(session: Session, today: str) -> int:
	"""Yesterday's finished days: a punch left unpaired (to the employee), lateness and absence
	(to their managers)."""
	wanted = {e: _has_template(session, e) for e in ("missed_check_out", "late_arrival", "absence_notice")}
	if not any(wanted.values()):
		return 0
	sent = 0
	for row, employee in _yesterday_rows(session, today):
		date = display(row.jdate)
		if wanted["missed_check_out"] and W_MISSING_PUNCH in (row.warnings or []):
			context = {"name": employee.full_name, "date": date}
			sent += (
				send_once(session, "missed_check_out", employee, context, f"{employee.id}:{row.jdate}")
				is not None
			)
		managers = None
		if (wanted["late_arrival"] and row.late_minutes > 0) or (wanted["absence_notice"] and row.absent_day):
			managers = [
				session.get(Employee, m) for m in access.parent_approvers(session, employee.id, today)
			]
		for manager in managers or []:
			if wanted["late_arrival"] and row.late_minutes > 0:
				context = {
					"name": employee.full_name,
					"date": date,
					"minutes": to_persian_digits(row.late_minutes),
				}
				key = f"{employee.id}:{row.jdate}:{manager.id}"
				sent += send_once(session, "late_arrival", manager, context, key) is not None
			if wanted["absence_notice"] and row.absent_day:
				context = {"name": employee.full_name, "date": date}
				key = f"{employee.id}:{row.jdate}:{manager.id}"
				sent += send_once(session, "absence_notice", manager, context, key) is not None
	return sent


def monthly_summaries(session: Session, today: str) -> int:
	"""In the first days of a month: last month's worked hours, with a link to the month page."""
	year, month, day = parse_jdate(today)
	if day > 3 or now().hour < SUMMARY_FROM_HOUR or not _has_template(session, "monthly_summary"):
		return 0
	from sqlalchemy import func

	from chronicle.db.models.attendance import DailyAttendance as Day

	py, pm = (year, month - 1) if month > 1 else (year - 1, 12)
	totals = dict(
		session.execute(
			select(Day.employee_id, func.coalesce(func.sum(Day.worked_minutes), 0))
			.where(Day.jyear == py, Day.jmonth == pm)
			.group_by(Day.employee_id)
		).all()
	)
	from chronicle.jalali.dates import MONTH_NAMES

	sent = 0
	for employee in _active_employees(session, today):
		if employee.id not in totals:
			continue
		minutes = int(totals[employee.id])
		context = {
			"name": employee.full_name,
			"month": f"{MONTH_NAMES[pm - 1]} {to_persian_digits(py)}",
			"hours": to_persian_digits(f"{minutes // 60}:{minutes % 60:02d}"),
			"link": f"/month/{py}/{pm}",
		}
		sent += (
			send_once(session, "monthly_summary", employee, context, f"{employee.id}:{py}-{pm:02d}")
			is not None
		)
	return sent


def birthdays(session: Session, today: str) -> int:
	"""Congratulate whoever's birthday (Jalali month and day) is today, once a year."""
	if now().hour < SUMMARY_FROM_HOUR or not _has_template(session, "birthday"):
		return 0
	_y, month, day = parse_jdate(today)
	sent = 0
	for employee in _active_employees(session, today):
		if not employee.birth_date:
			continue
		_by, bm, bd = parse_jdate(employee.birth_date)
		if (bm, bd) == (month, day):
			sent += (
				send_once(
					session, "birthday", employee, {"name": employee.full_name}, f"{employee.id}:{today[:4]}"
				)
				is not None
			)
	return sent


def run_periodic(session: Session, today: str) -> dict[str, int]:
	"""The worker's hourly job. Each check is independent: one failing does not stop the rest."""
	out: dict[str, int] = {}
	for check in (shift_reminders, missed_check_in, previous_day_notices, monthly_summaries, birthdays):
		try:
			with session.begin_nested():
				out[check.__name__] = check(session, today)
		except Exception:
			log.exception("sms check %s failed", check.__name__)
			out[check.__name__] = -1
	return out
