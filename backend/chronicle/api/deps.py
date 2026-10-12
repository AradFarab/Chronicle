"""Request-scoped dependencies: database session, current user, CSRF guard."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from chronicle.clock import today_jalali
from chronicle.db.models import AppUser
from chronicle.db.session import session_factory
from chronicle.i18n import _
from chronicle.services import access, users
from chronicle.services.errors import ChronicleError, PermissionDenied

COOKIE = "chronicle_session"
CSRF_HEADER = "x-chronicle"  # any value; a cross-site form or image cannot set a custom header
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class NotLoggedIn(ChronicleError):
	status_code = 401


def get_db(request: Request) -> Iterator[Session]:
	factory = getattr(request.app.state, "session_factory", None) or session_factory()
	session = factory()
	try:
		yield session
		session.commit()
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()


def csrf_guard(request: Request) -> None:
	if request.method not in SAFE_METHODS and CSRF_HEADER not in request.headers:
		raise PermissionDenied(_("Missing request header"))


DB = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: DB) -> AppUser:
	user = users.user_for_token(db, request.cookies.get(COOKIE))
	if user is None:
		raise NotLoggedIn(_("Please log in"))
	request.state.language = user.language
	return user


def current_actor(user: Annotated[AppUser, Depends(current_user)], db: DB) -> access.Actor:
	return access.actor_for(db, user)


def require_admin(actor: Annotated[access.Actor, Depends(current_actor)]) -> access.Actor:
	if not actor.is_admin:
		raise PermissionDenied(_("Not permitted"))
	return actor


Actor = Annotated[access.Actor, Depends(current_actor)]
Admin = Annotated[access.Actor, Depends(require_admin)]


def today() -> str:
	return today_jalali()


Today = Annotated[str, Depends(today)]
