"""Backups (پشتیبان‌گیری): the whole database and the uploaded files in one .zip.

A backup is ``database.dump`` (pg_dump, custom format), the ``files/`` folder and a
``manifest.json`` (when, which schema revision, made by whom or by the schedule). They live in
``<data dir>/backups`` on the company's own server; the system admin downloads them from the
PWA to keep a copy elsewhere. The schedule (an automatic backup every night, keeping the last N)
is an app setting. Restoring replaces everything, so it is a command on the server
(`chronicle backup restore FILE`), never a button in the PWA.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from chronicle.clock import now
from chronicle.config import get_settings
from chronicle.i18n import _
from chronicle.jalali.dates import to_jalali
from chronicle.services import settings
from chronicle.services.errors import NotFound, ValidationError

SETTING = "backup"
DEFAULTS = {"enabled": True, "hour": 2, "keep": 14}
NAME_RE = re.compile(r"^(?:chronicle|hozur)-(auto|manual)-\d{8}-\d{4,6}\.zip$")  # hozur-: before 0.3.0
MANIFEST, DUMP = "manifest.json", "database.dump"


class BackupError(ValidationError):
	pass


def folder() -> Path:
	path = get_settings().data_dir / "backups"
	path.mkdir(parents=True, exist_ok=True)
	return path


def schedule(session: Session) -> dict[str, Any]:
	return {**DEFAULTS, **(settings.get(session, SETTING) or {})}


def set_schedule(session: Session, values: dict[str, Any], user_id: int | None) -> dict[str, Any]:
	current = schedule(session)
	enabled = bool(values.get("enabled", current["enabled"]))
	try:
		hour = int(values.get("hour", current["hour"]))
		keep = int(values.get("keep", current["keep"]))
	except (TypeError, ValueError):
		raise ValidationError(_("Enter whole numbers for the hour and the number of backups")) from None
	if not 0 <= hour <= 23:
		raise ValidationError(_("The hour must be between 0 and 23"))
	if not 1 <= keep <= 365:
		raise ValidationError(_("Keep between 1 and 365 automatic backups"))
	value = {"enabled": enabled, "hour": hour, "keep": keep}
	settings.set_value(session, SETTING, value, user_id)
	return value


def _libpq() -> tuple[list[str], dict[str, str]]:
	"""Connection arguments for pg_dump / pg_restore; the password goes in the environment."""
	url = make_url(get_settings().database_url)
	args = [
		"--host",
		url.host or "localhost",
		"--port",
		str(url.port or 5432),
		"--dbname",
		url.database or "",
	]
	if url.username:
		args += ["--username", url.username]
	env = {**os.environ}
	if url.password:
		env["PGPASSWORD"] = str(url.password)
	return args, env


def tools_available() -> bool:
	return shutil.which("pg_dump") is not None and shutil.which("pg_restore") is not None


@dataclass
class Backup:
	name: str
	size: int
	created_at: datetime
	automatic: bool

	def as_dict(self) -> dict[str, Any]:
		day, clock = to_jalali(self.created_at.replace(tzinfo=None))
		return {
			"name": self.name,
			"size": self.size,
			"automatic": self.automatic,
			"jdate": day,
			"time": clock[:5],
			"created_at": self.created_at.isoformat(),
		}


def _of(path: Path) -> Backup:
	stat = path.stat()
	zone = now().tzinfo
	return Backup(
		path.name,
		stat.st_size,
		datetime.fromtimestamp(stat.st_mtime, zone),
		"-auto-" in path.name,
	)


def list_backups() -> list[Backup]:
	return sorted(
		(_of(p) for p in folder().iterdir() if NAME_RE.match(p.name)),
		key=lambda b: b.created_at,
		reverse=True,
	)


def path_of(name: str) -> Path:
	if not NAME_RE.match(name or ""):
		raise NotFound(_("Not found"))
	path = folder() / name
	if not path.is_file():
		raise NotFound(_("Not found"))
	return path


def create(session: Session, automatic: bool = False, user_id: int | None = None) -> Backup:
	"""pg_dump plus the uploaded files, zipped. Written to a temporary name and renamed, so a
	half-written backup is never listed."""
	if not tools_available():
		raise BackupError(_("pg_dump is not installed on the server"))
	revision = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
	day, clock = to_jalali(now().replace(tzinfo=None))
	stamp = f"{day.replace('/', '')}-{clock.replace(':', '')}"  # Jalali, e.g. 14050719-020000
	name = f"chronicle-{'auto' if automatic else 'manual'}-{stamp}.zip"
	target = folder() / name
	args, env = _libpq()
	with tempfile.TemporaryDirectory(dir=folder()) as work:
		dump = Path(work) / DUMP
		done = subprocess.run(
			["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump), *args],
			env=env,
			capture_output=True,
			text=True,
			timeout=3600,
		)
		if done.returncode != 0:
			raise BackupError(_("The backup failed: {0}"), (done.stderr or "").strip()[-500:])
		partial = Path(work) / (name + ".part")
		with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
			z.write(dump, DUMP)
			files = get_settings().files_dir
			if files.is_dir():
				for path in sorted(files.rglob("*")):
					if path.is_file():
						z.write(path, Path("files") / path.relative_to(files))
			z.writestr(
				MANIFEST,
				json.dumps(
					{
						"app": "chronicle",
						"schema_revision": revision,
						"created_at": now().isoformat(),
						"automatic": automatic,
						"created_by_user_id": user_id,
					},
					ensure_ascii=False,
				),
			)
		partial.replace(target)
	return _of(target)


def delete(name: str) -> None:
	path_of(name).unlink()


def prune(keep: int) -> list[str]:
	"""Keep the newest `keep` automatic backups; manual ones are only removed by hand."""
	removed = []
	for b in [b for b in list_backups() if b.automatic][keep:]:
		(folder() / b.name).unlink(missing_ok=True)
		removed.append(b.name)
	return removed


def restore(path: Path) -> dict[str, Any]:
	"""Replace the database and the files with a backup. Stop the server and the worker first."""
	if not tools_available():
		raise BackupError(_("pg_restore is not installed on the server"))
	args, env = _libpq()
	with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as work:
		names = set(z.namelist())
		if DUMP not in names or MANIFEST not in names:
			raise BackupError(_("This is not a Chronicle backup"))
		manifest = json.loads(z.read(MANIFEST))
		z.extract(DUMP, work)
		done = subprocess.run(
			[
				"pg_restore",
				"--clean",
				"--if-exists",
				"--no-owner",
				"--no-privileges",
				"--single-transaction",
				*args,
				str(Path(work) / DUMP),
			],
			env=env,
			capture_output=True,
			text=True,
			timeout=3600,
		)
		if done.returncode != 0:
			raise BackupError(_("The restore failed: {0}"), (done.stderr or "").strip()[-500:])
		files = get_settings().files_dir
		members = [n for n in names if n.startswith("files/") and not n.endswith("/")]
		if members:
			if files.exists():
				shutil.rmtree(files)
			files.mkdir(parents=True, exist_ok=True)
			for member in members:
				relative = Path(member).relative_to("files")
				if ".." in relative.parts:
					continue
				destination = files / relative
				destination.parent.mkdir(parents=True, exist_ok=True)
				with z.open(member) as src, open(destination, "wb") as dst:
					shutil.copyfileobj(src, dst)
	return manifest


def due(session: Session, today: str, hour: int) -> bool:
	"""Whether tonight's automatic backup should be taken now."""
	plan = schedule(session)
	if not plan["enabled"] or hour < plan["hour"]:
		return False
	stamp = f"chronicle-auto-{today.replace('/', '')}-"
	return not any(b.name.startswith(stamp) for b in list_backups())
