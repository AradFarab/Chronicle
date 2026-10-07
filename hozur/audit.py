"""Append-only audit trail (CLAUDE.md rule 4): who, when, why, before/after.

Doctypes listed in hooks.doc_events get Insert/Update/Delete entries automatically.
A doctype with a `change_reason` field must be given a reason for every update; the
reason is stored in the Audit Entry and cleared on the document afterwards.
"""

import json

import frappe
from frappe import _

from hozur.utils import now_jalali

IGNORED_FIELDS = {
	"modified",
	"modified_by",
	"creation",
	"owner",
	"idx",
	"lft",
	"rgt",
	"old_parent",
	"change_reason",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"_seen",
}


def _snapshot(doc) -> dict:
	data = doc.as_dict(no_default_fields=True, convert_dates_to_str=True)
	return {k: v for k, v in data.items() if k not in IGNORED_FIELDS and not k.startswith("__")}


def _diff(before: dict, after: dict) -> list[str]:
	keys = set(before) | set(after)
	return sorted(k for k in keys if (before.get(k) or None) != (after.get(k) or None))


def log(reference_doctype, reference_name, action, reason=None, before=None, after=None, changed=None):
	jdate, time = now_jalali()
	entry = frappe.get_doc(
		{
			"doctype": "Audit Entry",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"action": action,
			"user": frappe.session.user,
			"at_jdate": jdate,
			"at_time": time,
			"reason": reason,
			"changed_fields": ", ".join(changed or []),
			"before": json.dumps(before, ensure_ascii=False, indent=1, default=str)
			if before is not None
			else None,
			"after": json.dumps(after, ensure_ascii=False, indent=1, default=str)
			if after is not None
			else None,
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	return entry


def _reason(doc):
	return doc.get("change_reason") or doc.flags.get("audit_reason")


def require_reason(doc, method=None):
	"""validate hook: updates to doctypes with a change_reason field need a reason."""
	if doc.is_new() or doc.flags.get("from_seed") or not doc.meta.has_field("change_reason"):
		return
	before = doc.get_doc_before_save()
	if before and _diff(_snapshot(before), _snapshot(doc)) and not (doc.get("change_reason") or "").strip():
		frappe.throw(_("Please enter the reason for this change"), title=_("Reason Required"))


def on_update(doc, method=None):
	if doc.flags.get("skip_audit"):
		return
	if doc.flags.get("in_insert"):
		log(doc.doctype, doc.name, "Insert", _reason(doc), after=_snapshot(doc))
	else:
		before_doc = doc.get_doc_before_save()
		before = _snapshot(before_doc) if before_doc else {}
		after = _snapshot(doc)
		changed = _diff(before, after)
		if not changed:
			return
		log(
			doc.doctype,
			doc.name,
			"Update",
			_reason(doc),
			before={k: before.get(k) for k in changed},
			after={k: after.get(k) for k in changed},
			changed=changed,
		)
	if doc.meta.has_field("change_reason") and doc.get("change_reason"):
		frappe.db.set_value(doc.doctype, doc.name, "change_reason", None, update_modified=False)
		doc.change_reason = None


def on_trash(doc, method=None):
	if doc.flags.get("skip_audit"):
		return
	log(doc.doctype, doc.name, "Delete", _reason(doc), before=_snapshot(doc))
