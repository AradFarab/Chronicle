# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.engine.rules import PARAMETERS, violations
from hozur.rule_sets import baseline_name, rule_set_from_doc
from hozur.utils import clean_jdate


class LaborRuleSet(Document):
	"""Legal parameters with an effective date (CLAUDE.md rule 2). The legal baseline is
	read-only; a company rule set may only be more generous to the worker."""

	def validate(self):
		clean_jdate(self, "effective_from", required=True)
		if self.is_legal_baseline:
			if not self.flags.from_seed and not self.is_new() and self.has_changed():
				frappe.throw(
					_(
						"The legal baseline is the law itself and cannot be edited. Create a company rule set instead."
					)
				)
			return
		base_name = baseline_name()
		if not base_name:
			return
		base = frappe.get_doc("Labor Rule Set", base_name)
		for p in PARAMETERS:
			if self.get(p.name) in (None, ""):
				self.set(p.name, base.get(p.name))
		worse = violations(rule_set_from_doc(self), rule_set_from_doc(base))
		if worse:
			lines = "".join(
				f"<li>{_(self.meta.get_label(name))}: {value} ({_('law')}: {legal})</li>"
				for name, value, legal in worse
			)
			frappe.throw(
				_("These values are worse for the worker than the law allows:") + f"<ul>{lines}</ul>",
				title=_("Below the Legal Floor"),
			)

	def has_changed(self):
		before = self.get_doc_before_save()
		return bool(before) and any(before.get(p.name) != self.get(p.name) for p in PARAMETERS)

	def on_trash(self):
		if self.is_legal_baseline:
			frappe.throw(_("The legal baseline cannot be deleted"))

	def on_update(self):
		from hozur.attendance import recalculate_everyone
		from hozur.utils import today_jalali

		if not self.is_legal_baseline and not self.flags.from_seed:
			recalculate_everyone(
				max(self.effective_from, _open_month_start()),
				today_jalali(),
				_("Labor rule set {0} changed").format(self.name),
			)


def _open_month_start() -> str:
	from hozur.utils import today_jalali

	return today_jalali()[:7] + "/01"


@frappe.whitelist()
def get_baseline_values() -> dict:
	name = baseline_name()
	doc = frappe.get_doc("Labor Rule Set", name)
	return {p.name: doc.get(p.name) for p in PARAMETERS}
