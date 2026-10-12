"""Users, passwords (Argon2) and login sessions (a random cookie token; only its hash is stored)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from chronicle.config import get_settings
from chronicle.db.models import AppUser, UserRole, UserSession
from chronicle.db.models.access import ADMIN, ROLES
from chronicle.i18n import _
from chronicle.services.errors import ValidationError

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
	require_password: bool = False,
) -> AppUser:
	"""A login. Employees always get a password at creation; an account without one (a CLI
	admin created for someone else to set up) cannot log in until a password is set."""
	if require_password and not password:
		raise ValidationError(_("Enter a password"))
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


# administration (admins) -------------------------------------------------------------------------


def user_view(user: AppUser) -> dict:
	return {
		"id": user.id,
		"username": user.username,
		"full_name": user.full_name,
		"language": user.language,
		"is_active": user.is_active,
		"roles": sorted(user.role_names),
		"last_login_at": user.last_login_at,
	}


def update_user(session: Session, user: AppUser, values: dict, admin_id: int | None) -> AppUser:
	"""Name, language, active flag and roles. Deactivating ends the user's sessions; the last
	active admin cannot be removed."""
	from chronicle.services import audit

	before = user_view(user)
	if "full_name" in values:
		user.full_name = (values["full_name"] or "").strip() or user.username
	if "language" in values:
		user.language = values["language"] or "fa"
	if "is_active" in values:
		user.is_active = bool(values["is_active"])
	if "roles" in values:
		set_roles(session, user, list(values["roles"] or []))
	session.flush()
	if ADMIN in before["roles"] and (not user.is_active or ADMIN not in user.role_names):
		admins = session.scalar(
			select(func.count())
			.select_from(AppUser)
			.join(UserRole, UserRole.user_id == AppUser.id)
			.where(UserRole.role == ADMIN, AppUser.is_active)
		)
		if not admins:
			raise ValidationError(_("At least one active admin is needed"))
	if not user.is_active:
		end_all_sessions(session, user.id)
	after = user_view(user)
	before.pop("last_login_at"), after.pop("last_login_at")
	audit.log(session, "app_user", user.id, "update", admin_id, values.get("reason"), before, after)
	return user


def set_password(session: Session, user: AppUser, password: str, by_user_id: int | None) -> None:
	"""A new password ends every other session of the user."""
	from chronicle.services import audit

	user.password_hash = hash_password(password)
	end_all_sessions(session, user.id)
	audit.log(
		session, "app_user", user.id, "update", by_user_id, "password changed", after={"password": "***"}
	)


def change_own_password(session: Session, user: AppUser, current: str, new: str) -> None:
	if not verify_password(user, current):
		raise ValidationError(_("The current password is wrong"))
	set_password(session, user, new, user.id)
