"""Engine and sessions. One SQLAlchemy session per request or job."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from chronicle.config import get_settings


@cache
def get_engine() -> Engine:
	return create_engine(get_settings().database_url, pool_pre_ping=True)


@cache
def session_factory() -> sessionmaker[Session]:
	return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
	"""A session that commits on success and rolls back on error (jobs, CLI)."""
	session = session_factory()()
	try:
		yield session
		session.commit()
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()
