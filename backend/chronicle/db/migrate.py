"""Run Alembic from code, so an installed package needs no alembic.ini."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config(database_url: str | None = None, connection: Connection | None = None) -> Config:
	config = Config()
	config.set_main_option("script_location", str(MIGRATIONS))
	if database_url:
		config.attributes["database_url"] = database_url
	if connection is not None:
		config.attributes["connection"] = connection
	return config


def upgrade(
	database_url: str | None = None, connection: Connection | None = None, revision: str = "head"
) -> None:
	command.upgrade(alembic_config(database_url, connection), revision)
