"""Report builder: rows from daily_attendance, so every number matches the app.

Visibility applies (CLAUDE.md rule 8): a manager only gets the people below their designations. A
report can only ask for catalog fields (hozur.reports.catalog), never arbitrary columns.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from hozur.clock import now_jalali
from hozur.db.models import (
	AppUser,
	DailyAttendance,
	Department,
	Designation,
	Employee,
	LeaveType,
	Organization,
	ReportTemplate,
	Shift,
	WorkLocation,
)
from hozur.i18n import _, translate
from hozur.jalali.dates import WEEKDAY_NAMES, iter_days, month_bounds, normalize_jdate
from hozur.reports import catalog, exporters
from hozur.reports.catalog import COUNT, DAILY, DAYS, LEAVE_PREFIX, MINUTES, SUMMARY
from hozur.services import access, leave
from hozur.services.errors import NotFound, PermissionDenied, ValidationError
from hozur.services.rule_sets import rule_set_for

GROUPS = (None, "employee", "department", "day")
NUMERIC = (MINUTES, DAYS, COUNT)
EXTENSIONS = {"excel": "xlsx", "csv": "csv", "text": "txt", "pdf": "pdf"}
CONTENT_TYPES = {
	"excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"csv": "text/csv",
	"text": "text/plain",
	"pdf": "application/pdf",
}
FONT_DIR = Path(__file__).resolve().parent.parent / "reports" / "fonts"
DIRECT_COLUMNS = (
	"status",
	"day_type",
	"holiday_title",
	"required_minutes",
	"worked_minutes",
	"credited_minutes",
	"late_minutes",
	"early_leave_minutes",
	"absence_minutes",
	"overtime_normal_minutes",
	"overtime_exceptional_minutes",
	"overtime_emergency_minutes",
	"unapproved_extra_minutes",
	"night_work_minutes",
	"rest_day_work_minutes",
	"friday_premium_minutes",
	"holiday_work_minutes",
	"company_holiday_work_minutes",
	"leave_minutes",
	"mission_minutes",
	"nursing_minutes",
)


def leave_type_names(session: Session) -> set[str]:
	return set(session.scalars(select(LeaveType.name)))


def unknown_columns(session: Session, columns: Iterable[dict], source: str = SUMMARY) -> list[str]:
	types = leave_type_names(session)
	bad = []
	for col in columns:
		try:
			catalog.resolve(col.get("field", ""), source, types)
		except ValueError:
			bad.append(str(col.get("field")))
	return bad


def fields(session: Session, source: str, language: str) -> list[dict]:
	"""The fields the builder may use, grouped and translated."""
	out = [
		{
			"key": f.key,
			"label": translate(f.label, language),
			"group": translate(f.group, language),
			"kind": f.kind,
		}
		for f in catalog.FIELDS
		if source in f.sources
	]
	out += [
		{
			"key": LEAVE_PREFIX + t,
			"label": t,
			"group": translate("Leave by Type", language),
			"kind": catalog.DAYS,
		}
		for t in sorted(leave_type_names(session))
	]
	return out


def validate_spec(session: Session, spec: dict, language: str) -> dict:
	source = spec.get("source") or SUMMARY
	if source not in (DAILY, SUMMARY):
		raise ValidationError(_("Unknown report source"))
	if (spec.get("group_by") or None) not in GROUPS:
		raise ValidationError(_("Unknown grouping"))
	types = leave_type_names(session)
	columns = []
	for col in spec.get("columns") or []:
		try:
			f = catalog.resolve(col.get("field", ""), source, types)
		except ValueError as e:
			raise ValidationError(_("Report field not allowed: {0}"), str(e)) from None
		columns.append(
			{
				"key": f.key,
				"label": col.get("label") or translate(f.label, language),
				"kind": f.kind,
				"width": col.get("width"),
			}
		)
	if not columns:
		raise ValidationError(_("Choose at least one column"))
	return {**spec, "source": source, "group_by": spec.get("group_by") or None, "columns": columns}


def default_range(default: str | None, today: str) -> tuple[str, str]:
	year, month = int(today[:4]), int(today[5:7])
	if default == "today":
		return today, today
	if default == "previous_month":
		year, month = (year, month - 1) if month > 1 else (year - 1, 12)
	return month_bounds(year, month)


def _names(session: Session, model, ids: set[int]) -> dict[int, str]:
	if not ids:
		return {}
	return dict(session.execute(select(model.id, model.name).where(model.id.in_(ids))).all())


def _day_rows(session: Session, filters: dict, visible: set[int] | None) -> list[dict]:
	query = select(DailyAttendance).where(
		DailyAttendance.jdate.between(filters["from_date"], filters["to_date"])
	)
	if filters.get("employee_id"):
		query = query.where(DailyAttendance.employee_id == int(filters["employee_id"]))
	if filters.get("work_location_id"):
		query = query.where(DailyAttendance.work_location_id == int(filters["work_location_id"]))
	if filters.get("designation_id"):
		query = query.where(DailyAttendance.designation_id == int(filters["designation_id"]))
	if filters.get("department_id"):
		query = query.where(DailyAttendance.department_id == int(filters["department_id"]))
	if visible is not None:
		query = query.where(DailyAttendance.employee_id.in_(visible or {0}))
	rows = list(session.scalars(query.order_by(DailyAttendance.employee_id, DailyAttendance.jdate)))
	employees = {
		e.id: e
		for e in session.scalars(
			select(Employee).where(Employee.id.in_({r.employee_id for r in rows} or {0}))
		)
	}
	departments = _names(session, Department, {r.department_id for r in rows if r.department_id})
	locations = _names(session, WorkLocation, {r.work_location_id for r in rows if r.work_location_id})
	designations = _names(session, Designation, {r.designation_id for r in rows if r.designation_id})
	shifts = _names(session, Shift, {r.shift_id for r in rows if r.shift_id})
	types = {t.id: t for t in session.scalars(select(LeaveType))}
	out = []
	for r in rows:
		emp = employees[r.employee_id]
		row = {c: getattr(r, c) for c in DIRECT_COLUMNS}
		row.update(
			employee_id=r.employee_id,
			employee=emp.code,
			employee_name=emp.full_name,
			national_id=emp.national_id,
			work_location=locations.get(r.work_location_id),
			department=departments.get(r.department_id),
			designation=designations.get(r.designation_id),
			jdate=r.jdate,
			weekday_name=WEEKDAY_NAMES[r.weekday],
			shift=shifts.get(r.shift_id),
			first_in=r.first_in.strftime("%H:%M") if r.first_in else None,
			last_out=r.last_out.strftime("%H:%M") if r.last_out else None,
			warnings=", ".join(r.warnings) or None,
			absent_days=int(r.absent_day),
			mission_days=int(r.status == "mission"),
			leave_days=float(r.leave_days),
			overtime_total_minutes=r.overtime_normal_minutes
			+ r.overtime_exceptional_minutes
			+ r.overtime_emergency_minutes,
		)
		unpaid = 0.0
		for lv in r.leaves:
			t = types[lv.leave_type_id]
			row[LEAVE_PREFIX + t.name] = float(lv.days)
			unpaid += 0 if t.is_paid else float(lv.days)
		row["_unpaid_leave_days"] = unpaid
		out.append(row)
	return out


def _sum_rows(
	rows: list[dict], columns: list[dict], key_of: Callable, first_fields: tuple[str, ...]
) -> list[dict]:
	groups: OrderedDict = OrderedDict()
	for r in rows:
		groups.setdefault(key_of(r), []).append(r)
	out = []
	for members in groups.values():
		row = {f: members[0].get(f) for f in first_fields}
		for c in columns:
			if c["kind"] in NUMERIC:
				row[c["key"]] = sum(m.get(c["key"]) or 0 for m in members)
		row["_members"] = members
		out.append(row)
	return out


def _summary_extras(session: Session, row: dict, start: str, end: str, earned_id: int | None) -> None:
	members = row["_members"]
	emp = session.get(Employee, row["employee_id"])
	lo = max(start, emp.start_date)
	hi = min(end, emp.end_date) if emp.end_date else end
	employed = len(list(iter_days(lo, hi))) if lo <= hi else 0
	row["employed_days"] = employed
	row["present_days"] = sum(1 for m in members if m["status"] in ("present", "incomplete"))
	row["holiday_days"] = sum(1 for m in members if m["status"] == "holiday")
	row["rest_days"] = sum(1 for m in members if m["status"] == "rest_day")
	absent = sum(m["absent_days"] for m in members)
	unpaid = sum(m["_unpaid_leave_days"] for m in members)
	# Paid days: employed days minus unexcused absence and leave the employer does not pay.
	row["paid_days"] = round(max(0, employed - absent - unpaid), 4)
	row["leave_balance"] = float(leave.balance(session, emp.id, earned_id, upto=end)) if earned_id else 0


def build(session: Session, actor: access.Actor, today: str, spec: dict, filters: dict) -> dict:
	"""-> {"columns", "rows", "from_date", "to_date"} with raw values (minutes as ints)."""
	spec = validate_spec(session, spec, actor.language)
	columns = spec["columns"]
	filters = dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		filters["from_date"], filters["to_date"] = default_range(spec.get("default_range"), today)
	start, end = normalize_jdate(filters["from_date"]), normalize_jdate(filters["to_date"])
	if end < start:
		raise ValidationError(_("The end date is before the start date"))
	filters.update(from_date=start, to_date=end)
	visible = access.visible_employee_ids(session, actor, today)
	if filters.get("employee_id") and visible is not None and int(filters["employee_id"]) not in visible:
		raise PermissionDenied(_("Not permitted"))
	rows = _day_rows(session, filters, visible)
	identity = (
		"employee_id",
		"employee",
		"employee_name",
		"national_id",
		"work_location",
		"department",
		"designation",
	)
	group = spec["group_by"]
	if spec["source"] == SUMMARY:
		earned = leave.earned_leave_type(session)
		rows = _sum_rows(rows, columns, lambda r: r["employee_id"], identity)
		for r in rows:
			_summary_extras(session, r, start, end, earned.id if earned else None)
	elif group == "employee":
		rows = _sum_rows(rows, columns, lambda r: r["employee_id"], identity)
	elif group == "department":
		rows = _sum_rows(rows, columns, lambda r: r["department"], ("department", "work_location"))
	elif group == "day":
		rows = _sum_rows(
			rows, columns, lambda r: r["jdate"], ("jdate", "weekday_name", "day_type", "holiday_title")
		)
	return {
		"columns": columns,
		"rows": [{c["key"]: r.get(c["key"]) for c in columns} for r in rows],
		"from_date": start,
		"to_date": end,
	}


# templates ---------------------------------------------------------------------------------------


def visible_templates(session: Session, actor: access.Actor) -> list[ReportTemplate]:
	rows = session.scalars(select(ReportTemplate).order_by(ReportTemplate.name))
	return [t for t in rows if _may_use(actor, t)]


def _may_use(actor: access.Actor, t: ReportTemplate) -> bool:
	return actor.is_admin or actor.sees_all or t.is_standard or bool(set(t.shared_roles or ()) & actor.roles)


def template_spec(session: Session, actor: access.Actor, template_id: int) -> dict:
	t = session.get(ReportTemplate, template_id)
	if t is None:
		raise NotFound(_("Not found"))
	if not _may_use(actor, t):
		raise PermissionDenied(_("Not permitted"))
	return {
		"title": t.name,
		"source": t.source,
		"group_by": t.group_by,
		"time_unit": t.time_unit,
		"default_range": t.default_range,
		"export_format": t.export_format,
		"text_delimiter": t.text_delimiter,
		"text_encoding": t.text_encoding,
		"columns": t.columns,
	}


def spec_for(session: Session, actor: access.Actor, template_id: int | None, spec: dict | None) -> dict:
	"""A saved template (anyone it is shared with) or an ad-hoc spec (operators)."""
	if template_id:
		return template_spec(session, actor, template_id)
	if not actor.is_admin:
		raise PermissionDenied(_("Not permitted"))
	return dict(spec or {})


# export ------------------------------------------------------------------------------------------


def render(
	session: Session,
	actor: access.Actor,
	today: str,
	spec: dict,
	filters: dict,
	export_format: str | None = None,
) -> tuple[str, str, bytes]:
	"""-> (filename, content type, bytes)."""
	result = build(session, actor, today, spec, filters)
	export_format = export_format or spec.get("export_format") or "excel"
	if export_format not in EXTENSIONS:
		raise ValidationError(_("Unknown export format"))
	unit = spec.get("time_unit") or exporters.HOURS_MINUTES
	day_minutes = rule_set_for(session, result["to_date"])[1].hourly_leave_minutes_per_day
	title = spec.get("title") or translate("Report", actor.language)
	org = session.scalar(select(Organization.name).where(Organization.id == 1)) or ""
	user = session.get(AppUser, actor.user_id) if actor.user_id else None
	jdate, clock = now_jalali()
	meta = [
		" · ".join(x for x in (org, f"{result['from_date']} – {result['to_date']}") if x),
		translate("Prepared by {0} on {1} at {2}", actor.language).format(
			user.full_name if user else "", jdate, clock[:5]
		),
	]
	columns, rows = result["columns"], result["rows"]
	if export_format == "excel":
		content = exporters.to_xlsx(title, meta, columns, rows, unit, day_minutes)
	elif export_format in ("csv", "text"):
		content = exporters.to_text(
			columns,
			rows,
			unit,
			day_minutes,
			spec.get("text_delimiter") or "comma",
			spec.get("text_encoding") or "utf-8",
		)
	else:
		content = exporters.to_pdf(title, meta, columns, rows, unit, day_minutes, FONT_DIR.as_uri())
	filename = f"{title} {result['from_date']} {result['to_date']}.{EXTENSIONS[export_format]}".replace(
		"/", "-"
	)
	return filename, CONTENT_TYPES[export_format], content
