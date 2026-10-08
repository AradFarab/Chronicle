"""Labor-law parameters as data (CLAUDE.md rule 2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text, false, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.types import JDate


class LaborRuleSet(IdMixin, TimestampMixin, Base):
	"""Parameter values (names from hozur.engine.rules.PARAMETERS) valid from a Jalali day.

	The legal baseline is read-only and seeded from engine/data/labor_law_1369.json; a company
	rule set may only be more generous than it."""

	__tablename__ = "labor_rule_set"
	__table_args__ = (
		Index(
			"uq_labor_rule_set_baseline",
			"is_legal_baseline",
			unique=True,
			postgresql_where=text("is_legal_baseline"),
		),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	effective_from: Mapped[str] = mapped_column(JDate, unique=True)
	is_legal_baseline: Mapped[bool] = mapped_column(Boolean, server_default=false())
	description: Mapped[str | None] = mapped_column(Text)
	parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
	change_reason: Mapped[str | None] = mapped_column(Text)
