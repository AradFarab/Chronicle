"""Sending an SMS: the one gate the rest of the app uses (`dispatch`) and the sender behind it.

Rules that make this safe:

- Sending never happens in a web request: `dispatch` writes the message and a job in one
  transaction, and the worker sends.
- Every message has a row, also the one that was never sent (opt-out, no panel, a failure).
- A message is sent at most once. Before any network call the worker claims it with a
  conditional UPDATE (queued -> sending); a second worker finds nothing to claim. When the
  outcome is unknown (the panel did not answer, an unexpected error) the message becomes
  «unknown» and is never retried or sent through another panel: a double SMS is worse than a
  missing one, and the admin decides from the panel's report.
- The primary panel is tried first, then the fallback; a panel's definite refusal moves on.
"""

from __future__ import annotations

import logging
import random
import secrets as token_source
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from chronicle.clock import now
from chronicle.db.models import (
	Job,
	ShortLink,
	SmsEvent,
	SmsMessage,
	SmsOptOut,
	SmsProviderConfig,
	SmsTemplate,
)
from chronicle.db.models.sms import BULK, FAILED, PROMOTIONAL, QUEUED, SENDING, SENT, SKIPPED, UNKNOWN
from chronicle.i18n import DEFAULT_LANGUAGE, _, translate
from chronicle.services import settings
from chronicle.services.errors import ChronicleError
from chronicle.services.sms import (
	DEFAULT_SETTINGS,
	SETTING,
	build_params,
	driver_for,
	render_body,
	secrets_of,
)
from chronicle.sms import events as event_catalog
from chronicle.sms.base import (
	AmbiguousResult,
	ConfigurationError,
	ProviderError,
	SendResult,
	get_driver_class,
)
from chronicle.sms.masking import mask_text
from chronicle.sms.numbers import normalize_number

log = logging.getLogger("chronicle.sms")

SMS_SEND = "sms_send"  # job kind; payload {"message_id": int}
MAX_ATTEMPTS = 5
BACKOFF_CAP = 1800  # seconds
SHORT_LINK_DAYS = 14
# letters and digits that cannot be mistaken for each other (no 0/O, 1/l/I)
CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"


class DispatchError(ChronicleError):
	"""The message cannot even be recorded: a bad number or an unknown event."""


# short links -----------------------------------------------------------------------------------


def make_short_link(session: Session, target: str) -> str:
	"""«l/<code>» for the path of `target`. Only the path (and query) is kept: whatever domain was
	given is thrown away, so the link can never leave the site."""
	parts = urlsplit(target)
	path = parts.path + (f"?{parts.query}" if parts.query else "")
	# a backslash or a control character can make a browser read «/\\host» as «//host»
	if "\\" in target or any(ord(c) < 32 for c in target):
		raise DispatchError(_("A link must be a path on this site"))
	if not path.startswith("/") or path.startswith("//"):
		raise DispatchError(_("A link must be a path on this site"))
	for _attempt in range(10):
		code = "".join(token_source.choice(CODE_ALPHABET) for _i in range(8))
		if session.scalar(select(ShortLink.id).where(ShortLink.code == code)) is None:
			break
	session.add(
		ShortLink(code=code, target_path=path[:500], expires_at=now() + timedelta(days=SHORT_LINK_DAYS))
	)
	session.flush()
	return f"l/{code}"


def resolve_short_link(session: Session, code: str) -> str | None:
	"""The path behind a code, or None for an unknown or expired one (the same answer for both,
	so the existence of a code cannot be probed)."""
	if not code or len(code) > 16:
		return None
	row = session.scalar(select(ShortLink).where(ShortLink.code == code))
	if row is None or row.expires_at <= now():
		return None
	return row.target_path


# the send window -------------------------------------------------------------------------------


def window_settings(session: Session) -> dict[str, Any]:
	return {**DEFAULT_SETTINGS, **(settings.get(session, SETTING) or {})}


def next_send_time(at: datetime, window: dict[str, Any], bypass: bool = False) -> datetime:
	"""`at` when it is inside the window (or the window is off, or the event bypasses it), else
	the start of the next window."""
	if bypass or not window.get("window_enabled", True):
		return at
	start, end = int(window["window_start_hour"]), int(window["window_end_hour"])
	if start <= at.hour < end:
		return at
	opens = at.replace(hour=start, minute=0, second=0, microsecond=0)
	return opens if at.hour < start else opens + timedelta(days=1)


# dispatch --------------------------------------------------------------------------------------


def _enqueue(session: Session, message: SmsMessage, run_after: datetime) -> None:
	session.add(
		Job(
			kind=SMS_SEND,
			payload={"message_id": message.id},
			dedup_key=f"sms:{message.id}",
			run_after=run_after,
			max_attempts=2,
		)
	)
	session.flush()


def dispatch(
	session: Session,
	event_code: str,
	to: object,
	context: dict[str, Any] | None = None,
	*,
	entity_key: str | None = None,
	enqueue: bool = True,
) -> SmsMessage:
	"""Record a message for an event and queue it. With an `entity_key` the same event is
	recorded once per entity (the database enforces it): asking again returns the first message.
	`enqueue=False` records it without a job or the send window (the caller sends it at once:
	the settings page's test button).

	Raises DispatchError for a number that is not a mobile or an event that is unknown or off."""
	number = normalize_number(to)
	if number is None:
		raise DispatchError(_("«{0}» is not a mobile number"), str(to))
	event = session.scalar(select(SmsEvent).where(SmsEvent.code == event_code))
	if event is None or not event.is_active:
		raise DispatchError(_("The SMS event «{0}» is unknown or switched off"), event_code)
	if entity_key:
		existing = session.scalar(
			select(SmsMessage).where(SmsMessage.event_id == event.id, SmsMessage.entity_key == entity_key)
		)
		if existing is not None:
			return existing
	context = dict(context or {})
	for source, path in event_catalog.link_variables(list(event.variables)):
		if context.get(source):
			context[path] = make_short_link(session, str(context[source]))
			del context[source]  # only the short path is kept with the message
	at = now()
	message = SmsMessage(
		to_number=number,
		event_id=event.id,
		context=context,
		entity_key=entity_key,
		queued_at=at,
		send_after=at
		if not enqueue
		else next_send_time(at, window_settings(session), event.bypasses_send_window),
	)
	if event.category == PROMOTIONAL and session.scalar(
		select(SmsOptOut.id).where(SmsOptOut.mobile == number, SmsOptOut.category == PROMOTIONAL)
	):
		message.status = SKIPPED
		message.error = translate(_("The number opted out of promotional messages"), DEFAULT_LANGUAGE)
		session.add(message)
		session.flush()
		return message
	session.add(message)
	session.flush()
	if enqueue:
		_enqueue(session, message, message.send_after)
	return message


# the sender ------------------------------------------------------------------------------------


def _providers(session: Session) -> list[SmsProviderConfig]:
	rows = list(session.scalars(select(SmsProviderConfig).where(SmsProviderConfig.is_active)))
	rows.sort(key=lambda r: (not r.is_primary, not r.is_fallback, r.id))
	return [r for r in rows if r.is_primary or r.is_fallback]


def _template(session: Session, event_id: int, provider_code: str) -> SmsTemplate | None:
	return session.scalar(
		select(SmsTemplate).where(
			SmsTemplate.event_id == event_id,
			SmsTemplate.provider_code == provider_code,
			SmsTemplate.is_active,
		)
	)


def _text(error: Exception) -> str:
	translated = getattr(error, "translated", None)
	return translated(lambda t: translate(t, DEFAULT_LANGUAGE)) if translated else str(error)[:300]


def readiness(session: Session, event_code: str) -> str | None:
	"""Why an event cannot be sent now (in English, to translate), or None when a primary panel
	has an active template for it."""
	event = session.scalar(select(SmsEvent).where(SmsEvent.code == event_code))
	if event is None or not event.is_active:
		return _("The SMS event is switched off")
	providers = _providers(session)
	if not providers:
		return _("No SMS panel is set up: add one in the SMS section")
	if not any(_template(session, event.id, p.provider_code) for p in providers):
		return _("Create an SMS template for this event in the SMS section")
	return None


def _try(session: Session, row: SmsProviderConfig, template: SmsTemplate, message: SmsMessage) -> SendResult:
	driver = driver_for(row)
	driver.validate_config()
	if template.mode == BULK:
		return driver.send_bulk(
			message.to_number, render_body(template.body or "", message.context), template.line_number
		)
	cls = get_driver_class(row.provider_code)
	params = build_params(cls, template, message.context)
	return driver.send_pattern(message.to_number, template.pattern_code or "", params, template.line_number)


def send_message(session: Session, message_id: int) -> str:
	"""Send one queued message (the worker's job; also the test-send button). Returns the
	message's status after this attempt. Commits after each state change so that a crash
	afterwards leaves a truthful state."""
	claimed = session.execute(
		update(SmsMessage)
		.where(SmsMessage.id == message_id, SmsMessage.status == QUEUED)
		.values(status=SENDING, attempts=SmsMessage.attempts + 1)
		.returning(SmsMessage.id)
	).first()
	if claimed is None:
		return "not_claimed"  # sent, failed or taken by another worker
	session.commit()  # «sending» is now visible: nobody else will touch it
	message = session.get(SmsMessage, message_id)
	session.refresh(message)
	errors: list[str] = []
	any_retryable = False
	tried = False
	try:
		for row in _providers(session):
			template = _template(session, message.event_id, row.provider_code)
			if template is None:
				continue
			tried = True
			try:
				result = _try(session, row, template, message)
			except ConfigurationError as e:
				errors.append(f"{row.provider_code}: {_text(e)}")
				continue
			except ProviderError as e:
				cls = get_driver_class(row.provider_code)
				secrets = secrets_of(cls, _safe_plain(row, cls))
				message.raw_response = mask_text(e.raw, secrets)
				errors.append(f"{row.provider_code}: {_text(e)}")
				any_retryable = any_retryable or e.retryable
				continue
			cls = get_driver_class(row.provider_code)
			secrets = secrets_of(cls, _safe_plain(row, cls))
			message.provider_code = row.provider_code
			message.provider_message_id = result.provider_message_id
			message.cost = result.cost
			message.raw_request = mask_text(result.raw_request, secrets)
			message.raw_response = mask_text(result.raw_response, secrets)
			message.status, message.sent_at, message.error = SENT, now(), None
			session.commit()
			return SENT
	except AmbiguousResult as e:
		message.status, message.error = UNKNOWN, _text(e)
		session.commit()
		return UNKNOWN
	except Exception as e:  # the outcome is unknown: it may have gone out
		log.exception("sms %s: unexpected error while sending", message_id)
		message.status, message.error = UNKNOWN, f"{type(e).__name__}: {str(e)[:200]}"
		session.commit()
		return UNKNOWN
	if not tried:
		errors.append(
			translate(_("No SMS panel with a template for this event is available"), DEFAULT_LANGUAGE)
		)
	message.error = " | ".join(errors)
	if any_retryable and message.attempts < MAX_ATTEMPTS:
		delay = min(60 * 2 ** (message.attempts - 1), BACKOFF_CAP)
		message.status = QUEUED
		message.send_after = now() + timedelta(seconds=delay * random.uniform(0.8, 1.2))
		_enqueue_retry(session, message)
		session.commit()
		return QUEUED
	message.status = FAILED
	session.commit()
	return FAILED


def _safe_plain(row: SmsProviderConfig, cls) -> dict[str, Any]:
	from chronicle.services.sms import _plain

	try:
		return _plain(cls, row.config or {})
	except ConfigurationError:
		return {}


def _enqueue_retry(session: Session, message: SmsMessage) -> None:
	# the finished job may still be «running» when this runs: dedup only looks at queued jobs
	session.add(
		Job(
			kind=SMS_SEND,
			payload={"message_id": message.id},
			dedup_key=f"sms:{message.id}:{message.attempts}",
			run_after=message.send_after,
			max_attempts=2,
		)
	)
	session.flush()


def preview_event(session: Session, event_code: str, context: dict[str, Any]) -> dict[str, Any] | None:
	"""What the first panel with a template for the event would send for this context (without
	sending): the text of a full-text template, or the pattern code and parameters exactly as
	the panel gets them."""
	event = session.scalar(select(SmsEvent).where(SmsEvent.code == event_code))
	if event is None:
		return None
	for row in _providers(session):
		template = _template(session, event.id, row.provider_code)
		if template is None:
			continue
		if template.mode == BULK:
			return {
				"provider": row.provider_code,
				"text": render_body(template.body or "", context),
				"request": None,
			}
		cls = get_driver_class(row.provider_code)
		return {
			"provider": row.provider_code,
			"text": None,
			"request": {
				"pattern_code": template.pattern_code,
				"line_number": template.line_number,
				"params": build_params(cls, template, context),
			},
		}
	return None


def test_send(session: Session, event_code: str, to: object, context: dict[str, Any]) -> SmsMessage:
	"""Send a real message now, for the settings page's test button: no job, no send window."""
	message = dispatch(session, event_code, to, context, enqueue=False)
	if message.status == QUEUED:
		session.commit()
		send_message(session, message.id)
		session.refresh(message)
	return message
