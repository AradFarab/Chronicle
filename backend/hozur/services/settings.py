"""App settings (app_setting): small JSON values the operator can change."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from hozur.db.models import AppSetting
from hozur.setup.data import SETTINGS


def get(session: Session, key: str, default: Any = None) -> Any:
	row = session.get(AppSetting, key)
	if row is not None:
		return row.value
	return SETTINGS.get(key, default)


def set_value(session: Session, key: str, value: Any, user_id: int | None = None) -> None:
	row = session.get(AppSetting, key)
	if row is None:
		session.add(AppSetting(key=key, value=value, updated_by_id=user_id))
	else:
		row.value, row.updated_by_id = value, user_id
