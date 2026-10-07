"""Which Labor Rule Set applies on a day, and the read-only legal baseline."""

import frappe
from frappe import _
from frappe.utils.caching import request_cache

from hozur.engine.rules import PARAMETERS, RuleSet, load_baseline


def baseline_name() -> str | None:
	return frappe.db.get_value("Labor Rule Set", {"is_legal_baseline": 1}, "name")


def rule_set_from_doc(doc) -> RuleSet:
	return RuleSet.from_mapping({p.name: doc.get(p.name) for p in PARAMETERS})


@request_cache
def get_rule_set(jdate: str) -> tuple[str, RuleSet]:
	"""The company rule set in force on the day (latest effective_from <= day), else the law."""
	names = frappe.get_all(
		"Labor Rule Set",
		filters={"is_legal_baseline": 0, "effective_from": ["<=", jdate]},
		order_by="effective_from desc",
		limit=1,
		pluck="name",
	)
	name = names[0] if names else baseline_name()
	if not name:
		frappe.throw(_("The legal baseline Labor Rule Set is missing; run bench migrate"))
	return name, rule_set_from_doc(frappe.get_cached_doc("Labor Rule Set", name))


def seed_baseline() -> None:
	if baseline_name():
		return
	data = load_baseline()
	doc = frappe.get_doc(
		{
			"doctype": "Labor Rule Set",
			"rule_set_name": data["name"],
			"effective_from": data["effective_from"],
			"is_legal_baseline": 1,
			"description": data["source"],
			**{k: v["value"] for k, v in data["parameters"].items()},
		}
	)
	doc.flags.from_seed = doc.flags.skip_audit = True
	doc.insert(ignore_permissions=True)
