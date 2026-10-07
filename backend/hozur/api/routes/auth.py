"""Login and logout. The session lives in PostgreSQL; the cookie only carries a token."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from hozur.api.deps import COOKIE, DB
from hozur.config import get_settings
from hozur.i18n import _
from hozur.services import users
from hozur.services.errors import HozurError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginFailed(HozurError):
	status_code = 401


class Login(BaseModel):
	username: str
	password: str


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: DB) -> dict:
	user = users.authenticate(db, body.username, body.password)
	if user is None:
		raise LoginFailed(_("Wrong username or password"))
	token = users.start_session(
		db, user, request.headers.get("user-agent"), request.client.host if request.client else None
	)
	settings = get_settings()
	response.set_cookie(
		COOKIE,
		token,
		max_age=settings.session_days * 86400,
		httponly=True,
		secure=settings.cookie_secure,
		samesite="lax",
		path="/",
	)
	return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict:
	users.end_session(db, request.cookies.get(COOKIE))
	response.delete_cookie(COOKIE, path="/")
	return {"ok": True}
