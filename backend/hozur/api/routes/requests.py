"""Requests (leave, mission, overtime, manual entry) and approvals."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from hozur.api.deps import DB, Actor, Today
from hozur.api.views import request_view
from hozur.db.models import LeaveType
from hozur.services import access, leave, requests, suggestions

router = APIRouter(prefix="/api", tags=["requests"])
Kind = Literal["leave", "mission", "overtime", "correction"]


class Decision(BaseModel):
	comment: str | None = None


class Cancellation(BaseModel):
	reason: str | None = None


@router.get("/requests")
def list_requests(
	actor: Actor,
	db: DB,
	today: Today,
	employee_id: int | None = None,
	status: str | None = None,
	limit: int = Query(50, le=500),
) -> list[dict]:
	return [
		request_view(db, r, actor, today)
		for r in requests.list_requests(db, actor, today, employee_id, status, limit)
	]


@router.post("/requests/{kind}")
def submit(kind: Kind, values: dict[str, Any], actor: Actor, db: DB, today: Today) -> dict:
	return request_view(db, requests.submit(db, actor, kind, values, today), actor, today)


@router.get("/requests/{request_id}")
def get_request(request_id: int, actor: Actor, db: DB, today: Today) -> dict:
	return request_view(db, requests.get(db, actor, request_id, today), actor, today)


@router.post("/requests/{request_id}/approve")
def approve(request_id: int, body: Decision, actor: Actor, db: DB, today: Today) -> dict:
	return request_view(
		db, requests.act(db, actor, request_id, requests.APPROVE, body.comment, today), actor, today
	)


@router.post("/requests/{request_id}/reject")
def reject(request_id: int, body: Decision, actor: Actor, db: DB, today: Today) -> dict:
	return request_view(
		db, requests.act(db, actor, request_id, requests.REJECT, body.comment, today), actor, today
	)


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: int, body: Cancellation, actor: Actor, db: DB, today: Today) -> dict:
	return request_view(db, requests.cancel(db, actor, request_id, body.reason, today), actor, today)


@router.get("/inbox")
def inbox(actor: Actor, db: DB, today: Today) -> list[dict]:
	return [request_view(db, r, actor, today) for r in requests.inbox(db, actor, today)]


@router.get("/leave-types")
def leave_types(actor: Actor, db: DB) -> list[dict]:
	return [
		{
			"id": t.id,
			"name": t.name,
			"category": t.category,
			"allow_hourly": t.allow_hourly,
			"is_paid": t.is_paid,
		}
		for t in db.scalars(select(LeaveType).order_by(LeaveType.id))
	]


@router.get("/leave/balance")
def leave_balance(actor: Actor, db: DB, today: Today, employee_id: int | None = None) -> dict:
	employee_id = employee_id or actor.employee_id
	if not employee_id:
		return {"leave_type_id": None, "balance": None}
	access.assert_can_see(db, actor, employee_id, today)
	earned = leave.earned_leave_type(db)
	if earned is None:
		return {"leave_type_id": None, "balance": None}
	return {"leave_type_id": earned.id, "balance": float(leave.balance(db, employee_id, earned.id))}


@router.get("/suggestions")
def list_suggestions(actor: Actor, db: DB, employee_id: int | None = None) -> list[dict]:
	"""Requests the calculation proposes from the punches and the work pattern."""
	return [suggestions.view(s) for s in suggestions.open_for(db, actor, employee_id)]


@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: int, actor: Actor, db: DB) -> dict:
	return suggestions.view(suggestions.dismiss(db, actor, suggestion_id))
