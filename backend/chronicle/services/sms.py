"""The SMS section of the admin: panel accounts, templates, the send window, opt-outs and the
message history. Sending itself is services/sms_dispatch.py.

A panel account's secret fields are encrypted with the app secret (``enc:v1:...``) and shown
only as a mask; leaving a secret blank keeps the saved one. A template says how an event is
sent through a panel, and is checked when it is saved, not when a message goes out."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from chronicle.db.models import SmsEvent, SmsMessage, SmsOptOut, SmsProviderConfig, SmsTemplate
from chronicle.db.models.sms import BULK, CATEGORIES, MODES, SENDING, SENT, UNKNOWN
from chronicle.i18n import _, translate
from chronicle.jalali.dates import to_ascii_digits
from chronicle.secrets import decrypt, encrypt
from chronicle.services import audit, settings
from chronicle.services.access import Actor, require_admin
from chronicle.services.errors import NotFound, ValidationError
from chronicle.services.resources import flush
from chronicle.sms import events as event_catalog
from chronicle.sms.base import (
	NAMED,
	REGISTRY,
	AmbiguousResult,
	ConfigurationError,
	ProviderError,
	SmsDriver,
	get_driver_class,
)
from chronicle.sms.masking import MASK
from chronicle.sms.numbers import normalize_number

SETTING = "sms"
DEFAULT_SETTINGS: dict[str, Any] = {"window_enabled": True, "window_start_hour": 9, "window_end_hour": 21}
SECRET_PREFIX = "enc:v1:"
SAMPLE = {
	"name": "علی رضایی",
	"month": "مهر 1405",
	"expires": "1405/08/11",
	"link": "/p/example",
	"link_path": "l/AbC12345",
	"date": "1405/07/27",
	"time": "08:00",
	"shift": "صبح",
	"minutes": "15",
	"leave_type": "استحقاقی",
	"status": "تأیید شد",
	"hours": "176:30",
	"code": "123456",
}
# a pattern's variables are the ones the panel's approved text names: the stuck-message review
STUCK_MINUTES = 15


def admin_text(error: Exception, language: str) -> str:
	"""A driver error in the user's language."""
	translated = getattr(error, "translated", None)
	return translated(lambda text: translate(text, language)) if translated else str(error)


# drivers and events ----------------------------------------------------------------------------


def drivers() -> list[dict[str, Any]]:
	return [
		{
			"code": c.code,
			"label": c.label,
			"kind": c.kind,
			"config_schema": c.config_schema,
			"capabilities": sorted(c.capabilities),
			"pattern_schema": c.pattern_schema,
		}
		for c in REGISTRY.values()
	]


def sync_events(session: Session) -> None:
	"""Make the events table match the code (idempotent; the admin's on/off switch is kept)."""
	rows = {e.code: e for e in session.scalars(select(SmsEvent))}
	for event in event_catalog.EVENTS:
		row = rows.get(event.code)
		if row is None:
			session.add(
				SmsEvent(
					code=event.code,
					label=event.label,
					variables=list(event.variables),
					category=event.category,
					bypasses_send_window=event.bypasses_send_window,
				)
			)
			continue
		row.label, row.variables = event.label, list(event.variables)
		row.category, row.bypasses_send_window = event.category, event.bypasses_send_window
	session.flush()


def event_by_code(session: Session, code: str) -> SmsEvent:
	event = session.scalar(select(SmsEvent).where(SmsEvent.code == code))
	if event is None:
		raise NotFound(_("Not found"))
	return event


def list_events(session: Session) -> list[dict[str, Any]]:
	active = {
		(t.event_id, t.provider_code)
		for t in session.scalars(select(SmsTemplate).where(SmsTemplate.is_active))
	}
	return [
		{
			"id": e.id,
			"code": e.code,
			"label": e.label,
			"variables": list(e.variables),
			"category": e.category,
			"bypasses_send_window": e.bypasses_send_window,
			"is_active": e.is_active,
			"providers": sorted(p for event_id, p in active if event_id == e.id),
		}
		for e in session.scalars(select(SmsEvent).order_by(SmsEvent.id))
	]


def set_event_active(session: Session, actor: Actor, code: str, active: bool) -> dict[str, Any]:
	require_admin(actor)
	event = event_by_code(session, code)
	before = {"is_active": event.is_active}
	event.is_active = bool(active)
	audit.log(
		session, "sms_event", event.id, "update", actor.user_id, None, before, {"is_active": event.is_active}
	)
	return next(e for e in list_events(session) if e["code"] == code)


# panel accounts --------------------------------------------------------------------------------


def _plain(driver: type[SmsDriver], stored: dict[str, Any]) -> dict[str, Any]:
	"""The saved configuration with its secrets decrypted (only to talk to the panel)."""
	plain = {}
	for key, spec in driver.config_schema.items():
		value = stored.get(key)
		if spec["type"] == "secret" and value:
			text = str(value)
			token = text[len(SECRET_PREFIX) :] if text.startswith(SECRET_PREFIX) else text
			value = decrypt(token)
			if value is None:
				raise ConfigurationError(_("The saved «{0}» cannot be read; enter it again"), spec["label"])
		if value is not None:
			plain[key] = value
	return plain


def secrets_of(driver: type[SmsDriver], plain: dict[str, Any]) -> list[str]:
	return [
		str(plain[k]) for k, spec in driver.config_schema.items() if spec["type"] == "secret" and plain.get(k)
	]


def driver_for(row: SmsProviderConfig) -> SmsDriver:
	cls = get_driver_class(row.provider_code)
	return cls(_plain(cls, row.config or {}))


def provider_view(code: str, row: SmsProviderConfig | None) -> dict[str, Any]:
	cls = get_driver_class(code)
	stored = (row.config if row else None) or {}
	config = {}
	for key, spec in cls.config_schema.items():
		if spec["type"] == "secret":
			config[key] = MASK if stored.get(key) else ""
		else:
			config[key] = stored.get(key, "")
	return {
		"code": code,
		"label": cls.label,
		"configured": row is not None,
		"config": config,
		"is_primary": bool(row and row.is_primary),
		"is_fallback": bool(row and row.is_fallback),
		"is_active": bool(row and row.is_active),
	}


def list_providers(session: Session) -> list[dict[str, Any]]:
	rows = {r.provider_code: r for r in session.scalars(select(SmsProviderConfig))}
	return [provider_view(code, rows.get(code)) for code in REGISTRY]


def _coerce(spec: dict[str, Any], value: Any) -> Any:
	kind = spec["type"]
	if kind == "boolean":
		return bool(value)
	if kind == "integer":
		try:
			return int(to_ascii_digits(str(value)))
		except ValueError:
			raise ValidationError(_("«{0}» must be a number"), spec["label"]) from None
	return str(value or "").strip()


def save_provider(session: Session, actor: Actor, code: str, values: dict[str, Any]) -> dict[str, Any]:
	require_admin(actor)
	try:
		cls = get_driver_class(code)
	except ConfigurationError as e:
		raise ValidationError(e.template, *e.params) from None
	row = session.scalar(select(SmsProviderConfig).where(SmsProviderConfig.provider_code == code))
	before = provider_view(code, row) if row else None
	stored = dict((row.config if row else None) or {})
	given = values.get("config") or {}
	for key, spec in cls.config_schema.items():
		if key not in given:
			continue
		value = given[key]
		if spec["type"] == "secret":
			text = str(value or "").strip()
			if text and text != MASK:
				stored[key] = SECRET_PREFIX + (encrypt(text) or "")
			continue
		stored[key] = _coerce(spec, value)
	is_primary = bool(values.get("is_primary", row.is_primary if row else False))
	is_fallback = bool(values.get("is_fallback", row.is_fallback if row else False))
	is_active = bool(values.get("is_active", row.is_active if row else True))
	if is_primary and is_fallback:
		raise ValidationError(_("A panel cannot be both the primary and the fallback"))
	try:
		cls(_plain(cls, stored)).validate_config()
	except ConfigurationError as e:
		raise ValidationError(e.template, *e.params) from None
	# one primary and one fallback at a time: the one chosen now takes the role. The others are
	# demoted first, so the unique indexes never see two of them.
	if is_active and is_primary:
		session.execute(
			update(SmsProviderConfig)
			.where(SmsProviderConfig.provider_code != code, SmsProviderConfig.is_primary)
			.values(is_primary=False)
		)
	if is_active and is_fallback:
		session.execute(
			update(SmsProviderConfig)
			.where(SmsProviderConfig.provider_code != code, SmsProviderConfig.is_fallback)
			.values(is_fallback=False)
		)
	new_row = row is None
	if new_row:
		row = SmsProviderConfig(provider_code=code)
	row.config, row.is_primary, row.is_fallback, row.is_active = stored, is_primary, is_fallback, is_active
	flush(session, add=row if new_row else None)
	after = provider_view(code, row)
	audit.log(
		session,
		"sms_provider_config",
		row.id,
		"update" if before else "insert",
		actor.user_id,
		None,
		before,
		after,
	)
	return after


def delete_provider(session: Session, actor: Actor, code: str) -> None:
	require_admin(actor)
	row = session.scalar(select(SmsProviderConfig).where(SmsProviderConfig.provider_code == code))
	if row is None:
		raise NotFound(_("Not found"))
	before = provider_view(code, row)
	audit.log(session, "sms_provider_config", row.id, "delete", actor.user_id, None, before)
	session.delete(row)
	session.flush()


def test_provider(session: Session, actor: Actor, code: str) -> dict[str, Any]:
	require_admin(actor)
	row = session.scalar(select(SmsProviderConfig).where(SmsProviderConfig.provider_code == code))
	if row is None:
		raise NotFound(_("Not found"))
	try:
		driver = driver_for(row)
		driver.validate_config()
		health = driver.test_connection()
	except (ConfigurationError, ProviderError, AmbiguousResult) as e:
		return {"ok": False, "message": admin_text(e, actor.language), "credit": None}
	return {"ok": health.ok, "message": health.message, "credit": health.credit}


# the send window and opt-outs ------------------------------------------------------------------


def get_settings(session: Session) -> dict[str, Any]:
	return {**DEFAULT_SETTINGS, **(settings.get(session, SETTING) or {})}


def save_settings(session: Session, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
	require_admin(actor)
	current = get_settings(session)
	new = dict(current)
	if "window_enabled" in values:
		new["window_enabled"] = bool(values["window_enabled"])
	for key in ("window_start_hour", "window_end_hour"):
		if key in values:
			try:
				new[key] = int(to_ascii_digits(str(values[key])))
			except ValueError:
				raise ValidationError(_("The hours must be numbers")) from None
	if not (0 <= new["window_start_hour"] <= 23 and 1 <= new["window_end_hour"] <= 24):
		raise ValidationError(_("The hours must be between 0 and 24"))
	if new["window_start_hour"] >= new["window_end_hour"]:
		raise ValidationError(_("The window must start before it ends"))
	settings.set_value(session, SETTING, new, actor.user_id)
	audit.log(session, "app_setting", SETTING, "update", actor.user_id, None, current, new)
	return new


def list_opt_outs(session: Session) -> list[dict[str, Any]]:
	return [
		{"id": o.id, "mobile": o.mobile, "category": o.category, "reason": o.reason}
		for o in session.scalars(select(SmsOptOut).order_by(SmsOptOut.id.desc()))
	]


def add_opt_out(session: Session, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
	require_admin(actor)
	mobile = normalize_number(values.get("mobile"))
	if mobile is None:
		raise ValidationError(_("This is not a mobile number"))
	category = values.get("category") or "promotional"
	if category not in CATEGORIES:
		raise ValidationError(_("Unknown category"))
	row = SmsOptOut(mobile=mobile, category=category, reason=(values.get("reason") or "").strip() or None)
	flush(session, add=row)
	audit.log(
		session,
		"sms_opt_out",
		row.id,
		"insert",
		actor.user_id,
		row.reason,
		after={"mobile": mobile, "category": category},
	)
	return {"id": row.id, "mobile": mobile, "category": category, "reason": row.reason}


def remove_opt_out(session: Session, actor: Actor, opt_out_id: int) -> None:
	require_admin(actor)
	row = session.get(SmsOptOut, opt_out_id)
	if row is None:
		raise NotFound(_("Not found"))
	audit.log(
		session,
		"sms_opt_out",
		row.id,
		"delete",
		actor.user_id,
		None,
		{"mobile": row.mobile, "category": row.category},
	)
	session.delete(row)
	session.flush()


# templates -------------------------------------------------------------------------------------


def _check_params(event: SmsEvent, cls: type[SmsDriver], values: dict[str, Any]) -> tuple[Any, list[str]]:
	"""The checked param_map of a pattern template and the event variables it leaves out."""
	style = cls.pattern_schema.get("param_style", NAMED)
	known = set(event.variables)
	mapping = values.get("param_map")
	if style == NAMED:
		if not isinstance(mapping, dict) or not mapping:
			raise ValidationError(_("Map the pattern's variables: this panel names them"))
		cleaned = {}
		for name, variable in mapping.items():
			if not str(name).strip().strip("#"):
				raise ValidationError(_("A pattern variable has no name"))
			cleaned[str(name).strip()] = variable
		used = list(cleaned.values())
	else:
		if not isinstance(mapping, list) or not mapping:
			raise ValidationError(_("List the event variables in the order of the pattern"))
		cleaned = list(mapping)
		used = cleaned
	unknown = sorted({str(v) for v in used if v not in known})
	if unknown:
		raise ValidationError(_("Unknown event variables: {0}"), ", ".join(unknown))
	limit = cls.pattern_schema.get("max_params")
	if limit and len(used) > limit:
		raise ValidationError(_("This panel allows at most {0} pattern variables"), limit)
	links = event_catalog.link_variables(event.variables)
	if links and not {v for pair in links for v in pair} & set(used):
		raise ValidationError(_("Put the link (or its short path) in the pattern"))
	superseded = {source for source, path in links if path in used}
	missing = [v for v in event.variables if v not in used and v not in superseded]
	return cleaned, missing


def validate_template(session: Session, values: dict[str, Any]) -> tuple[SmsEvent, dict[str, Any], list[str]]:
	"""Check a template the way the admin entered it; returns the event, the cleaned fields and
	warnings. Raises ValidationError with the reason: a template that fails here would only fail
	later, when somebody's message goes out."""
	event = (
		session.get(SmsEvent, int(values["event_id"]))
		if values.get("event_id")
		else session.scalar(select(SmsEvent).where(SmsEvent.code == values.get("event")))
	)
	if event is None:
		raise ValidationError(_("Choose the event"))
	provider = values.get("provider_code")
	try:
		cls = get_driver_class(str(provider))
	except ConfigurationError as e:
		raise ValidationError(e.template, *e.params) from None
	mode = values.get("mode")
	if mode not in MODES:
		raise ValidationError(_("Choose how the message is sent"))
	if mode not in cls.capabilities:
		raise ValidationError(_("{0} cannot send in this way"), cls.label)
	cleaned: dict[str, Any] = {
		"event_id": event.id,
		"provider_code": provider,
		"mode": mode,
		"is_active": bool(values.get("is_active", True)),
		"body": None,
		"pattern_code": None,
		"line_number": (str(values.get("line_number") or "").strip() or None),
		"param_map": None,
	}
	warnings: list[str] = []
	if mode == BULK:
		body = str(values.get("body") or "").strip()
		if not body:
			raise ValidationError(_("Write the text of the message"))
		names = re.findall(r"\{(\w+)\}", body)
		unknown = sorted({n for n in names if n not in event.variables})
		if unknown:
			raise ValidationError(_("Unknown fields in the text: {0}"), ", ".join(unknown))
		links = event_catalog.link_variables(event.variables)
		if links and not {v for pair in links for v in pair} & set(names):
			raise ValidationError(_("Put the link (or its short path) in the text"))
		cleaned["body"] = body
		warnings = [v for v in event.variables if v not in names]
	else:
		code = str(values.get("pattern_code") or "").strip()
		if not code:
			raise ValidationError(_("Enter the pattern code"))
		problem = cls(dict()).validate_pattern_code(code)
		if problem:
			raise ValidationError(problem)
		if cls.pattern_schema.get("requires_line_number") and not cleaned["line_number"]:
			raise ValidationError(_("This panel needs the service number for a pattern"))
		cleaned["pattern_code"] = code
		cleaned["param_map"], warnings = _check_params(event, cls, values)
	return event, cleaned, warnings


def template_view(template: SmsTemplate, event: SmsEvent) -> dict[str, Any]:
	return {
		"id": template.id,
		"event": event.code,
		"event_id": event.id,
		"event_label": event.label,
		"provider_code": template.provider_code,
		"mode": template.mode,
		"body": template.body,
		"pattern_code": template.pattern_code,
		"line_number": template.line_number,
		"param_map": template.param_map,
		"is_active": template.is_active,
	}


def list_templates(session: Session) -> list[dict[str, Any]]:
	events = {e.id: e for e in session.scalars(select(SmsEvent))}
	return [
		template_view(t, events[t.event_id])
		for t in session.scalars(
			select(SmsTemplate).order_by(SmsTemplate.event_id, SmsTemplate.provider_code)
		)
	]


def save_template(
	session: Session, actor: Actor, values: dict[str, Any], template_id: int | None = None
) -> dict[str, Any]:
	require_admin(actor)
	event, cleaned, warnings = validate_template(session, values)
	template = session.get(SmsTemplate, template_id) if template_id else None
	if template_id and template is None:
		raise NotFound(_("Not found"))
	before = template_view(template, session.get(SmsEvent, template.event_id)) if template else None
	new_row = template is None
	if new_row:
		template = SmsTemplate(**cleaned)
	else:
		for key, value in cleaned.items():
			setattr(template, key, value)
	flush(session, add=template if new_row else None)
	view = template_view(template, event)
	audit.log(
		session,
		"sms_template",
		template.id,
		"update" if before else "insert",
		actor.user_id,
		None,
		before,
		view,
	)
	return {**view, "warnings": warnings}


def delete_template(session: Session, actor: Actor, template_id: int) -> None:
	require_admin(actor)
	template = session.get(SmsTemplate, template_id)
	if template is None:
		raise NotFound(_("Not found"))
	before = template_view(template, session.get(SmsEvent, template.event_id))
	session.delete(template)
	audit.log(session, "sms_template", template_id, "delete", actor.user_id, None, before)
	session.flush()


def sample_context(event: SmsEvent) -> dict[str, str]:
	return {v: SAMPLE.get(v, f"<{v}>") for v in event.variables}


def render_body(body: str, context: dict[str, Any]) -> str:
	"""Only ``{name}`` is replaced; never a template engine, whose syntax would be a way to run
	code from text an admin (or a name in the database) controls."""
	return re.sub(r"\{(\w+)\}", lambda m: str(context.get(m.group(1), m.group(0))), body)


def build_params(cls: type[SmsDriver], template: SmsTemplate, context: dict[str, Any]) -> Any:
	"""The values for the pattern's variables, in the panel's own naming (see prepare_params)."""
	mapping = template.param_map
	driver = cls({})
	if isinstance(mapping, dict):
		return driver.prepare_params({name: context.get(var, "") for name, var in mapping.items()})
	return driver.prepare_params([context.get(var, "") for var in (mapping or [])])


def preview(session: Session, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
	"""What a template would send for a sample context: the final text of a full-text template, or
	for a pattern exactly the code and parameters that go to the panel (after the panel's naming
	and the half-space replacement), so a wrong name is seen here and not by an employee."""
	require_admin(actor)
	event, cleaned, warnings = validate_template(session, values)
	cls = get_driver_class(cleaned["provider_code"])
	context = {**sample_context(event), **(values.get("context") or {})}
	template = SmsTemplate(**cleaned)
	if cleaned["mode"] == BULK:
		return {"text": render_body(cleaned["body"], context), "request": None, "warnings": warnings}
	return {
		"text": None,
		"request": {
			"pattern_code": cleaned["pattern_code"],
			"line_number": cleaned["line_number"],
			"params": build_params(cls, template, context),
		},
		"warnings": warnings,
	}


# history ---------------------------------------------------------------------------------------


def message_view(m: SmsMessage, event: SmsEvent, full: bool = False) -> dict[str, Any]:
	view = {
		"id": m.id,
		"to": m.to_number,
		"event": event.code,
		"event_label": event.label,
		"provider_code": m.provider_code,
		"status": m.status,
		"attempts": m.attempts,
		"error": m.error,
		"cost": float(m.cost) if m.cost is not None else None,
		"queued_at": m.queued_at,
		"send_after": m.send_after,
		"sent_at": m.sent_at,
	}
	if full:
		view.update(
			provider_message_id=m.provider_message_id,
			context=m.context,
			raw_request=m.raw_request,
			raw_response=m.raw_response,
		)
	return view


def list_messages(
	session: Session,
	actor: Actor,
	status: str | None = None,
	event: str | None = None,
	to: str | None = None,
	limit: int = 100,
	offset: int = 0,
) -> dict[str, Any]:
	require_admin(actor)
	query = select(SmsMessage, SmsEvent).join(SmsEvent, SmsEvent.id == SmsMessage.event_id)
	if status:
		query = query.where(SmsMessage.status == status)
	if event:
		query = query.where(SmsEvent.code == event)
	if to:
		number = normalize_number(to) or to
		query = query.where(SmsMessage.to_number == number)
	total = session.scalar(select(func.count()).select_from(query.subquery()))
	rows = session.execute(query.order_by(SmsMessage.id.desc()).limit(min(limit, 500)).offset(offset)).all()
	return {"total": total, "items": [message_view(m, e) for m, e in rows]}


def get_message(session: Session, actor: Actor, message_id: int) -> dict[str, Any]:
	require_admin(actor)
	row = session.execute(
		select(SmsMessage, SmsEvent)
		.join(SmsEvent, SmsEvent.id == SmsMessage.event_id)
		.where(SmsMessage.id == message_id)
	).first()
	if row is None:
		raise NotFound(_("Not found"))
	return message_view(row[0], row[1], full=True)


def needs_review(session: Session, actor: Actor) -> list[dict[str, Any]]:
	"""Messages whose outcome nobody knows: «unknown», and «sending» for too long (the worker died
	mid-send). The panel's report decides what happened; nothing here retries them."""
	require_admin(actor)
	from datetime import timedelta

	from chronicle.clock import now

	cutoff = now() - timedelta(minutes=STUCK_MINUTES)
	rows = session.execute(
		select(SmsMessage, SmsEvent)
		.join(SmsEvent, SmsEvent.id == SmsMessage.event_id)
		.where(
			(SmsMessage.status == UNKNOWN)
			| ((SmsMessage.status == SENDING) & (SmsMessage.send_after < cutoff))
		)
		.order_by(SmsMessage.id)
	).all()
	return [message_view(m, e) for m, e in rows]


def resolve_message(
	session: Session, actor: Actor, message_id: int, outcome: str, note: str | None
) -> dict[str, Any]:
	"""The admin looked at the panel's report: mark an uncertain message as sent or failed."""
	require_admin(actor)
	if outcome not in (SENT, "failed"):
		raise ValidationError(_("Choose sent or failed"))
	message = session.get(SmsMessage, message_id)
	if message is None:
		raise NotFound(_("Not found"))
	if message.status not in (UNKNOWN, SENDING):
		raise ValidationError(_("Only a message with an unknown outcome can be marked"))
	before = {"status": message.status}
	message.status = outcome
	audit.log(session, "sms_message", message.id, "update", actor.user_id, note, before, {"status": outcome})
	event = session.get(SmsEvent, message.event_id)
	return message_view(message, event)
