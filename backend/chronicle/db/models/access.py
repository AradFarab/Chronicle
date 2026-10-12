"""People who log in, their roles and sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chronicle.db.base import Base, IdMixin, TimestampMixin
from chronicle.db.types import enum_check

# The system admin (مدیر سیستم) does everything an operator used to do. Who is the CEO or a
# manager is not a role: it follows from the designation a person holds.
ADMIN, EMPLOYEE = "admin", "employee"
ROLES = (ADMIN, EMPLOYEE)


class AppUser(IdMixin, TimestampMixin, Base):
	__tablename__ = "app_user"
	__table_args__ = (CheckConstraint("username = lower(username)", name="username_lower"),)

	username: Mapped[str] = mapped_column(String(150), unique=True)
	full_name: Mapped[str] = mapped_column(String(200))
	password_hash: Mapped[str | None] = mapped_column(Text)
	language: Mapped[str] = mapped_column(String(8), server_default="fa")
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
	last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	roles: Mapped[list[UserRole]] = relationship(
		back_populates="user", cascade="all, delete-orphan", lazy="selectin"
	)

	@property
	def role_names(self) -> set[str]:
		return {r.role for r in self.roles}


class UserRole(Base):
	__tablename__ = "user_role"
	__table_args__ = (enum_check("role", ROLES),)

	user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True)
	role: Mapped[str] = mapped_column(String(20), primary_key=True)

	user: Mapped[AppUser] = relationship(back_populates="roles")


class UserSession(Base):
	"""A login. The cookie carries a random token; only its SHA-256 is stored."""

	__tablename__ = "user_session"

	token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
	user_id: Mapped[int] = mapped_column(
		BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), index=True
	)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	user_agent: Mapped[str | None] = mapped_column(Text)
	ip: Mapped[str | None] = mapped_column(String(64))
