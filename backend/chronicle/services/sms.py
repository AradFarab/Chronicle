"""The SMS connection (provider, API key, sender line): configured in the PWA like a device.

The key is encrypted with the app secret (chronicle.secrets) and never leaves the server: the
API only says whether one is set."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from chronicle import sms
from chronicle.i18n import DEFAULT_LANGUAGE, _, translate
from chronicle.jalali.dates import to_ascii_digits
from chronicle.secrets import decrypt, encrypt
from chronicle.services import audit, settings
from chronicle.services.errors import ValidationError
from chronicle.sms.base import REGISTRY, SmsConfig, SmsError, SmsGateway

SETTING = "sms"
DEFAULTS: dict[str, Any] = {"provider": "smsir", "line_number": "", "api_key_encrypted": None}


class SmsFailure(ValidationError):
	"""The provider could not be reached or refused the request; the message is for the system admin."""

	status_code = 502

	@classmethod
	def wrap(cls, error: SmsError) -> SmsFailure:
		return cls(error.template, *error.params)


def admin_text(error: SmsError) -> str:
	"""Stored messages (the error of a failed SMS) are in the company language."""
	return error.translated(lambda text: translate(text, DEFAULT_LANGUAGE))


def _stored(session: Session) -> dict[str, Any]:
	return {**DEFAULTS, **(settings.get(session, SETTING) or {})}


def _public(stored: dict[str, Any]) -> dict[str, Any]:
	return {
		"provider": stored["provider"],
		"line_number": stored["line_number"],
		"has_key": bool(stored["api_key_encrypted"]),
	}


def view(session: Session) -> dict[str, Any]:
	return {
		**_public(_stored(session)),
		"providers": [{"code": c.code, "label": c.label} for c in REGISTRY.values()],
	}


def save(session: Session, values: dict[str, Any], user_id: int | None) -> dict[str, Any]:
	current = _stored(session)
	provider = values.get("provider") or current["provider"]
	if provider not in REGISTRY:
		raise ValidationError(_("No SMS gateway registered for {0}"), provider)
	line = to_ascii_digits(str(values.get("line_number", current["line_number"]) or "")).strip()
	if line and not line.isdigit():
		raise ValidationError(_("The sender line number must be a number"))
	key = str(values.get("api_key") or "").strip()
	new = {
		"provider": provider,
		"line_number": line,
		"api_key_encrypted": encrypt(key) if key else current["api_key_encrypted"],
	}
	settings.set_value(session, SETTING, new, user_id)
	audit.log(session, "app_setting", SETTING, "update", user_id, None, _public(current), _public(new))
	return view(session)


def gateway(session: Session) -> SmsGateway:
	"""The configured gateway; a ValidationError says what is missing."""
	stored = _stored(session)
	key = decrypt(stored["api_key_encrypted"])
	if not key:
		raise ValidationError(_("Enter the SMS API key first"))
	if not stored["line_number"]:
		raise ValidationError(_("Enter the SMS sender line number first"))
	try:
		cls = sms.get_gateway_class(stored["provider"])
	except SmsError as e:
		raise SmsFailure.wrap(e) from None
	return cls(SmsConfig(api_key=key, line_number=stored["line_number"]))


def check(session: Session) -> dict[str, Any]:
	"""Test the connection: does the provider accept the key, and what credit is left."""
	try:
		health = gateway(session).health()
	except SmsError as e:
		return {"ok": False, "message": admin_text(e), "credit": None}
	return {"ok": health.ok, "message": health.message, "credit": health.credit}
