"""Settings from the environment (prefix CHRONICLE_). Nothing secret has a production default.

Until 0.3.0 the app was called hozur and its variables HOZUR_*; those are still read when the
CHRONICLE_ one is not set, so an existing installation keeps working after the rename."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
	model_config = SettingsConfigDict(env_prefix="CHRONICLE_", env_file=".env", extra="ignore")

	database_url: str = "postgresql+psycopg://hozur:hozur@localhost:5432/hozur"
	# Signs nothing by itself; derives the key that encrypts device comm keys at rest.
	secret_key: str = DEV_SECRET
	data_dir: Path = Path("data")
	timezone: str = "Asia/Tehran"
	session_days: int = 30
	cookie_secure: bool = False
	# Built PWA to serve at / (frontend/dist); empty to serve only the API.
	frontend_dist: Path | None = None

	@property
	def files_dir(self) -> Path:
		return self.data_dir / "files"


LEGACY_PREFIX, PREFIX = "HOZUR_", "CHRONICLE_"


def _adopt_legacy_environment() -> None:
	for key, value in list(os.environ.items()):
		if key.startswith(LEGACY_PREFIX):
			os.environ.setdefault(PREFIX + key.removeprefix(LEGACY_PREFIX), value)


@cache
def get_settings() -> Settings:
	_adopt_legacy_environment()
	return Settings()
