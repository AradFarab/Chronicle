"""Excel import: the sample workbook of every create form, and the upload."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Response, UploadFile

from hozur.api.deps import DB, Admin, Today
from hozur.i18n import _, translate
from hozur.services import excel, resources

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


@router.post("/{name}")
async def upload(name: str, file: Annotated[UploadFile, File()], actor: Admin, db: DB, today: Today) -> dict:
	"""All or nothing: if any row is wrong, nothing is saved and every wrong row is listed."""
	ctx = resources.Context(db, actor, today)
	return excel.run(ctx, name, await file.read()).as_dict()
