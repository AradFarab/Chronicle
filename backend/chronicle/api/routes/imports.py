"""Excel import: the sample workbook of every create form, and the upload."""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile

from chronicle.api.deps import DB, Admin, Today
from chronicle.i18n import _, translate
from chronicle.services import excel, resources
from chronicle.services.errors import ValidationError

router = APIRouter(prefix="/api/import", tags=["import"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
def list_imports(actor: Admin) -> list[dict]:
	return [{**i, "title": translate(i["title"], actor.language)} for i in excel.available()]


@router.get("/{name}/template")
def sample(name: str, actor: Admin, db: DB) -> Response:
	"""The sample workbook: formats and drop-downs applied, every field of the form as a column."""
	spec = excel.spec(name)
	filename = f"{translate(_('Sample'), actor.language)} {translate(spec.title, actor.language)}.xlsx"
	return Response(
		excel.template(db, name, actor.language),
		media_type=XLSX,
		headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
	)


@router.post("/{name}/inspect")
async def inspect(
	name: str,
	file: Annotated[UploadFile, File()],
	actor: Admin,
	db: DB,
	sheet: Annotated[str | None, Form()] = None,
	header_row: Annotated[int | None, Form()] = None,
) -> dict:
	"""The column-mapping panel: the file's sheets and columns, the fields, suggested matches."""
	return excel.inspect_file(
		db, name, await file.read(), file.filename or "", actor.language, sheet or None, header_row
	)


@router.post("/{name}")
async def upload(
	name: str,
	file: Annotated[UploadFile, File()],
	actor: Admin,
	db: DB,
	today: Today,
	mapping: Annotated[str | None, Form()] = None,
	sheet: Annotated[str | None, Form()] = None,
	header_row: Annotated[int | None, Form()] = None,
	dry_run: Annotated[bool, Form()] = False,
) -> dict:
	"""All or nothing: if any row is wrong, nothing is saved and every wrong row is listed.
	`mapping` (JSON: field -> column number or {"value": ...}) connects the file's own columns;
	without it the sample's headers are used. `dry_run` checks and previews without saving."""
	try:
		fields = json.loads(mapping) if mapping else None
	except json.JSONDecodeError:
		raise ValidationError(_("The column mapping is not valid")) from None
	ctx = resources.Context(db, actor, today)
	return excel.run(
		ctx,
		name,
		await file.read(),
		filename=file.filename or "",
		mapping=fields,
		sheet=sheet or None,
		header_row=header_row,
		dry_run=dry_run,
	).as_dict()
