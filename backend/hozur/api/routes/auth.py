"""Login and logout. The session lives in PostgreSQL; the cookie only carries a token."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from hozur.api.deps import COOKIE, DB, current_user
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
	login_cookie(response, token)
	return {"ok": True}


def login_cookie(response: Response, token: str) -> None:
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


@router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict:
	users.end_session(db, request.cookies.get(COOKIE))
	response.delete_cookie(COOKIE, path="/")
	return {"ok": True}


class PasswordChange(BaseModel):
	current_password: str
	new_password: str


@router.post("/password")
def change_password(body: PasswordChange, request: Request, response: Response, db: DB) -> dict:
	"""Change your own password; other devices are logged out, this one gets a new session."""
	user = current_user(request, db)
	users.change_own_password(db, user, body.current_password, body.new_password)
	login_cookie(response, users.start_session(db, user, request.headers.get("user-agent")))
	return {"ok": True}
