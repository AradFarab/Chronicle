"""Holidays and the yearly calendar refresh (operators)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Admin
from hozur.api.views import holiday_view, jalali_moment
from hozur.calendar import service
from hozur.db.models import CalendarYear, Holiday
from hozur.jalali.dates import year_bounds

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class HolidayChange(BaseModel):
	values: dict[str, Any]
	reason: str | None = None


class Reason(BaseModel):
	reason: str


@router.get("/years")
def years(actor: Actor, db: DB) -> list[dict]:
	return [
		{
			"jyear": y.jyear,
			"status": y.status,
			"source": y.source,
			"refreshed_at": jalali_moment(y.refreshed_at),
			"holiday_count": y.holiday_count,
		}
		for y in db.scalars(select(CalendarYear).order_by(CalendarYear.jyear))
	]


@router.get("/holidays")
def holidays(year: int, actor: Actor, db: DB) -> list[dict]:
	start, end = year_bounds(year)
	rows = db.scalars(
		select(Holiday).where(Holiday.jdate.between(start, end)).order_by(Holiday.jdate, Holiday.id)
	)
	return [holiday_view(h) for h in rows]


@router.post("/holidays")
def create(values: dict[str, Any], actor: Admin, db: DB) -> dict:
	return holiday_view(service.create_holiday(db, values, actor.user_id))


@router.patch("/holidays/{holiday_id}")
def update(holiday_id: int, body: HolidayChange, actor: Admin, db: DB) -> dict:
	return holiday_view(service.update_holiday(db, holiday_id, body.values, body.reason or "", actor.user_id))


@router.post("/holidays/{holiday_id}/delete")
def delete(holiday_id: int, body: Reason, actor: Admin, db: DB) -> dict:
	service.delete_holiday(db, holiday_id, body.reason, actor.user_id)
	return {"ok": True}


async def _source(db, source: str, file: UploadFile | None):
	content = await file.read() if file is not None else None
	return service.make_source(db, source, content, file.filename if file else "")


@router.post("/refresh/preview")
async def preview(
	actor: Admin,
	db: DB,
	year: Annotated[int, Form()],
	source: Annotated[str, Form()] = "time_ir",
	file: Annotated[UploadFile | None, File()] = None,
) -> dict:
	"""What a refresh would change. Nothing is written."""
	plan = service.plan_refresh(db, year, await _source(db, source, file))
	return plan.as_dict()


@router.post("/refresh/apply")
async def apply(
	actor: Admin,
	db: DB,
	year: Annotated[int, Form()],
	source: Annotated[str, Form()] = "time_ir",
	skip: Annotated[list[str] | None, Form()] = None,
	file: Annotated[UploadFile | None, File()] = None,
) -> dict:
	plan = service.plan_refresh(db, year, await _source(db, source, file))
	return service.apply_refresh(db, plan, actor.user_id, set(skip or ()))
