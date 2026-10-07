"""Encryption at rest for the few secrets the app stores (device comm keys).

The key is derived from HOZUR_SECRET_KEY, so a database dump alone does not reveal them."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from hozur.config import get_settings


def _fernet() -> Fernet:
	digest = hashlib.sha256(b"hozur-secrets:" + get_settings().secret_key.encode()).digest()
	return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str | None) -> str | None:
	if not value:
		return None
	return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
	"""None when empty or when the secret key has changed since it was stored."""
	if not token:
		return None
	try:
		return _fernet().decrypt(token.encode()).decode()
	except InvalidToken:
		return None
