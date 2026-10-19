"""Uploaded files: bytes on disk under the data directory, metadata in stored_file."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from chronicle.clock import now
from chronicle.config import get_settings
from chronicle.db.models import StoredFile


def _root() -> Path:
	return get_settings().files_dir


def save(
	session: Session, content: bytes, filename: str, content_type: str | None, user_id: int | None
) -> StoredFile:
	stamp = now()
	relative = f"{stamp:%Y/%m}/{uuid.uuid4().hex}{Path(filename).suffix.lower()[:10]}"
	path = _root() / relative
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_bytes(content)
	row = StoredFile(
		filename=Path(filename).name[:255] or "file",
		content_type=content_type,
		size=len(content),
		sha256=hashlib.sha256(content).hexdigest(),
		storage_path=relative,
		created_by_id=user_id,
	)
	session.add(row)
	session.flush()
	return row


def read(row: StoredFile) -> bytes:
	return (_root() / row.storage_path).read_bytes()


def delete(session: Session, row: StoredFile) -> None:
	"""Remove a stored file's record and its bytes (nothing may reference it any more)."""
	path = _root() / row.storage_path
	session.delete(row)
	session.flush()
	path.unlink(missing_ok=True)
