"""Report builder endpoints for the desk and the PWA."""

from __future__ import annotations

import json

import frappe
from frappe import _

from hozur.jalali.dates import month_bounds
from hozur.reports import builder, catalog, exporters
from hozur.utils import now_jalali, today_jalali

FONT_DIR = "hozur/public/fonts/vazirmatn"
EXTENSIONS = {"Excel": "xlsx", "CSV": "csv", "Text": "txt", "PDF": "pdf"}


def _range(default_range: str | None) -> tuple[str, str]:
	today = today_jalali()
	year, month = int(today[:4]), int(today[5:7])
	if default_range == "Today":
		return today, today
	if default_range == "Previous Month":
		year, month = (year, month - 1) if month > 1 else (year - 1, 12)
	return month_bounds(year, month)


def _template(name: str) -> dict:
	doc = frappe.get_doc("Report Template", name)
	doc.check_permission("read")
	return {
		"title": doc.template_name,
		"source": doc.source,
		"group_by": doc.group_by or "",
		"time_unit": doc.time_unit,
		"default_range": doc.default_range,
		"export_format": doc.export_format,
		"text_delimiter": doc.text_delimiter,
		"text_encoding": doc.text_encoding,
		"columns": [{"field": c.field, "label": c.label, "width": c.width} for c in doc.columns],
	}


def _spec(template: str | None, spec: str | dict | None) -> dict:
	if template:
		return _template(template)
	spec = json.loads(spec) if isinstance(spec, str) else (spec or {})
	frappe.only_for(["System Manager", "Hozur Operator"])
	return spec


def _filters(spec: dict, filters) -> dict:
	filters = json.loads(filters) if isinstance(filters, str) else dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		filters["from_date"], filters["to_date"] = _range(spec.get("default_range"))
	return filters


def _day_minutes(jdate: str) -> int:
	from hozur.rule_sets import get_rule_set

	return get_rule_set(jdate)[1].hourly_leave_minutes_per_day


@frappe.whitelist()
def fields(source: str = catalog.SUMMARY) -> list[dict]:
	"""The field list the builder may use, grouped and translated."""
	out = [
		{"key": f.key, "label": _(f.label), "group": _(f.group), "kind": f.kind}
		for f in catalog.FIELDS
		if source in f.sources
	]
	out += [
		{"key": catalog.LEAVE_PREFIX + t, "label": t, "group": _("Leave by Type"), "kind": catalog.DAYS}
		for t in sorted(builder.leave_types())
	]
	return out


@frappe.whitelist()
def preview(template: str | None = None, spec=None, filters=None, limit: int = 500) -> dict:
	spec = _spec(template, spec)
	result = builder.build(spec, _filters(spec, filters))
	result["total_rows"] = len(result["rows"])
	result["rows"] = result["rows"][: int(limit)]
	result["time_unit"] = spec.get("time_unit") or exporters.HOURS_MINUTES
	return result


def render(spec: dict, filters: dict, export_format: str | None = None) -> tuple[str, bytes]:
	result = builder.build(spec, filters)
	export_format = export_format or spec.get("export_format") or "Excel"
	unit = spec.get("time_unit") or exporters.HOURS_MINUTES
	day_minutes = _day_minutes(result["to_date"])
	title = spec.get("title") or _("Report")
	org = frappe.db.get_single_value("Organization", "organization_name") or ""
	jdate, time = now_jalali()
	meta = [
		" · ".join(x for x in (org, f"{result['from_date']} – {result['to_date']}") if x),
		_("Prepared by {0} on {1} at {2}").format(
			frappe.utils.get_fullname(frappe.session.user), jdate, time
		),
	]
	columns, rows = result["columns"], result["rows"]
	if export_format == "Excel":
		content = exporters.to_xlsx(title, meta, columns, rows, unit, day_minutes)
	elif export_format in ("CSV", "Text"):
		content = exporters.to_text(
			columns,
			rows,
			unit,
			day_minutes,
			spec.get("text_delimiter") or "Comma",
			spec.get("text_encoding") or "UTF-8",
		)
	elif export_format == "PDF":
		font_url = "file://" + frappe.get_app_path("hozur", "public", "fonts", "vazirmatn")
		content = exporters.to_pdf(title, meta, columns, rows, unit, day_minutes, font_url)
	else:
		frappe.throw(_("Unknown export format"))
	filename = f"{title} {result['from_date']} {result['to_date']}.{EXTENSIONS[export_format]}".replace(
		"/", "-"
	)
	return filename, content


@frappe.whitelist()
def export(template: str | None = None, spec=None, filters=None, export_format: str | None = None):
	spec = _spec(template, spec)
	filename, content = render(spec, _filters(spec, filters), export_format)
	frappe.response["type"] = "download"
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = content


def template_query(user=None, doctype=None):
	"""Templates a user may see: standard ones, their own, or shared with one of their roles."""
	from hozur.permissions import has_all_access

	user = user or frappe.session.user
	if has_all_access(user):
		return ""
	roles = ", ".join(frappe.db.escape(r) for r in frappe.get_roles(user)) or "''"
	return (
		f"(`tabReport Template`.is_standard = 1 or `tabReport Template`.owner = {frappe.db.escape(user)} "
		f"or `tabReport Template`.name in (select parent from `tabReport Template Role` where role in ({roles})))"
	)


def has_template_permission(doc, ptype=None, user=None, debug=False):
	from hozur.permissions import has_all_access

	user = user or frappe.session.user
	if has_all_access(user) or doc.is_standard or doc.owner == user:
		return True
	return ptype == "read" and bool({r.role for r in doc.shared_with} & set(frappe.get_roles(user)))
