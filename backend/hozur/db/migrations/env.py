"""Alembic environment: the URL comes from the app settings, the metadata from the models."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from hozur.config import get_settings
from hozur.db import models  # noqa: F401  (registers every table)
from hozur.db.base import Base

config = context.config
if config.config_file_name is not None:
	fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
	return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
	context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
	with context.begin_transaction():
		context.run_migrations()


def run_migrations_online() -> None:
	connection = config.attributes.get("connection")
	if connection is not None:
		context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
		with context.begin_transaction():
			context.run_migrations()
		return
	engine = create_engine(_url(), poolclass=pool.NullPool)
	with engine.connect() as conn:
		context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
		with context.begin_transaction():
			context.run_migrations()


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
