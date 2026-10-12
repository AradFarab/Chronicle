"""Attendance devices, device users, punch-file imports (operators)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from chronicle.api.deps import DB, Admin
from chronicle.api.views import jalali_moment
from chronicle.db.models import AttendanceDevice, DeviceUserMap, PunchImport, PunchImportTemplate
from chronicle.i18n import _, translate
from chronicle.services import audit, devices
from chronicle.services.errors import NotFound

router = APIRouter(prefix="/api/devices", tags=["devices"])


class Since(BaseModel):
	jdate: str


def device_view(d: AttendanceDevice) -> dict:
	view = audit.snapshot(d)
	view.pop("comm_key_encrypted")
	view["has_comm_key"] = bool(d.comm_key_encrypted)
	for key in ("last_sync_at", "last_health_check_at", "created_at", "updated_at"):
		view[key] = jalali_moment(getattr(d, key))
	return view


def _sync_view(result: devices.SyncResult, language: str) -> dict:
	return {
		"ok": result.ok,
		**result.stats,
		"message": result.error.translated(lambda t: translate(t, language)) if result.error else None,
	}


@router.get("/adapters")
def adapters(actor: Admin) -> list[dict]:
	return devices.adapter_types()


@router.get("")
def list_devices(actor: Admin, db: DB) -> list[dict]:
	return [device_view(d) for d in db.scalars(select(AttendanceDevice).order_by(AttendanceDevice.name))]


@router.post("")
def create_device(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return device_view(devices.save_device(db, values, actor.user_id))


@router.get("/{device_id:int}")
def get_device(device_id: int, actor: Admin, db: DB) -> dict:
	return device_view(devices.get_device(db, device_id))


@router.patch("/{device_id}")
def update_device(device_id: int, values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return device_view(devices.save_device(db, values, actor.user_id, device_id))


@router.delete("/{device_id}")
def delete_device(device_id: int, actor: Admin, db: DB) -> dict:
	devices.delete_device(db, devices.get_device(db, device_id), actor.user_id)
	return {"ok": True}


@router.post("/{device_id}/test")
def test_connection(device_id: int, actor: Admin, db: DB) -> dict:
	return devices.test_connection(db, devices.get_device(db, device_id))


@router.post("/{device_id}/sync")
def sync_now(device_id: int, actor: Admin, db: DB) -> dict:
	return _sync_view(devices.sync_device(db, devices.get_device(db, device_id)), actor.language)


@router.post("/{device_id}/resync")
def resync(device_id: int, body: Since, actor: Admin, db: DB) -> dict:
	return _sync_view(devices.resync_from(db, devices.get_device(db, device_id), body.jdate), actor.language)


@router.post("/{device_id}/read-users")
def read_users(device_id: int, actor: Admin, db: DB) -> dict:
	return devices.read_device_users(db, devices.get_device(db, device_id), actor.user_id)


@router.post("/{device_id}/set-clock")
def set_clock(device_id: int, actor: Admin, db: DB) -> dict:
	return {"set_to": devices.set_device_clock(db, devices.get_device(db, device_id), actor.user_id)}


# device users --------------------------------------------------------------------------------------


@router.get("/users/unmapped")
def unmapped(actor: Admin, db: DB) -> list[dict]:
	return devices.unmapped_device_users(db)


@router.get("/{device_id}/users")
def device_users(device_id: int, actor: Admin, db: DB) -> list[dict]:
	rows = db.scalars(
		select(DeviceUserMap)
		.where(DeviceUserMap.device_id == device_id)
		.order_by(DeviceUserMap.device_user_id)
	)
	return [audit.snapshot(m) for m in rows]


@router.post("/users")
def create_mapping(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return audit.snapshot(devices.save_mapping(db, values, actor.user_id))


@router.patch("/users/{map_id}")
def update_mapping(map_id: int, values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return audit.snapshot(devices.save_mapping(db, values, actor.user_id, map_id))


# file imports ------------------------------------------------------------------------------------


@router.get("/import-templates")
def templates(actor: Admin, db: DB) -> list[dict]:
	return [
		audit.snapshot(t) for t in db.scalars(select(PunchImportTemplate).order_by(PunchImportTemplate.name))
	]


@router.post("/import-templates")
def create_template(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return audit.snapshot(devices.save_template(db, values, actor.user_id))


@router.patch("/import-templates/{template_id}")
def update_template(template_id: int, values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return audit.snapshot(devices.save_template(db, values, actor.user_id, template_id))


def import_view(r: PunchImport) -> dict:
	view = audit.snapshot(r)
	view["imported_at"], view["created_at"] = jalali_moment(r.imported_at), jalali_moment(r.created_at)
	return view


@router.get("/imports")
def imports(actor: Admin, db: DB) -> list[dict]:
	return [
		import_view(r) for r in db.scalars(select(PunchImport).order_by(PunchImport.id.desc()).limit(200))
	]


@router.post("/{device_id}/import")
def import_file(
	device_id: int,
	template_id: Annotated[int, Form()],
	file: Annotated[UploadFile, File()],
	actor: Admin,
	db: DB,
) -> dict:
	template = db.get(PunchImportTemplate, template_id)
	if template is None:
		raise NotFound(_("Not found"))
	record = devices.import_file(
		db,
		devices.get_device(db, device_id),
		template,
		file.file.read(),
		file.filename or "punches",
		file.content_type,
		actor.user_id,
	)
	return import_view(record)
