"""Holidays in the database and the operator's yearly calendar refresh.

A refresh compares a source (time.ir, the bundled seed or a file) with the official holidays
already stored for that year, shows the differences, and applies the ones the operator keeps.
Rows the operator edited by hand and dates inside closed periods are never touched. Changed
days are queued for recalculation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chronicle.calendar.sources import BundledSource, FileSource, SourceHoliday, TimeIrSource, clean_title
from chronicle.db.models import CalendarYear, Holiday, Province
from chronicle.i18n import _
from chronicle.jalali import holidays as hol
from chronicle.jalali.calendar import DayInfo, resolve_day
from chronicle.jalali.dates import year_bounds
from chronicle.services import audit, jobs, settings
from chronicle.services.errors import Message, ValidationError
from chronicle.services.periods import closed_months

MANAGED_TYPES = (hol.OFFICIAL_SOLAR, hol.OFFICIAL_LUNAR, hol.OFFICIAL_OCCASIONAL)
SOURCED = ("bundled", "time_ir", "file")
ADD, REMOVE, CHANGE = "add", "remove", "change"


# reading -------------------------------------------------------------------------------


def as_rule(h: Holiday) -> dict:
	"""The fields chronicle.jalali.calendar needs."""
	return {
		"title": h.title,
		"holiday_type": h.holiday_type,
		"closure_pay_mode": h.closure_pay_mode,
		"scope": h.scope,
		"province_id": h.province_id,
		"work_location_id": h.work_location_id,
		"status": h.status,
	}


def holidays_by_date(session: Session, start: str, end: str) -> dict[str, list[dict]]:
	rows = session.scalars(
		select(Holiday).where(Holiday.jdate.between(start, end)).order_by(Holiday.jdate, Holiday.id)
	)
	out: dict[str, list[dict]] = defaultdict(list)
	for h in rows:
		out[h.jdate].append(as_rule(h))
	return out


def day_info(
	session: Session, jdate: str, work_location_id: int | None = None, province_id: int | None = None
) -> DayInfo:
	return resolve_day(
		jdate, holidays_by_date(session, jdate, jdate).get(jdate, ()), work_location_id, province_id
	)


# the bundled seed on install ------------------------------------------------------------


def _province_ids(session: Session) -> dict[str, int]:
	return {name: pid for name, pid in session.execute(select(Province.name, Province.id))}


def ensure_bundled_years(session: Session) -> list[int]:
	"""Load the bundled seed for every seed year that has no calendar yet (fresh install)."""
	first, last = hol.seed_years()
	have = set(session.scalars(select(CalendarYear.jyear)))
	provinces = _province_ids(session)
	loaded = []
	for year in range(first, last + 1):
		if year in have:
			continue
		rows = BundledSource().fetch(year)
		for r in rows:
			session.add(_new_holiday(r, "bundled", provinces))
		predicted = any(r.status == hol.PREDICTED for r in rows)
		session.add(
			CalendarYear(
				jyear=year,
				status=hol.PREDICTED if predicted else hol.CONFIRMED,
				source="bundled",
				holiday_count=len(rows),
			)
		)
		loaded.append(year)
	session.flush()
	return loaded


def _new_holiday(r: SourceHoliday, source: str, provinces: dict[str, int]) -> Holiday:
	province_id = provinces.get(r.province) if r.province else None
	scope = r.scope if (r.scope != hol.PROVINCE or province_id) else hol.COUNTRY
	return Holiday(
		jdate=r.jdate,
		title=r.title,
		holiday_type=r.holiday_type,
		status=r.status,
		scope=scope,
		province_id=province_id if scope == hol.PROVINCE else None,
		source=source,
		source_key=r.key[:100] or None,
		note=r.note or None,
	)


# refresh -------------------------------------------------------------------------------


@dataclass
class PlanItem:
	key: str
	action: str  # add / remove / change
	jdate: str
	title: str
	holiday_type: str
	status: str
	holiday_id: int | None = None  # existing row (remove, change)
	new_title: str | None = None
	new_type: str | None = None
	new_status: str | None = None
	locked: bool = False  # inside a closed period: shown, never applied


@dataclass
class RefreshPlan:
	year: int
	source: str
	items: list[PlanItem] = field(default_factory=list)
	unchanged: int = 0
	kept_edits: int = 0  # dates the operator edited by hand: left alone

	def as_dict(self) -> dict:
		return {
			"year": self.year,
			"source": self.source,
			"items": [asdict(i) for i in self.items],
			"unchanged": self.unchanged,
			"kept_edits": self.kept_edits,
		}


def make_source(session: Session, code: str, content: bytes | None = None, filename: str = ""):
	if code == "time_ir":
		return TimeIrSource(settings.get(session, "time_ir_url"), settings.get(session, "time_ir_api_key"))
	if code == "bundled":
		return BundledSource()
	if code == "file":
		if not content:
			raise ValidationError(_("Choose a holiday file"))
		return FileSource(content, filename)
	raise ValidationError(_("Unknown calendar source {0}"), code)


def _norm(title: str) -> str:
	return clean_title(title).replace("‌", " ")


def plan_refresh(session: Session, year: int, source) -> RefreshPlan:
	if not 1300 <= year <= 1499:
		raise ValidationError(_("Year out of range"))
	incoming = [r for r in source.fetch(year) if r.scope == hol.COUNTRY and r.holiday_type in MANAGED_TYPES]
	start, end = year_bounds(year)
	stored = list(
		session.scalars(
			select(Holiday).where(
				Holiday.jdate.between(start, end),
				Holiday.scope == hol.COUNTRY,
				Holiday.holiday_type.in_(MANAGED_TYPES),
			)
		)
	)
	plan = RefreshPlan(year=year, source=source.code)
	# Dates the operator owns: a hand-edited or manual row means "leave this date alone".
	owned = {h.jdate for h in stored if h.edited_by_admin or h.source not in SOURCED}
	plan.kept_edits = len(owned)
	current: dict[str, list[Holiday]] = defaultdict(list)
	for h in stored:
		if h.jdate not in owned:
			current[h.jdate].append(h)
	wanted: dict[str, list[SourceHoliday]] = defaultdict(list)
	for r in incoming:
		if r.jdate not in owned:
			wanted[r.jdate].append(r)
	locked = closed_months(session, set(current) | set(wanted))

	for jdate in sorted(set(current) | set(wanted)):
		is_locked = (int(jdate[:4]), int(jdate[5:7])) in locked
		cur, new = list(current.get(jdate, [])), list(wanted.get(jdate, []))
		# same title first, then pair what is left in order (a renamed holiday)
		pairs = []
		for h in list(cur):
			match = next((r for r in new if _norm(r.title) == _norm(h.title)), None)
			if match:
				pairs.append((h, match))
				cur.remove(h)
				new.remove(match)
		leftover = list(zip(cur, new, strict=False))
		pairs += leftover
		removed, added = cur[len(leftover) :], new[len(leftover) :]
		for h, r in pairs:
			if (_norm(h.title), h.holiday_type, h.status) == (_norm(r.title), r.holiday_type, r.status):
				plan.unchanged += 1
				continue
			plan.items.append(
				PlanItem(
					key=f"{CHANGE}:{h.id}",
					action=CHANGE,
					jdate=jdate,
					title=h.title,
					holiday_type=h.holiday_type,
					status=h.status,
					holiday_id=h.id,
					new_title=r.title,
					new_type=r.holiday_type,
					new_status=r.status,
					locked=is_locked,
				)
			)
		for h in removed:
			plan.items.append(
				PlanItem(
					key=f"{REMOVE}:{h.id}",
					action=REMOVE,
					jdate=jdate,
					title=h.title,
					holiday_type=h.holiday_type,
					status=h.status,
					holiday_id=h.id,
					locked=is_locked,
				)
			)
		for r in added:
			plan.items.append(
				PlanItem(
					key=f"{ADD}:{jdate}:{r.title}",
					action=ADD,
					jdate=jdate,
					title=r.title,
					holiday_type=r.holiday_type,
					status=r.status,
					locked=is_locked,
				)
			)
	plan.items.sort(key=lambda i: (i.jdate, i.action))
	return plan


def apply_refresh(
	session: Session,
	plan: RefreshPlan,
	user_id: int | None,
	skip_keys: set[str] | frozenset[str] = frozenset(),
) -> dict:
	"""Apply a plan (minus skipped and locked items), record the year's status and queue the
	changed days for recalculation."""
	applied: list[PlanItem] = []
	affected: set[str] = set()
	for item in plan.items:
		if item.locked or item.key in skip_keys:
			continue
		if item.action == ADD:
			session.add(
				Holiday(
					jdate=item.jdate,
					title=item.title,
					holiday_type=item.holiday_type,
					status=item.status,
					scope=hol.COUNTRY,
					source=plan.source,
					source_key=item.key[:100],
				)
			)
			affected.add(item.jdate)
		elif item.action == REMOVE:
			row = session.get(Holiday, item.holiday_id)
			if row is not None:
				session.delete(row)
				affected.add(item.jdate)
		else:
			row = session.get(Holiday, item.holiday_id)
			if row is not None:
				row.title, row.holiday_type, row.status = item.new_title, item.new_type, item.new_status
				row.source = plan.source
		applied.append(item)
	session.flush()
	start, end = year_bounds(plan.year)
	managed = session.execute(
		select(func.count(), func.bool_or(Holiday.status == hol.PREDICTED)).where(
			Holiday.jdate.between(start, end),
			Holiday.scope == hol.COUNTRY,
			Holiday.holiday_type.in_(MANAGED_TYPES),
		)
	).one()
	year_row = session.get(CalendarYear, plan.year) or CalendarYear(jyear=plan.year)
	year_row.source = plan.source
	year_row.status = hol.PREDICTED if managed[1] else hol.CONFIRMED
	year_row.holiday_count = managed[0]
	year_row.refreshed_at = datetime.now(UTC)
	year_row.refreshed_by_id = user_id
	session.add(year_row)
	summary = {
		"source": plan.source,
		"added": sum(i.action == ADD for i in applied),
		"removed": sum(i.action == REMOVE for i in applied),
		"changed": sum(i.action == CHANGE for i in applied),
		"skipped": sum(1 for i in plan.items if i.key in skip_keys or i.locked),
	}
	audit.log(
		session,
		"calendar_year",
		plan.year,
		"refresh",
		user_id=user_id,
		after={**summary, "items": [asdict(i) for i in applied]},
	)
	if affected:
		jobs.enqueue(
			session,
			jobs.RECALCULATE,
			{"dates": sorted(affected), "reason": f"calendar refresh {plan.year}"},
		)
	session.flush()
	return {**summary, "affected_dates": sorted(affected), "status": year_row.status}


def refresh_warning(session: Session, today: str) -> Message | None:
	"""From Esfand on, warn when next year's holidays are not confirmed yet; any time of year,
	warn when this year's still are predictions."""
	year, month = int(today[:4]), int(today[5:7])
	for target, active in ((year, True), (year + 1, month == 12)):
		if not active:
			continue
		row = session.get(CalendarYear, target)
		if row is None or row.status != hol.CONFIRMED:
			return Message(_("The holidays of {0} are not confirmed yet; refresh the calendar"), target)
	return None


# operator edits ----------------------------------------------------------------------------

EDITABLE = (
	"jdate",
	"title",
	"holiday_type",
	"status",
	"scope",
	"province_id",
	"work_location_id",
	"closure_pay_mode",
	"note",
)


def _validate(values: dict) -> dict:
	from chronicle.jalali.dates import InvalidJalaliDate, normalize_jdate

	try:
		values["jdate"] = normalize_jdate(values["jdate"])
	except (InvalidJalaliDate, KeyError):
		raise ValidationError(_("{0} is not a valid Jalali date"), values.get("jdate"))
	if not (values.get("title") or "").strip():
		raise ValidationError(_("Enter a title"))
	values["title"] = values["title"].strip()
	if values.get("holiday_type") not in hol.HOLIDAY_TYPES:
		raise ValidationError(_("Unknown holiday type"))
	scope = values.setdefault("scope", hol.COUNTRY)
	if scope == hol.PROVINCE and not values.get("province_id"):
		raise ValidationError(_("Choose the province"))
	if scope == hol.WORK_LOCATION and not values.get("work_location_id"):
		raise ValidationError(_("Choose the work location"))
	if scope != hol.PROVINCE:
		values["province_id"] = None
	if scope != hol.WORK_LOCATION:
		values["work_location_id"] = None
	if values["holiday_type"] == hol.OFFICE_CLOSURE:
		if values.get("closure_pay_mode") not in (
			hol.CLOSURE_PAID_HOLIDAY,
			hol.CLOSURE_EMPLOYER_PAID,
			hol.CLOSURE_WORKDAY,
		):
			raise ValidationError(_("Choose how the office closure is paid"))
	else:
		values["closure_pay_mode"] = None
	return values


def _recalculate(session: Session, dates: set[str], reason: str) -> None:
	jobs.enqueue(session, jobs.RECALCULATE, {"dates": sorted(dates), "reason": reason})


def create_holiday(session: Session, values: dict, user_id: int | None) -> Holiday:
	from chronicle.services.periods import assert_open

	values = _validate({k: values.get(k) for k in EDITABLE})
	assert_open(session, [values["jdate"]])
	holiday = Holiday(**values, source="manual")
	session.add(holiday)
	session.flush()
	audit.log(
		session, "holiday", holiday.id, "insert", user_id, values.get("note"), after=audit.snapshot(holiday)
	)
	_recalculate(session, {holiday.jdate}, "holiday added")
	return holiday


def update_holiday(
	session: Session, holiday_id: int, values: dict, reason: str, user_id: int | None
) -> Holiday:
	from chronicle.services.errors import NotFound
	from chronicle.services.periods import assert_open

	holiday = session.get(Holiday, holiday_id)
	if holiday is None:
		raise NotFound(_("Holiday not found"))
	if not (reason or "").strip():
		raise ValidationError(_("Enter the reason for the change"))
	before = audit.snapshot(holiday)
	merged = _validate({k: values.get(k, getattr(holiday, k)) for k in EDITABLE})
	assert_open(session, {holiday.jdate, merged["jdate"]})
	for k, v in merged.items():
		setattr(holiday, k, v)
	holiday.change_reason = reason
	if holiday.source != "manual":
		holiday.edited_by_admin = True  # a later refresh leaves this date alone
	session.flush()
	audit.log(session, "holiday", holiday.id, "update", user_id, reason, before, audit.snapshot(holiday))
	_recalculate(session, {before["jdate"], holiday.jdate}, "holiday changed")
	return holiday


def delete_holiday(session: Session, holiday_id: int, reason: str, user_id: int | None) -> None:
	from chronicle.services.errors import NotFound
	from chronicle.services.periods import assert_open

	holiday = session.get(Holiday, holiday_id)
	if holiday is None:
		raise NotFound(_("Holiday not found"))
	if not (reason or "").strip():
		raise ValidationError(_("Enter the reason for the change"))
	assert_open(session, [holiday.jdate])
	before = audit.snapshot(holiday)
	session.delete(holiday)
	session.flush()
	audit.log(session, "holiday", holiday_id, "delete", user_id, reason, before=before)
	_recalculate(session, {before["jdate"]}, "holiday deleted")
