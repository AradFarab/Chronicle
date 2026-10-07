"""Users, passwords (Argon2) and login sessions (a random cookie token; only its hash is stored)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from hozur.config import get_settings
from hozur.db.models import AppUser, UserRole, UserSession
from hozur.db.models.access import ROLES
from hozur.i18n import _
from hozur.services.errors import ValidationError

_hasher = PasswordHasher()
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
	if len(password or "") < MIN_PASSWORD:
		raise ValidationError(_("The password must be at least {0} characters"), MIN_PASSWORD)
	return _hasher.hash(password)


def verify_password(user: AppUser, password: str) -> bool:
	if not user.password_hash:
		return False
	try:
		return _hasher.verify(user.password_hash, password)
	except (VerifyMismatchError, VerificationError, InvalidHashError):
		return False


def create_user(
	session: Session,
	username: str,
	full_name: str,
	password: str | None,
	roles: list[str] | tuple[str, ...] = (),
) -> AppUser:
	username = (username or "").strip().lower()
	if not username:
		raise ValidationError(_("Enter a username"))
	if session.scalar(select(AppUser.id).where(AppUser.username == username)):
		raise ValidationError(_("The username {0} is taken"), username)
	unknown = [r for r in roles if r not in ROLES]
	if unknown:
		raise ValidationError(_("Unknown role {0}"), ", ".join(unknown))
	user = AppUser(username=username, full_name=full_name or username)
	if password:
		user.password_hash = hash_password(password)
	user.roles = [UserRole(role=r) for r in dict.fromkeys(roles)]
	session.add(user)
	session.flush()
	return user


def set_roles(session: Session, user: AppUser, roles: list[str]) -> None:
	unknown = [r for r in roles if r not in ROLES]
	if unknown:
		raise ValidationError(_("Unknown role {0}"), ", ".join(unknown))
	user.roles = [UserRole(role=r) for r in dict.fromkeys(roles)]
	session.flush()


def _token_hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def authenticate(session: Session, username: str, password: str) -> AppUser | None:
	user = session.scalar(select(AppUser).where(AppUser.username == (username or "").strip().lower()))
	if user is None or not user.is_active:
		_hasher.hash("timing")  # same cost whether or not the user exists
		return None
	if not verify_password(user, password):
		return None
	if _hasher.check_needs_rehash(user.password_hash):
		user.password_hash = _hasher.hash(password)
	user.last_login_at = datetime.now(UTC)
	return user


def start_session(
	session: Session, user: AppUser, user_agent: str | None = None, ip: str | None = None
) -> str:
	token = secrets.token_urlsafe(32)
	session.add(
		UserSession(
			token_hash=_token_hash(token),
			user_id=user.id,
			expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_days),
			user_agent=(user_agent or "")[:500],
			ip=ip,
		)
	)
	session.flush()
	return token


def user_for_token(session: Session, token: str | None) -> AppUser | None:
	if not token:
		return None
	row = session.get(UserSession, _token_hash(token))
	now = datetime.now(UTC)
	if row is None or row.expires_at <= now:
		return None
	user = session.get(AppUser, row.user_id)
	if user is None or not user.is_active:
		return None
	if (now - row.last_seen_at) > timedelta(minutes=5):
		row.last_seen_at = now
	return user


def end_session(session: Session, token: str | None) -> None:
	if token:
		session.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))


def end_all_sessions(session: Session, user_id: int) -> None:
	session.execute(delete(UserSession).where(UserSession.user_id == user_id))
