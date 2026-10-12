"""The punches the calculation uses: device punches plus approved manual corrections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from chronicle.db.models import CorrectionItem, DeviceUserMap, RawPunch, Request
from chronicle.db.models.requests import ADD_PUNCH, APPROVED, CORRECTION, IGNORE_PUNCH

MANUAL = "manual"


@dataclass(frozen=True)
class EffectivePunch:
	jdate: str
	time: time
	direction: str
	source: str  # device / file_import / manual
	raw_punch_id: int | None = None
	request_id: int | None = None
	is_duplicate: bool = False


def employee_raw_punches(session: Session, employee_id: int, start: str, end: str) -> list[RawPunch]:
	"""Raw punches of an employee between two Jalali days (inclusive), through the device user
	map and its validity dates."""
	maps = session.scalars(select(DeviceUserMap).where(DeviceUserMap.employee_id == employee_id)).all()
	if not maps:
		return []
	conditions = []
	for m in maps:
		cond = [RawPunch.device_id == m.device_id, RawPunch.device_user_id == m.device_user_id]
		if m.valid_from:
			cond.append(RawPunch.jdate >= m.valid_from)
		if m.valid_to:
			cond.append(RawPunch.jdate <= m.valid_to)
		conditions.append(and_(*cond))
	return list(
		session.scalars(
			select(RawPunch)
			.where(RawPunch.jdate.between(start, end), or_(*conditions))
			.order_by(RawPunch.jdate, RawPunch.time, RawPunch.id)
		)
	)


def effective_punches(
	session: Session, employee_id: int, start: str, end: str | None = None
) -> list[EffectivePunch]:
	"""Raw punches that are not duplicates and not ignored by an approved correction, plus
	the times approved corrections add. Ordered by day and time."""
	end = end or start
	items = session.execute(
		select(CorrectionItem, Request.start_jdate, Request.id)
		.join(Request, Request.id == CorrectionItem.request_id)
		.where(
			Request.employee_id == employee_id,
			Request.kind == CORRECTION,
			Request.status == APPROVED,
			Request.start_jdate.between(start, end),
		)
	).all()
	ignored = {item.raw_punch_id for item, _d, _r in items if item.action == IGNORE_PUNCH}
	out = [
		EffectivePunch(p.jdate, p.time, p.direction, p.source, raw_punch_id=p.id)
		for p in employee_raw_punches(session, employee_id, start, end)
		if not p.is_duplicate and p.id not in ignored
	]
	out += [
		EffectivePunch(jdate, item.time, item.direction, MANUAL, request_id=request_id)
		for item, jdate, request_id in items
		if item.action == ADD_PUNCH
	]
	out.sort(key=lambda p: (p.jdate, p.time))
	return out
