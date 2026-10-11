"""Configuration screens: org, schedules, rule sets, leave types, approval processes, users,
settings and the audit trail. Generic tables go through hozur.services.resources."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Admin, Today
from hozur.api.views import jalali_moment
from hozur.db.models import ApprovalDefault, AppUser, AuditEntry, Employee, Organization
from hozur.db.models.requests import ADMIN_ENTRY, REQUEST_TYPES
from hozur.i18n import _
from hozur.services import audit, backup, resources, settings, users
from hozur.services.errors import NotFound, ValidationError
from hozur.setup.data import SETTINGS

router = APIRouter(prefix="/api/admin", tags=["admin"])


class Reason(BaseModel):
	reason: str | None = None


def _ctx(db, actor, today) -> resources.Context:
	return resources.Context(db, actor, today)


# organization (one row) -----------------------------------------------------------------------

ORGANIZATION_FIELDS = (
	"name",
	"legal_name",
	"national_id",
	"economic_code",
	"insurance_workshop_code",
	"phone",
	"address",
)


@router.get("/organization")
def get_organization(actor: Actor, db: DB) -> dict:
	org = db.get(Organization, 1)
	return audit.snapshot(org) if org else {"id": 1, "name": ""}


@router.put("/organization")
def put_organization(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	org = db.get(Organization, 1)
	before = audit.snapshot(org) if org else None
	if org is None:
		org = Organization(id=1)
		db.add(org)
	for key in ORGANIZATION_FIELDS:
		if key in values:
			setattr(org, key, resources.coerce(Organization, key, values[key]))
	if not (org.name or "").strip():
		raise ValidationError(_("Enter a name"))
	resources.flush(db)
	audit.log(
		db,
		"organization",
		1,
		"update" if before else "insert",
		actor.user_id,
		None,
		before,
		audit.snapshot(org),
	)
	return audit.snapshot(org)


# approval defaults ---------------------------------------------------------------------------------


@router.get("/approval-defaults")
def approval_defaults(actor: Admin, db: DB) -> list[dict]:
	rows = {r.request_type: r.process_id for r in db.scalars(select(ApprovalDefault))}
	return [{"request_type": t, "process_id": rows.get(t)} for t in (*REQUEST_TYPES, ADMIN_ENTRY)]


@router.put("/approval-defaults/{request_type}")
def set_approval_default(
	request_type: str, values: dict[str, Any], actor: Admin, db: DB, today: Today
) -> dict:
	if request_type not in (*REQUEST_TYPES, ADMIN_ENTRY):
		raise NotFound(_("Not found"))
	row = resources.set_approval_default(_ctx(db, actor, today), request_type, int(values["process_id"]))
	return {"request_type": row.request_type, "process_id": row.process_id}


# labor rule parameters ------------------------------------------------------------------------


@router.get("/rule-parameters")
def rule_parameters(actor: Actor, db: DB) -> list[dict]:
	"""Every legal parameter with its article, unit, direction and the legal value (for the form)."""
	from dataclasses import asdict

	from hozur.engine.rules import PARAMETERS, baseline_rule_set

	law = baseline_rule_set()
	return [{**asdict(p), "legal_value": getattr(law, p.name)} for p in PARAMETERS]


# settings ------------------------------------------------------------------------------------------


@router.get("/settings")
def get_settings(actor: Admin, db: DB) -> dict[str, Any]:
	return {key: settings.get(db, key) for key in SETTINGS}


@router.put("/settings")
def put_settings(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	unknown = sorted(set(values) - set(SETTINGS))
	if unknown:
		raise ValidationError(_("Unknown settings: {0}"), ", ".join(unknown))
	before = {key: settings.get(db, key) for key in values}
	for key, value in values.items():
		default = SETTINGS[key]
		if isinstance(default, bool):
			value = bool(value)
		elif isinstance(default, int):
			try:
				value = int(value)
			except (TypeError, ValueError):
				raise ValidationError(_("{0} must be a number"), key) from None
		settings.set_value(db, key, value, actor.user_id)
	audit.log(db, "app_setting", "settings", "update", actor.user_id, None, before, dict(values))
	return {key: settings.get(db, key) for key in SETTINGS}


# users -----------------------------------------------------------------------------------------------


class NewUser(BaseModel):
	username: str
	full_name: str | None = None
	password: str
	roles: list[str] = []


class Password(BaseModel):
	password: str


def _user(db, user_id: int) -> AppUser:
	user = db.get(AppUser, user_id)
	if user is None:
		raise NotFound(_("Not found"))
	return user


@router.get("/users")
def list_users(actor: Admin, db: DB) -> list[dict]:
	links = dict(db.execute(select(Employee.user_id, Employee.id).where(Employee.user_id.is_not(None))).all())
	return [
		{
			**users.user_view(u),
			"employee_id": links.get(u.id),
			"last_login_at": jalali_moment(u.last_login_at),
		}
		for u in db.scalars(select(AppUser).order_by(AppUser.username))
	]


@router.post("/users")
def create_user(body: NewUser, actor: Admin, db: DB) -> dict:
	"""A login with no employee record (e.g. an IT admin). Employees get theirs when they are
	created, in the employees screen."""
	user = users.create_user(
		db, body.username, body.full_name or body.username, body.password, body.roles, require_password=True
	)
	resources.flush(db)
	audit.log(
		db,
		"app_user",
		user.id,
		"insert",
		actor.user_id,
		None,
		after=users.user_view(user) | {"last_login_at": None},
	)
	return users.user_view(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return users.user_view(users.update_user(db, _user(db, user_id), values, actor.user_id))


@router.post("/users/{user_id}/password")
def reset_password(user_id: int, body: Password, actor: Admin, db: DB) -> dict:
	users.set_password(db, _user(db, user_id), body.password, actor.user_id)
	return {"ok": True}


# audit trail ---------------------------------------------------------------------------------------


@router.get("/audit")
def audit_trail(
	actor: Admin,
	db: DB,
	entity: str | None = None,
	entity_id: str | None = None,
	limit: int = Query(100, le=1000),
) -> list[dict]:
	query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
	if entity:
		query = query.where(AuditEntry.entity == entity)
	if entity_id:
		query = query.where(AuditEntry.entity_id == entity_id)
	names = dict(db.execute(select(AppUser.id, AppUser.full_name)).all())
	return [
		{
			"id": e.id,
			"entity": e.entity,
			"entity_id": e.entity_id,
			"action": e.action,
			"user": names.get(e.user_id),
			"at": jalali_moment(e.at),
			"reason": e.reason,
			"changed_fields": e.changed_fields,
			"before": e.before,
			"after": e.after,
		}
		for e in db.scalars(query)
	]


# backups ----------------------------------------------------------------------------------------


@router.get("/backups")
def list_backups(actor: Admin, db: DB) -> dict:
	return {
		"backups": [b.as_dict() for b in backup.list_backups()],
		"schedule": backup.schedule(db),
		"available": backup.tools_available(),
		"folder": str(backup.folder()),
	}


@router.post("/backups")
def create_backup(actor: Admin, db: DB) -> dict:
	made = backup.create(db, automatic=False, user_id=actor.user_id)
	audit.log(db, "backup", made.name, "insert", actor.user_id, "backup taken")
	return made.as_dict()


@router.put("/backups/schedule")
def set_backup_schedule(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return backup.set_schedule(db, values, actor.user_id)


@router.get("/backups/{name}")
def download_backup(name: str, actor: Admin) -> FileResponse:
	return FileResponse(backup.path_of(name), media_type="application/zip", filename=name)


@router.delete("/backups/{name}")
def delete_backup(name: str, actor: Admin, db: DB) -> dict:
	backup.delete(name)
	audit.log(db, "backup", name, "delete", actor.user_id, "backup deleted")
	return {"ok": True}


class BulkAssignment(BaseModel):
	employee_ids: list[int]
	work_pattern_id: int
	valid_from: str
	valid_to: str | None = None
	cycle_offset_days: int | None = None
	note: str | None = None


@router.post("/work-pattern-assignments/bulk")
def assign_pattern_to_many(body: BulkAssignment, actor: Actor, db: DB, today: Today) -> list[dict]:
	"""Give one work pattern to several people at once."""
	resource = resources.resource("work-pattern-assignments")
	values = body.model_dump(exclude={"employee_ids"})
	saved = resources.assign_pattern(_ctx(db, actor, today), body.employee_ids, values)
	return [resources.view(resource, r) for r in saved]


# generic tables (keep last: the path parameter matches any name) ------------------------------------


@router.get("/{name}")
def list_rows(name: str, actor: Actor, db: DB, today: Today) -> list[dict]:
	resource = resources.resource(name)
	ctx = _ctx(db, actor, today)
	return [resources.view(resource, r) for r in resources.list_rows(ctx, resource)]


@router.get("/{name}/{row_id}")
def get_row(name: str, row_id: int, actor: Actor, db: DB, today: Today) -> dict:
	resource = resources.resource(name)
	ctx = _ctx(db, actor, today)
	return resources.view(resource, resources.get_row(ctx, resource, row_id))


@router.post("/{name}")
def create_row(name: str, values: dict[str, Any], actor: Actor, db: DB, today: Today) -> dict:
	resource = resources.resource(name)
	return resources.view(resource, resources.save(_ctx(db, actor, today), resource, values))


@router.patch("/{name}/{row_id}")
def update_row(name: str, row_id: int, values: dict[str, Any], actor: Actor, db: DB, today: Today) -> dict:
	resource = resources.resource(name)
	return resources.view(resource, resources.save(_ctx(db, actor, today), resource, values, row_id))


@router.delete("/{name}/{row_id}")
def delete_row(
	name: str, row_id: int, actor: Actor, db: DB, today: Today, body: Reason | None = None
) -> dict:
	resources.delete(_ctx(db, actor, today), resources.resource(name), row_id, body.reason if body else None)
	return {"ok": True}
