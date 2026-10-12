"""Which labor rule set applies on a day (CLAUDE.md rule 2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronicle.db.models import LaborRuleSet
from chronicle.engine.rules import PARAMETERS, RuleSet, baseline_rule_set, violations
from chronicle.i18n import _
from chronicle.services.errors import ValidationError


def rule_set_for(session: Session, jdate: str) -> tuple[LaborRuleSet, RuleSet]:
	"""The company rule set in force on the day (latest effective_from <= day), else the law."""
	row = session.scalar(
		select(LaborRuleSet)
		.where(LaborRuleSet.is_legal_baseline.is_(False), LaborRuleSet.effective_from <= jdate)
		.order_by(LaborRuleSet.effective_from.desc())
		.limit(1)
	)
	if row is None:
		row = session.scalar(select(LaborRuleSet).where(LaborRuleSet.is_legal_baseline))
	if row is None:
		raise ValidationError(_("The legal baseline Labor Rule Set is missing; run chronicle db install"))
	return row, RuleSet.from_mapping({p.name: row.parameters[p.name] for p in PARAMETERS})


def check_parameters(parameters: dict) -> dict:
	"""Every parameter present, numeric, and not worse for the worker than the law."""
	missing = [p.name for p in PARAMETERS if p.name not in parameters]
	if missing:
		raise ValidationError(_("Missing parameters: {0}"), ", ".join(missing))
	clean = {}
	for p in PARAMETERS:
		value = parameters[p.name]
		if not isinstance(value, int | float) or isinstance(value, bool):
			raise ValidationError(_("{0} must be a number"), p.name)
		clean[p.name] = value
	worse = violations(RuleSet.from_mapping(clean), baseline_rule_set())
	if worse:
		raise ValidationError(
			_("Worse for the worker than the law: {0}"),
			", ".join(f"{name} ({value} vs {legal})" for name, value, legal in worse),
		)
	return clean
