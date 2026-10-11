"""Configuration records edited in the PWA (org, schedules, rules, approval processes, ...).

One declarative `Resource` per table says which columns may be written, who may read and
write, how to validate, and which recalculation a change needs. The generic code below does
type coercion from JSON (Jalali dates, times, numbers), audit entries (CLAUDE.md rule 4)
and turns database constraint errors into messages for the system admin. Tables with their own
workflow (requests, holidays, devices, users, periods) have their own services.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, String, Text, Time, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hozur.db.models import (
	ApprovalDefault,
	ApprovalOverride,
	ApprovalProcess,
	ApprovalProcessStep,
	Department,
	Designation,
	DesignationAssignment,
	Employee,
	LaborRuleSet,
	LeaveType,
	Province,
	ReportTemplate,
	Shift,
	ShiftOverride,
	ShiftSegment,
	WorkLocation,
	WorkPattern,
	WorkPatternAssignment,
	WorkPatternDay,
)
from hozur.db.models.schedules import BREAK, FLEXIBLE, OVERTIME_WINDOW, ROTATING, TARGET_EMPLOYEE, TWO_DAYS
from hozur.db.types import JDate
from hozur.i18n import _
from hozur.jalali.dates import InvalidJalaliDate, add_days, normalize_jdate, normalize_time
from hozur.services import access, audit, jobs
from hozur.services.errors import Conflict, NotFound, PermissionDenied, ValidationError
from hozur.services.rule_sets import check_parameters
from hozur.services.schedules import employees_following

ADMIN, EVERYONE, NOBODY = "admin", "everyone", "nobody"  # NOBODY: written through its own service
RECALC_LOOKBACK_DAYS = 366  # a configuration change never recalculates further back than this


@dataclass
class Context:
	session: Session
	actor: access.Actor
	today: str
	reason: str | None = None


Hook = Callable[[Context, Any, dict[str, Any] | None], None]


@dataclass
class Resource:
	name: str  # URL segment
	model: type
	fields: tuple[str, ...]  # writable columns
	read: str = ADMIN
	write: str = ADMIN
	order_by: tuple[str, ...] = ("id",)
	children: dict[str, tuple[type, tuple[str, ...]]] = field(default_factory=dict)  # name -> (model, fields)
	validate: Hook | None = None  # (ctx, obj, before) after values are set, before flush
	changed: Hook | None = None  # (ctx, obj, before) after flush: recalculation, follow-ups
	deletable: Callable[[Any], bool] = lambda obj: not getattr(obj, "is_standard", False)
	reason_required: bool = False


# coercion ----------------------------------------------------------------------------------


def _column_types(model: type) -> dict[str, Any]:
	return {c.key: c.columns[0] for c in inspect(model).column_attrs}


def coerce(model: type, key: str, value: Any) -> Any:
	"""A JSON value -> the column's Python type; a ValidationError names the field."""
	column = _column_types(model)[key]
	kind = column.type
	if value is None or (
		isinstance(value, str) and not value.strip() and not isinstance(kind, String | Text)
	):
		return None
	try:
		if isinstance(kind, JDate):
			return normalize_jdate(str(value))
		if isinstance(kind, Time):
			clock = normalize_time(str(value))
			if clock is None:
				raise ValueError(value)
			return time.fromisoformat(clock)
		if isinstance(kind, Boolean):
			if isinstance(value, str):
				return value.strip().lower() in ("1", "true", "yes", "on")
			return bool(value)
		if isinstance(kind, Integer):
			if isinstance(value, bool):
				raise ValueError(value)
			return int(value)
		if isinstance(kind, Numeric):
			return Decimal(str(value))
		if isinstance(kind, String | Text):
			text = str(value).strip()
			return text or (None if column.nullable else text)
	except (ValueError, TypeError, InvalidOperation, InvalidJalaliDate):
		raise ValidationError(_("{0}: the value {1} is not valid"), key, value) from None
	return value


def _apply(model: type, obj: Any, values: dict[str, Any], allowed: tuple[str, ...]) -> None:
	for key in allowed:
		if key in values:
			setattr(obj, key, coerce(model, key, values[key]))


# permission ---------------------------------------------------------------------------------


def _allowed(actor: access.Actor, level: str) -> bool:
	return level == EVERYONE or (level == ADMIN and actor.is_admin)


def check(actor: access.Actor, level: str) -> None:
	if not _allowed(actor, level):
		raise PermissionDenied(_("Not permitted"))


# integrity errors -> messages -----------------------------------------------------------------


def flush(session: Session, deleting: bool = False) -> None:
	"""Flush inside a savepoint; constraint violations become messages for the system admin."""
	try:
		with session.begin_nested():
			session.flush()
	except IntegrityError as e:
		state = getattr(e.orig, "sqlstate", None)
		diag = getattr(e.orig, "diag", None)
		if state == "23505":
			raise Conflict(_("Another record already has this value")) from None
		if state == "23503":
			if deleting:
				raise Conflict(_("This record is used elsewhere and cannot be removed")) from None
			raise ValidationError(_("A linked record does not exist")) from None
		if state == "23502":
			raise ValidationError(_("{0} is required"), getattr(diag, "column_name", "")) from None
		if state == "23514":
			raise ValidationError(
				_("A value is not valid ({0})"), getattr(diag, "constraint_name", "")
			) from None
		raise


# generic operations ------------------------------------------------------------------------------


def view(resource: Resource, obj: Any) -> dict[str, Any]:
	out = audit.snapshot(obj)
	for key, value in list(out.items()):
		if isinstance(value, str) and key.endswith("_time") and len(value) == 8:
			out[key] = value[:5]  # 'HH:MM:SS' -> 'HH:MM'
	for name, (_child, fields) in resource.children.items():
		out[name] = [{k: _plain_child(getattr(c, k)) for k in ("id", *fields)} for c in getattr(obj, name)]
	return out


def _plain_child(value: Any) -> Any:
	return value.strftime("%H:%M") if isinstance(value, time) else value


def _snapshot(resource: Resource, obj: Any) -> dict[str, Any]:
	return view(resource, obj)


def list_rows(ctx: Context, resource: Resource) -> list[Any]:
	check(ctx.actor, resource.read)
	order = [getattr(resource.model, k) for k in resource.order_by]
	return list(ctx.session.scalars(select(resource.model).order_by(*order)))


def get_row(ctx: Context, resource: Resource, row_id: int) -> Any:
	check(ctx.actor, resource.read)
	obj = ctx.session.get(resource.model, row_id)
	if obj is None:
		raise NotFound(_("Not found"))
	return obj


def _set_children(ctx: Context, resource: Resource, obj: Any, values: dict[str, Any]) -> None:
	for name, (child, fields) in resource.children.items():
		if name not in values:
			continue
		rows = []
		for item in values[name] or []:
			c = child()
			_apply(child, c, item, fields)
			rows.append(c)
		if getattr(obj, name):
			getattr(obj, name).clear()
			flush(ctx.session)  # delete the old rows before inserting rows with the same keys
		getattr(obj, name).extend(rows)


def save(ctx: Context, resource: Resource, values: dict[str, Any], row_id: int | None = None) -> Any:
	check(ctx.actor, resource.write)
	reason = (values.get("reason") or ctx.reason or "").strip() or None
	if row_id is not None and resource.reason_required and not reason:
		raise ValidationError(_("Enter the reason for the change"))
	ctx.reason = reason
	obj = get_row(ctx, resource, row_id) if row_id is not None else resource.model()
	before = _snapshot(resource, obj) if row_id is not None else None
	_apply(resource.model, obj, values, resource.fields)
	if row_id is None:
		ctx.session.add(obj)
	_set_children(ctx, resource, obj, values)
	if resource.validate:
		resource.validate(ctx, obj, before)
	flush(ctx.session)
	after = _snapshot(resource, obj)
	if before == after:
		return obj
	audit.log(
		ctx.session,
		resource.model.__tablename__,
		obj.id,
		"update" if before else "insert",
		ctx.actor.user_id,
		reason,
		before,
		after,
	)
	if resource.changed:
		resource.changed(ctx, obj, before)
	return obj


def delete(ctx: Context, resource: Resource, row_id: int, reason: str | None = None) -> None:
	check(ctx.actor, resource.write)
	obj = get_row(ctx, resource, row_id)
	if not resource.deletable(obj):
		raise Conflict(_("A standard record cannot be removed"))
	before = _snapshot(resource, obj)
	ctx.session.delete(obj)
	flush(ctx.session, deleting=True)
	audit.log(
		ctx.session, resource.model.__tablename__, row_id, "delete", ctx.actor.user_id, reason, before=before
	)
	ctx.reason = reason
	if resource.changed:
		resource.changed(ctx, obj, before)


# recalculation after configuration changes -----------------------------------------------------


def recalculate(ctx: Context, start: str | None, employee_ids: set[int] | None, why: str) -> None:
	"""Queue a recalculation from `start` (bounded to a year back) to today."""
	floor = add_days(ctx.today, -RECALC_LOOKBACK_DAYS)
	start = max(start or ctx.today[:8] + "01", floor)
	if start > ctx.today or employee_ids == set():
		return
	payload: dict[str, Any] = {"range": [start, ctx.today], "reason": why}
	if employee_ids is not None:
		payload["employee_ids"] = sorted(employee_ids)
	jobs.enqueue(ctx.session, jobs.RECALCULATE, payload)


def _month_start(ctx: Context) -> str:
	return ctx.today[:8] + "01"


# validation and side effects per table ------------------------------------------------------------


def _employee(ctx: Context, e: Employee, before) -> None:
	if e.end_date and e.start_date and e.end_date < e.start_date:
		raise ValidationError(_("The end date is before the start date"))
	if e.national_id and (len(e.national_id) != 10 or not e.national_id.isdigit()):
		raise ValidationError(_("The national id must be 10 digits"))


EMPLOYMENT_FIELDS = ("start_date", "end_date", "status")
CALCULATION_FIELDS = (
	"work_location_id",
	"department_id",
	"birth_date",
	"nursing_until",
	"overtime_consent_on_file",
	"overtime_consent_date",
)


def _employee_changed(ctx: Context, e: Employee, before) -> None:
	if before is None:
		recalculate(ctx, e.start_date, {e.id}, "new employee")
		return
	if any(before.get(k) != getattr(e, k) for k in EMPLOYMENT_FIELDS):
		dates = [before.get("start_date"), e.start_date, before.get("end_date"), e.end_date]
		recalculate(ctx, min(d for d in dates if d), {e.id}, "employment changed")
	elif any(before.get(k) != getattr(e, k) for k in CALCULATION_FIELDS):
		recalculate(ctx, _month_start(ctx), {e.id}, "employee changed")


def _shift(ctx: Context, s: Shift, before) -> None:
	if s.shift_type == FLEXIBLE and not s.required_minutes:
		raise ValidationError(_("A flexible shift needs the required minutes"))
	if s.start_time is None or s.end_time is None:
		raise ValidationError(_("Enter the start and end time"))
	start, end = _minutes(s.start_time), _minutes(s.end_time)
	end += 1440 if end <= start else 0
	kinds = {BREAK: [], OVERTIME_WINDOW: []}
	for g in s.segments:
		if g.kind not in kinds or g.start_minute is None or g.end_minute is None:
			raise ValidationError(_("Each part of the shift needs a kind, a start and an end"))
		if not 0 <= g.start_minute < g.end_minute <= TWO_DAYS:
			raise ValidationError(_("A part of the shift must end after it starts"))
		kinds[g.kind].append((g.start_minute, g.end_minute))
	for kind, label in ((BREAK, _("Breaks")), (OVERTIME_WINDOW, _("Overtime windows"))):
		ordered = sorted(kinds[kind])
		if any(b_start < a_end for (_a, a_end), (b_start, _b) in pairwise(ordered)):
			raise ValidationError(_("{0} overlap each other"), label)
	if any(not (start <= a and b <= end) for a, b in kinds[BREAK]):
		raise ValidationError(_("The break must be inside the shift"))
	if s.shift_type != FLEXIBLE and any(a < end and b > start for a, b in kinds[OVERTIME_WINDOW]):
		raise ValidationError(_("An overtime window must be before the start or after the end of the shift"))


def _minutes(t: time) -> int:
	return t.hour * 60 + t.minute


def _schedule_changed(ctx: Context, obj, before) -> None:
	recalculate(ctx, _month_start(ctx), None, f"{obj.__tablename__} changed")


def _pattern(ctx: Context, p: WorkPattern, before) -> None:
	if p.pattern_type == ROTATING:
		if not p.cycle_start_date:
			raise ValidationError(_("A rotating pattern needs the first day of the cycle"))
		cycle = sorted(d.cycle_day for d in p.days)
		if not cycle or cycle != list(range(1, len(cycle) + 1)) or any(d.weekday is not None for d in p.days):
			raise ValidationError(_("Number the days of the cycle 1, 2, 3, ..."))
	else:
		weekdays = [d.weekday for d in p.days]
		if None in weekdays or len(set(weekdays)) != len(weekdays) or any(not 0 <= w <= 6 for w in weekdays):
			raise ValidationError(_("Each weekday can appear once"))
		for d in p.days:
			d.cycle_day = None


def _pattern_changed(ctx: Context, p: WorkPattern, before) -> None:
	if p.id is None or inspect(p).deleted:
		return
	recalculate(ctx, _month_start(ctx), employees_following(ctx.session, p.id), "work pattern changed")


def _assignment_changed(ctx: Context, a: WorkPatternAssignment, before) -> None:
	start = min(filter(None, (a.valid_from, (before or {}).get("valid_from"))))
	people = None
	if a.target_type == TARGET_EMPLOYEE and (before is None or before.get("target_type") == TARGET_EMPLOYEE):
		people = {a.employee_id, (before or {}).get("employee_id")} - {None}
	recalculate(ctx, start, people, "work pattern assignment changed")


def _override_changed(ctx: Context, o: ShiftOverride, before) -> None:
	dates = {o.jdate, (before or {}).get("jdate")} - {None}
	people = {o.employee_id, (before or {}).get("employee_id")} - {None}
	for jdate in dates:
		if jdate <= ctx.today:
			jobs.enqueue(
				ctx.session,
				jobs.RECALCULATE,
				{"dates": [jdate], "employee_ids": sorted(people), "reason": "shift override"},
			)


def _rule_set(ctx: Context, r: LaborRuleSet, before) -> None:
	if r.is_legal_baseline or (before and before.get("is_legal_baseline")):
		raise ValidationError(_("The legal baseline is part of the app and cannot be changed"))
	r.parameters = check_parameters(dict(r.parameters or {}))


def _rule_set_changed(ctx: Context, r: LaborRuleSet, before) -> None:
	start = min(filter(None, (r.effective_from, (before or {}).get("effective_from"))))
	recalculate(ctx, start, None, "labor rule set changed")


def _designation(ctx: Context, d: Designation, before) -> None:
	if d.is_ceo and d.parent_id:
		raise ValidationError(_("The CEO designation must be at the top of the chart"))
	if d.id and d.parent_id:
		with ctx.session.no_autoflush:  # the edited row is not valid until these checks pass
			below = access.descendants(ctx.session, {d.id})
		if d.parent_id in below:
			raise ValidationError(_("A designation cannot be below itself"))


def _holders_of(ctx: Context, designation_id: int) -> set[int]:
	return set(
		ctx.session.scalars(
			select(DesignationAssignment.employee_id).where(
				DesignationAssignment.designation_id == designation_id
			)
		)
	)


def _designation_changed(ctx: Context, d: Designation, before) -> None:
	if before and before.get("hard_and_harmful") != d.hard_and_harmful and not inspect(d).deleted:
		recalculate(ctx, _month_start(ctx), _holders_of(ctx, d.id), "designation changed")


def _designation_assignment(ctx: Context, a: DesignationAssignment, before) -> None:
	if a.valid_to and a.valid_from and a.valid_to < a.valid_from:
		raise ValidationError(_("The end date is before the start date"))


def _designation_assignment_changed(ctx: Context, a: DesignationAssignment, before) -> None:
	starts = [d for d in (a.valid_from, (before or {}).get("valid_from")) if d]
	recalculate(ctx, min(starts), {a.employee_id}, "designation given or taken")


def _work_location_changed(ctx: Context, b: WorkLocation, before) -> None:
	if before and before.get("province_id") != b.province_id and not inspect(b).deleted:
		ids = set(ctx.session.scalars(select(Employee.id).where(Employee.work_location_id == b.id)))
		recalculate(ctx, _month_start(ctx), ids, "work location province changed")


def _leave_type_changed(ctx: Context, t: LeaveType, before) -> None:
	if before and before.get("is_paid") != t.is_paid:
		recalculate(ctx, _month_start(ctx), None, "leave type changed")


def _process(ctx: Context, p: ApprovalProcess, before) -> None:
	positions = sorted(s.position for s in p.steps)
	if positions != list(range(1, len(positions) + 1)):
		raise ValidationError(_("Number the steps 1, 2, 3, ..."))


def _report_template(ctx: Context, t: ReportTemplate, before) -> None:
	from hozur.services.reports import unknown_columns

	unknown = unknown_columns(ctx.session, t.columns or [], t.source or "summary")
	if unknown:
		raise ValidationError(_("Unknown report columns: {0}"), ", ".join(unknown))


RESOURCES: dict[str, Resource] = {
	r.name: r
	for r in (
		Resource("provinces", Province, (), read=EVERYONE, write=ADMIN, order_by=("name",)),
		Resource(
			"work-locations",
			WorkLocation,
			("name", "province_id", "city", "address", "is_active"),
			read=EVERYONE,
			order_by=("name",),
			changed=_work_location_changed,
		),
		Resource("departments", Department, ("name",), read=EVERYONE, order_by=("name",)),
		Resource(
			"designations",
			Designation,
			(
				"name",
				"parent_id",
				"is_ceo",
				"description",
				"hard_and_harmful",
				"committee_ruling_no",
				"committee_ruling_date",
			),
			read=EVERYONE,
			order_by=("name",),
			validate=_designation,
			changed=_designation_changed,
		),
		Resource(
			"designation-assignments",
			DesignationAssignment,
			("employee_id", "designation_id", "valid_from", "valid_to", "note"),
			order_by=("valid_from", "id"),
			validate=_designation_assignment,
			changed=_designation_assignment_changed,
			deletable=lambda a: True,
		),
		# Employees are users too, so they are written by services/employees.py (password,
		# username); the generic layer only reads them.
		Resource(
			"employees",
			Employee,
			(),
			read=EVERYONE,  # narrowed to what the actor may see in the route
			write=NOBODY,
			order_by=("code",),
			deletable=lambda e: False,  # people leave (status / end date); their history stays
		),
		Resource(
			"shifts",
			Shift,
			(
				"name",
				"shift_type",
				"color",
				"start_time",
				"end_time",
				"latest_start_time",
				"required_minutes",
				"break_minutes",
				"grace_late_minutes",
				"grace_early_minutes",
				"overtime_after_minutes",
			),
			read=EVERYONE,
			order_by=("name",),
			children={"segments": (ShiftSegment, ("kind", "start_minute", "end_minute"))},
			validate=_shift,
			changed=_schedule_changed,
		),
		Resource(
			"work-patterns",
			WorkPattern,
			("name", "pattern_type", "weekly_rest_day", "cycle_start_date", "description", "change_reason"),
			order_by=("name",),
			children={"days": (WorkPatternDay, ("weekday", "cycle_day", "shift_id"))},
			validate=_pattern,
			changed=_pattern_changed,
		),
		Resource(
			"work-pattern-assignments",
			WorkPatternAssignment,
			(
				"target_type",
				"employee_id",
				"designation_id",
				"department_id",
				"work_pattern_id",
				"cycle_offset_days",
				"valid_from",
				"valid_to",
				"note",
			),
			order_by=("valid_from", "id"),
			changed=_assignment_changed,
		),
		Resource(
			"shift-overrides",
			ShiftOverride,
			("employee_id", "jdate", "shift_id", "reason"),
			order_by=("jdate", "id"),
			changed=_override_changed,
		),
		Resource(
			"rule-sets",
			LaborRuleSet,
			("name", "effective_from", "description", "parameters", "change_reason"),
			write=ADMIN,
			order_by=("effective_from",),
			validate=_rule_set,
			changed=_rule_set_changed,
			deletable=lambda r: not r.is_legal_baseline,
			reason_required=True,
		),
		Resource(
			"leave-types",
			LeaveType,
			(
				"name",
				"category",
				"is_paid",
				"deducts_from_balance",
				"allow_hourly",
				"rule_limit",
				"max_days_per_request",
				"once_in_service",
				"description",
			),
			read=EVERYONE,
			write=ADMIN,
			order_by=("name",),
			changed=_leave_type_changed,
		),
		Resource(
			"approval-processes",
			ApprovalProcess,
			("name", "description"),
			write=ADMIN,
			order_by=("name",),
			children={"steps": (ApprovalProcessStep, ("position", "approver_type", "approver_id"))},
			validate=_process,
		),
		Resource(
			"approval-overrides",
			ApprovalOverride,
			("employee_id", "request_type", "process_id"),
			write=ADMIN,
		),
		Resource(
			"report-templates",
			ReportTemplate,
			(
				"name",
				"source",
				"group_by",
				"time_unit",
				"default_range",
				"export_format",
				"text_delimiter",
				"text_encoding",
				"description",
				"columns",
				"shared_roles",
			),
			read=EVERYONE,  # narrowed by shared_roles in the reports service
			order_by=("name",),
			validate=_report_template,
		),
	)
}


def resource(name: str) -> Resource:
	try:
		return RESOURCES[name]
	except KeyError:
		raise NotFound(_("Not found")) from None


# approval defaults: one row per request type (primary key), so not a generic resource ------------


def assign_pattern(ctx: Context, employee_ids: list[int], values: dict[str, Any]) -> list[Any]:
	"""One work pattern for many people at once: one assignment per person, all or nothing.
	The newest assignment wins from its start date, so earlier ones need no editing."""
	people = list(dict.fromkeys(int(i) for i in employee_ids or []))
	if not people:
		raise ValidationError(_("Choose at least one person"))
	resource = RESOURCES["work-pattern-assignments"]
	fields = {
		k: values.get(k) for k in ("work_pattern_id", "valid_from", "valid_to", "cycle_offset_days", "note")
	}
	saved = []
	with ctx.session.begin_nested():
		for employee_id in people:
			if ctx.session.get(Employee, employee_id) is None:
				raise ValidationError(_("The employee {0} does not exist"), employee_id)
			row = {**fields, "target_type": TARGET_EMPLOYEE, "employee_id": employee_id}
			saved.append(save(ctx, resource, {k: v for k, v in row.items() if v is not None}))
	return saved


def set_approval_default(ctx: Context, request_type: str, process_id: int) -> ApprovalDefault:
	check(ctx.actor, ADMIN)
	row = ctx.session.get(ApprovalDefault, request_type)
	before = {"process_id": row.process_id} if row else None
	if row is None:
		row = ApprovalDefault(request_type=request_type, process_id=process_id)
		ctx.session.add(row)
	else:
		row.process_id = process_id
	flush(ctx.session)
	audit.log(
		ctx.session,
		"approval_default",
		request_type,
		"update" if before else "insert",
		ctx.actor.user_id,
		None,
		before,
		{"process_id": process_id},
	)
	return row
