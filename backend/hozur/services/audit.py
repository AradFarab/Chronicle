"""The audit trail (CLAUDE.md rule 4): who changed what, when and why."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from hozur.db.models import AuditEntry


def _plain(value: Any) -> Any:
	if isinstance(value, datetime | date | time):
		return value.isoformat()
	if isinstance(value, Decimal):
		return float(value)
	return value


def snapshot(obj: Any, exclude: tuple[str, ...] = ("created_at", "updated_at")) -> dict[str, Any]:
	"""Column values of a model instance, JSON-ready."""
	mapper = inspect(obj).mapper
	return {c.key: _plain(getattr(obj, c.key)) for c in mapper.column_attrs if c.key not in exclude}


def log(
	session: Session,
	entity: str,
	entity_id: object,
	action: str,
	user_id: int | None = None,
	reason: str | None = None,
	before: dict[str, Any] | None = None,
	after: dict[str, Any] | None = None,
) -> AuditEntry:
	changed = sorted(
		k for k in set(before or {}) | set(after or {}) if (before or {}).get(k) != (after or {}).get(k)
	)
	entry = AuditEntry(
		entity=entity,
		entity_id=str(entity_id),
		action=action,
		user_id=user_id,
		reason=reason,
		changed_fields=changed,
		before=before,
		after=after,
	)
	session.add(entry)
	return entry
