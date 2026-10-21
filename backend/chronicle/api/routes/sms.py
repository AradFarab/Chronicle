"""The SMS section of the admin: panels, templates, events, the send window, opt-outs and the
message history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chronicle.api.deps import DB, Admin
from chronicle.api.views import jalali_moment
from chronicle.services import sms, sms_dispatch
from chronicle.services.errors import ValidationError

router = APIRouter(prefix="/api/sms", tags=["sms"])


class Active(BaseModel):
	is_active: bool


class TestSend(BaseModel):
	event: str
	to: str


class Resolve(BaseModel):
	outcome: str
	note: str | None = None


def _moments(view: dict[str, Any]) -> dict[str, Any]:
	for key in ("queued_at", "send_after", "sent_at"):
		if key in view:
			view[key] = jalali_moment(view[key])
	return view


# drivers, events, settings -----------------------------------------------------------------------


@router.get("/drivers")
def drivers(actor: Admin) -> list[dict[str, Any]]:
	return sms.drivers()


@router.get("/events")
def events(actor: Admin, db: DB) -> list[dict[str, Any]]:
	return sms.list_events(db)


@router.put("/events/{code}")
def set_event(code: str, body: Active, actor: Admin, db: DB) -> dict[str, Any]:
	return sms.set_event_active(db, actor, code, body.is_active)


@router.get("/settings")
def get_settings(actor: Admin, db: DB) -> dict[str, Any]:
	return sms.get_settings(db)


@router.put("/settings")
def put_settings(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.save_settings(db, actor, values)


# panels ------------------------------------------------------------------------------------------


@router.get("/providers")
def providers(actor: Admin, db: DB) -> list[dict[str, Any]]:
	return sms.list_providers(db)


@router.put("/providers/{code}")
def put_provider(code: str, values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.save_provider(db, actor, code, values)


@router.delete("/providers/{code}")
def delete_provider(code: str, actor: Admin, db: DB) -> dict:
	sms.delete_provider(db, actor, code)
	return {"ok": True}


@router.post("/providers/{code}/test")
def test_provider(code: str, actor: Admin, db: DB) -> dict[str, Any]:
	return sms.test_provider(db, actor, code)


# templates ---------------------------------------------------------------------------------------


@router.get("/templates")
def templates(actor: Admin, db: DB) -> list[dict[str, Any]]:
	return sms.list_templates(db)


@router.post("/templates")
def create_template(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.save_template(db, actor, values)


@router.post("/templates/preview")
def preview_template(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.preview(db, actor, values)


@router.post("/test-send")
def test_send(body: TestSend, actor: Admin, db: DB) -> dict[str, Any]:
	"""A real message now through the saved, active template of the event."""
	event = sms.event_by_code(db, body.event)
	problem = sms_dispatch.readiness(db, body.event)
	if problem:
		raise ValidationError(problem)
	message = sms_dispatch.test_send(db, body.event, body.to, sms.sample_context(event))
	return _moments(sms.get_message(db, actor, message.id))


@router.patch("/templates/{template_id}")
def update_template(template_id: int, values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.save_template(db, actor, values, template_id)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, actor: Admin, db: DB) -> dict:
	sms.delete_template(db, actor, template_id)
	return {"ok": True}


# history -----------------------------------------------------------------------------------------


@router.get("/messages")
def messages(
	actor: Admin,
	db: DB,
	status: str | None = None,
	event: str | None = None,
	to: str | None = None,
	limit: int = Query(100, le=500),
	offset: int = 0,
) -> dict[str, Any]:
	data = sms.list_messages(db, actor, status, event, to, limit, offset)
	data["items"] = [_moments(m) for m in data["items"]]
	return data


@router.get("/review")
def review(actor: Admin, db: DB) -> list[dict[str, Any]]:
	return [_moments(m) for m in sms.needs_review(db, actor)]


@router.get("/messages/{message_id}")
def message(message_id: int, actor: Admin, db: DB) -> dict[str, Any]:
	return _moments(sms.get_message(db, actor, message_id))


@router.post("/messages/{message_id}/resolve")
def resolve(message_id: int, body: Resolve, actor: Admin, db: DB) -> dict[str, Any]:
	return _moments(sms.resolve_message(db, actor, message_id, body.outcome, body.note))


# opt-outs ----------------------------------------------------------------------------------------


@router.get("/opt-outs")
def opt_outs(actor: Admin, db: DB) -> list[dict[str, Any]]:
	return sms.list_opt_outs(db)


@router.post("/opt-outs")
def add_opt_out(values: dict[str, Any], actor: Admin, db: DB) -> dict[str, Any]:
	return sms.add_opt_out(db, actor, values)


@router.delete("/opt-outs/{opt_out_id}")
def remove_opt_out(opt_out_id: int, actor: Admin, db: DB) -> dict:
	sms.remove_opt_out(db, actor, opt_out_id)
	return {"ok": True}
