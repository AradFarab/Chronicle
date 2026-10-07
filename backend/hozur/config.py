"""Settings from the environment (prefix HOZUR_). Nothing secret has a production default."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
	model_config = SettingsConfigDict(env_prefix="HOZUR_", env_file=".env", extra="ignore")

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


@cache
def get_settings() -> Settings:
	return Settings()
