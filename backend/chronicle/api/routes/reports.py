"""Report builder: fields, templates, preview and export."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Response
from pydantic import BaseModel

from chronicle.api.deps import DB, Actor, Today
from chronicle.reports.catalog import SUMMARY
from chronicle.reports.exporters import HOURS_MINUTES
from chronicle.services import reports, resources

router = APIRouter(prefix="/api/reports", tags=["reports"])


class Run(BaseModel):
	template_id: int | None = None
	spec: dict[str, Any] | None = None
	filters: dict[str, Any] = {}
	export_format: str | None = None
	limit: int = 500


@router.get("/fields")
def fields(actor: Actor, db: DB, source: str = SUMMARY) -> list[dict]:
	return reports.fields(db, source, actor.language)


@router.get("/templates")
def templates(actor: Actor, db: DB) -> list[dict]:
	resource = resources.resource("report-templates")
	return [resources.view(resource, t) for t in reports.visible_templates(db, actor)]


@router.post("/preview")
def preview(body: Run, actor: Actor, db: DB, today: Today) -> dict:
	spec = reports.spec_for(db, actor, body.template_id, body.spec)
	result = reports.build(db, actor, today, spec, body.filters)
	result["total_rows"] = len(result["rows"])
	result["rows"] = result["rows"][: max(1, min(body.limit, 5000))]
	result["time_unit"] = spec.get("time_unit") or HOURS_MINUTES
	return result


@router.post("/export")
def export(body: Run, actor: Actor, db: DB, today: Today) -> Response:
	spec = reports.spec_for(db, actor, body.template_id, body.spec)
	filename, content_type, content = reports.render(db, actor, today, spec, body.filters, body.export_format)
	return Response(
		content,
		media_type=content_type,
		headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
	)
