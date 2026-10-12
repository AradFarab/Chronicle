"""Leave balances as a ledger: a balance is never edited, it is the sum of its entries
(allocation, usage, reversal, carry-over, expiry, adjustment), as in Frappe HR."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chronicle.calendar.service import holidays_by_date
from chronicle.db.models import Designation, Employee, LeaveLedgerEntry, LeaveType, WorkLocation
from chronicle.db.models.org import SUSPENDED
from chronicle.engine.periodic import annual_leave_entitlement, year_end_carry_over
from chronicle.jalali.calendar import COMPANY_HOLIDAY, OFFICIAL_HOLIDAY, resolve_day
from chronicle.jalali.dates import iter_days, month_bounds, year_bounds
from chronicle.services.access import designations_on
from chronicle.services.rule_sets import rule_set_for
from chronicle.services.schedules import ScheduleResolver

ALLOCATION, USAGE, REVERSAL, CARRY_OVER, EXPIRY, ADJUSTMENT = (
	"allocation",
	"usage",
	"reversal",
	"carry_over",
	"expiry",
	"adjustment",
)


def earned_leave_type(session: Session) -> LeaveType | None:
	return session.scalar(
		select(LeaveType)
		.where(LeaveType.category == "earned", LeaveType.deducts_from_balance)
		.order_by(LeaveType.id)
	)


def balance(session: Session, employee_id: int, leave_type_id: int, upto: str | None = None) -> Decimal:
	query = select(func.coalesce(func.sum(LeaveLedgerEntry.days), 0)).where(
		LeaveLedgerEntry.employee_id == employee_id, LeaveLedgerEntry.leave_type_id == leave_type_id
	)
	if upto:
		query = query.where(LeaveLedgerEntry.jdate <= upto)
	return Decimal(session.scalar(query)).quantize(Decimal("0.0001"))


def add_entry(
	session: Session,
	employee_id: int,
	leave_type_id: int,
	entry_type: str,
	jdate: str,
	days: Decimal | float,
	request_id: int | None = None,
	note: str | None = None,
	user_id: int | None = None,
) -> LeaveLedgerEntry:
	entry = LeaveLedgerEntry(
		employee_id=employee_id,
		leave_type_id=leave_type_id,
		entry_type=entry_type,
		jdate=jdate,
		days=Decimal(str(days)).quantize(Decimal("0.0001")),
		request_id=request_id,
		note=note,
		created_by_id=user_id,
	)
	session.add(entry)
	session.flush()
	return entry


def province_of(session: Session, employee: Employee) -> tuple[int | None, int | None]:
	if not employee.work_location_id:
		return None, None
	return employee.work_location_id, session.scalar(
		select(WorkLocation.province_id).where(WorkLocation.id == employee.work_location_id)
	)


def working_days(
	session: Session, employee_id: int, start: str, end: str, resolver: ScheduleResolver | None = None
) -> list[str]:
	"""Days of a daily leave that count: scheduled working days only. Official holidays,
	company holidays and weekly rest days inside a leave are not leave (Article 64)."""
	resolver = resolver or ScheduleResolver(session)
	employee = session.get(Employee, employee_id)
	work_location_id, province_id = province_of(session, employee)
	holidays = holidays_by_date(session, start, end)
	days = []
	for jdate in iter_days(start, end):
		if resolve_day(jdate, holidays.get(jdate, ()), work_location_id, province_id).day_type in (
			OFFICIAL_HOLIDAY,
			COMPANY_HOLIDAY,
		):
			continue
		schedule = resolver.resolve(employee_id, jdate)
		if schedule.shift and not schedule.rest_day:
			days.append(jdate)
	return days


def employed_days(employee: Employee, start: str, end: str) -> int:
	lo = max(start, employee.start_date)
	hi = min(end, employee.end_date) if employee.end_date else end
	return len(list(iter_days(lo, hi))) if lo <= hi else 0


def allocate_month(session: Session, year: int, month: int) -> int:
	"""Accrue earned leave for a finished Jalali month in proportion to the days employed
	(Articles 64, 65). Idempotent per employee and month."""
	leave_type = earned_leave_type(session)
	if leave_type is None:
		return 0
	start, end = month_bounds(year, month)
	y_start, y_end = year_bounds(year)
	year_days = len(list(iter_days(y_start, y_end)))
	_row, rules = rule_set_for(session, end)
	note = f"accrual {year}/{month:02d}"
	created = 0
	for emp in session.scalars(select(Employee).where(Employee.status != SUSPENDED)):
		exists = session.scalar(
			select(LeaveLedgerEntry.id).where(
				LeaveLedgerEntry.employee_id == emp.id,
				LeaveLedgerEntry.entry_type == ALLOCATION,
				LeaveLedgerEntry.note == note,
			)
		)
		days = employed_days(emp, start, end)
		if exists or not days:
			continue
		held = designations_on(session, emp.id, end)
		hard = bool(held) and bool(
			session.scalar(
				select(func.count())
				.select_from(Designation)
				.where(Designation.id.in_(held), Designation.hard_and_harmful)
			)
		)
		amount = annual_leave_entitlement(days, year_days, rules, hard_harmful=hard)
		add_entry(session, emp.id, leave_type.id, ALLOCATION, end, amount, note=note)
		created += 1
	return created


def close_leave_year(session: Session, year: int) -> int:
	"""Year end (Article 66): up to the carry-over limit stays, the rest expires."""
	leave_type = earned_leave_type(session)
	if leave_type is None:
		return 0
	_start, end = year_bounds(year)
	_row, rules = rule_set_for(session, end)
	note = f"year end {year}"
	expired_count = 0
	for employee_id in session.scalars(select(Employee.id)):
		if session.scalar(
			select(LeaveLedgerEntry.id).where(
				LeaveLedgerEntry.employee_id == employee_id,
				LeaveLedgerEntry.entry_type == EXPIRY,
				LeaveLedgerEntry.note == note,
			)
		):
			continue
		_carried, expired = year_end_carry_over(
			float(balance(session, employee_id, leave_type.id, upto=end)), rules
		)
		if expired > 0:
			add_entry(session, employee_id, leave_type.id, EXPIRY, end, -expired, note=note)
			expired_count += 1
	return expired_count
