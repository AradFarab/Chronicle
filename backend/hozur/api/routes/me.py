"""What the PWA needs on start: who you are, what you may do, warnings."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Today
from hozur.calendar.service import refresh_warning
from hozur.db.models import AppUser, Employee, Organization
from hozur.i18n import catalog
from hozur.services import access

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def me(actor: Actor, db: DB, today: Today) -> dict:
	user = db.get(AppUser, actor.user_id)
	employee = db.get(Employee, actor.employee_id) if actor.employee_id else None
	warnings = []
	if actor.is_operator:
		warning = refresh_warning(db, today)
		if warning:
			warnings.append(warning.translated(actor.language))
	return {
		"user": {
			"id": user.id,
			"username": user.username,
			"full_name": user.full_name,
			"language": user.language,
		},
		"roles": sorted(actor.roles),
		"employee": (
			{
				"id": employee.id,
				"code": employee.code,
				"full_name": employee.full_name,
				"department_id": employee.department_id,
				"branch_id": employee.branch_id,
			}
			if employee
			else None
		),
		"organization": db.scalar(select(Organization.name).where(Organization.id == 1)) or "",
		"today": today,
		"is_operator": actor.is_operator,
		"is_admin": actor.is_admin,
		"is_manager": access.is_manager(db, actor, today),
		"warnings": warnings,
	}


@router.get("/translations/{language}")
def translations(language: str) -> dict[str, str]:
	"""The app's Persian catalog for the PWA's __()."""
	return catalog(language)
