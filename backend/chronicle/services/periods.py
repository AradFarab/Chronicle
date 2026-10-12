"""Monthly period locks (CLAUDE.md rule 9)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from chronicle.db.models import AttendancePeriod
from chronicle.db.models.attendance import CLOSED, OPEN
from chronicle.i18n import _
from chronicle.services import audit
from chronicle.services.errors import Conflict, ValidationError


def closed_months(session: Session, dates: Iterable[str]) -> set[tuple[int, int]]:
	months = {(int(d[:4]), int(d[5:7])) for d in dates}
	if not months:
		return set()
	rows = session.execute(
		select(AttendancePeriod.jyear, AttendancePeriod.jmonth).where(
			AttendancePeriod.status == CLOSED,
			tuple_(AttendancePeriod.jyear, AttendancePeriod.jmonth).in_(months),
		)
	)
	return {(y, m) for y, m in rows}


def is_closed(session: Session, jdate: str) -> bool:
	return bool(closed_months(session, [jdate]))


def assert_open(session: Session, dates: Iterable[str]) -> None:
	closed = closed_months(session, dates)
	if closed:
		labels = ", ".join(f"{y}/{m:02d}" for y, m in sorted(closed))
		raise Conflict(_("The period {0} is closed; reopen it first"), labels)


# closing and reopening (operators) ------------------------------------------------------------


def _period(session: Session, year: int, month: int) -> AttendancePeriod:
	row = session.scalar(
		select(AttendancePeriod).where(AttendancePeriod.jyear == year, AttendancePeriod.jmonth == month)
	)
	if row is None:
		row = AttendancePeriod(jyear=year, jmonth=month)
		session.add(row)
		session.flush()
	return row


def close(
	session: Session, year: int, month: int, today: str, user_id: int | None, note: str | None
) -> AttendancePeriod:
	"""Lock a finished month. Pending requests in it and queued recalculations must be
	finished first, so what is locked is final."""
	from chronicle.clock import now
	from chronicle.db.models import Job, Request
	from chronicle.db.models.requests import PENDING
	from chronicle.jalali.dates import month_bounds

	if not 1 <= month <= 12:
		raise ValidationError(_("Unknown month"))
	start, end = month_bounds(year, month)
	if end >= today:
		raise Conflict(_("The month {0} is not over yet"), f"{year}/{month:02d}")
	pending = session.scalar(
		select(func.count())
		.select_from(Request)
		.where(Request.status == PENDING, Request.start_jdate <= end, Request.end_jdate >= start)
	)
	if pending:
		raise Conflict(_("{0} requests in this month are still waiting for approval"), pending)
	if session.scalar(
		select(func.count())
		.select_from(Job)
		.where(Job.kind == "recalculate", Job.status.in_(("queued", "running")))
	):
		raise Conflict(_("Calculations are still running; try again in a minute"))
	row = _period(session, year, month)
	if row.status == CLOSED:
		return row
	row.status, row.closed_at, row.closed_by_id, row.note = CLOSED, now(), user_id, note
	audit.log(
		session, "attendance_period", row.label, "lock", user_id, note, {"status": OPEN}, {"status": CLOSED}
	)
	return row


def reopen(session: Session, year: int, month: int, user_id: int | None, reason: str) -> AttendancePeriod:
	if not (reason or "").strip():
		raise ValidationError(_("Enter the reason for reopening"))
	row = _period(session, year, month)
	if row.status == OPEN:
		return row
	row.status, row.closed_at, row.closed_by_id = OPEN, None, None
	audit.log(
		session,
		"attendance_period",
		row.label,
		"reopen",
		user_id,
		reason,
		{"status": CLOSED},
		{"status": OPEN},
	)
	return row


def list_periods(session: Session, year: int) -> list[dict]:
	rows = {
		p.jmonth: p for p in session.scalars(select(AttendancePeriod).where(AttendancePeriod.jyear == year))
	}
	return [
		{
			"jyear": year,
			"jmonth": m,
			"status": rows[m].status if m in rows else OPEN,
			"closed_at": rows[m].closed_at if m in rows else None,
			"note": rows[m].note if m in rows else None,
		}
		for m in range(1, 13)
	]
