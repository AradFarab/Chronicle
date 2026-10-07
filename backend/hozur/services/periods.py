"""Monthly period locks (CLAUDE.md rule 9)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from hozur.db.models import AttendancePeriod
from hozur.db.models.attendance import CLOSED
from hozur.i18n import _
from hozur.services.errors import Conflict


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
