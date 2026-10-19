"""Payslips: the system admin's screens (upload, month overview, SMS) and the employee's
public link page. The public routes need no login: the token in the link and the last four
digits of the national id are the two factors."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Request, Response, UploadFile
from pydantic import BaseModel

from chronicle.api.deps import DB, Admin
from chronicle.api.views import jalali_moment
from chronicle.i18n import _
from chronicle.services import payslips as service
from chronicle.services import sms as sms_service
from chronicle.services.errors import ValidationError

router = APIRouter(prefix="/api/payslips", tags=["payslips"])
public = APIRouter(prefix="/api/payslip-link", tags=["payslips"])

MAX_UPLOAD = 100 * 1024 * 1024  # bytes per file


class SendRequest(BaseModel):
	mode: str = "unsent"
	payslip_ids: list[int] | None = None


class Secret(BaseModel):
	secret: str = ""


# settings and the SMS connection ----------------------------------------------------------------


@router.get("/settings")
def get_settings(actor: Admin, db: DB) -> dict[str, Any]:
	return service.get_settings(db)


@router.put("/settings")
def put_settings(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return service.save_settings(db, actor, values)


@router.get("/sms")
def get_sms(actor: Admin, db: DB) -> dict[str, Any]:
	return sms_service.view(db)


@router.put("/sms")
def put_sms(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms_service.save(db, values, actor.user_id)


@router.post("/sms/test")
def test_sms(actor: Admin, db: DB) -> dict[str, Any]:
	return sms_service.check(db)


# one payslip or link ----------------------------------------------------------------------------


@router.get("/item/{payslip_id}")
def payslip_file(payslip_id: int, actor: Admin, db: DB) -> Response:
	return Response(
		service.payslip_file(db, actor, payslip_id),
		media_type="application/pdf",
		headers={"Cache-Control": "no-store, private", "Content-Disposition": "inline"},
	)


@router.delete("/item/{payslip_id}")
def delete_payslip(payslip_id: int, actor: Admin, db: DB) -> dict:
	service.delete_payslip(db, actor, payslip_id)
	return {"ok": True}


@router.post("/link/{link_id}/void")
def void_link(link_id: int, actor: Admin, db: DB) -> dict:
	service.void_link(db, actor, link_id)
	return {"ok": True}


# a month ----------------------------------------------------------------------------------------


@router.get("/{jyear}/{jmonth}")
def month(jyear: int, jmonth: int, actor: Admin, db: DB) -> dict[str, Any]:
	data = service.overview(db, actor, jyear, jmonth)
	for row in data["rows"]:
		link = row["link"]
		if link:
			link["sms_sent_at"] = jalali_moment(link["sms_sent_at"])
			link["expires_at"] = jalali_moment(link["expires_at"])
	for rejection in data["rejections"]:
		rejection["created_at"] = jalali_moment(rejection["created_at"])
	return data


@router.post("/{jyear}/{jmonth}/upload")
def upload(jyear: int, jmonth: int, actor: Admin, db: DB, files: Annotated[list[UploadFile], File()]) -> dict:
	uploads = []
	for f in files:
		content = f.file.read(MAX_UPLOAD + 1)
		if len(content) > MAX_UPLOAD:
			raise ValidationError(_("The file {0} is larger than 100 MB"), f.filename or "")
		uploads.append((f.filename or "", content))
	if not uploads:
		raise ValidationError(_("No file was chosen"))
	return service.upload(db, actor, jyear, jmonth, uploads)


@router.delete("/{jyear}/{jmonth}/rejections")
def clear_rejections(jyear: int, jmonth: int, actor: Admin, db: DB) -> dict:
	service.clear_rejections(db, actor, jyear, jmonth)
	return {"ok": True}


@router.post("/{jyear}/{jmonth}/send-preview")
def send_preview(jyear: int, jmonth: int, body: SendRequest, actor: Admin, db: DB) -> dict[str, Any]:
	return service.preview(db, actor, jyear, jmonth, body.mode, body.payslip_ids)


@router.post("/{jyear}/{jmonth}/send")
def send(jyear: int, jmonth: int, body: SendRequest, actor: Admin, db: DB) -> dict[str, Any]:
	return service.queue_send(db, actor, jyear, jmonth, body.mode, body.payslip_ids)


# the employee's link (no login) -----------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
	return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


@public.get("/{token}")
def link_info(token: str, db: DB) -> dict[str, str]:
	return service.link_info(db, token)


@public.post("/{token}")
def open_payslip(token: str, body: Secret, request: Request, db: DB) -> Response:
	content, filename = service.open_payslip(db, token, body.secret, _client_ip(request))
	return Response(
		content,
		media_type="application/pdf",
		headers={
			"Content-Disposition": f'inline; filename="{filename}"',
			# not in the browser's or a proxy's cache
			"Cache-Control": "no-store, no-cache, must-revalidate, private",
			"Pragma": "no-cache",
			"X-Content-Type-Options": "nosniff",
		},
	)
