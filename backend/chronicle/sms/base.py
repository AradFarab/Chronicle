"""SMS driver interface. Pure Python: no database or web imports.

The core never talks to a panel: it dispatches an event and a driver does the panel's part. A
driver is registered with @register and chosen by its **code**, never by a module path read from
the database. Three things differ between panels and the interface keeps them apart:

- ``bulk``: a recipient and a full text (an advertising line);
- ``pattern`` with **named** variables (sms.ir, Kavenegar): a pattern code and a dictionary;
- ``pattern`` with **positional** variables (Melipayamak): a pattern code and an ordered list.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

BULK, PATTERN = "bulk", "pattern"
NAMED, POSITIONAL = "named", "positional"
ZWNJ = "‌"  # half-space: many panels reject a plain space inside a pattern parameter


def _(text: str) -> str:
	"""Marks a message for translation extraction; the caller translates it."""
	return text


class _Translatable(Exception):
	"""An English template with {0}-style arguments, so the caller can translate it."""

	def __init__(self, message: str, *params):
		super().__init__(message.format(*params) if params else message)
		self.template = message
		self.params = params

	def translated(self, translate) -> str:
		return translate(self.template).format(*self.params)


class ConfigurationError(_Translatable):
	"""The panel's configuration is incomplete: found before any network call."""


class ProviderError(_Translatable):
	"""The panel refused the request. `retryable` says whether trying again can help (a network
	error or a 5xx/429 answer yes, a revoked key or a wrong parameter no); `raw` is the panel's
	answer for the message history."""

	def __init__(self, message: str, *params, retryable: bool = False, raw: Any = None):
		super().__init__(message, *params)
		self.retryable = retryable
		self.raw = raw


class AmbiguousResult(_Translatable):
	"""The request may have reached the panel (the answer timed out or the connection broke
	halfway): the message might have been sent. Never retried, never sent through another panel."""


@dataclass(frozen=True)
class SendResult:
	"""One accepted send. The request and the answer are kept on purpose: without them "why did
	this SMS not arrive" cannot be answered."""

	ok: bool = True
	provider_message_id: str | None = None
	cost: float | None = None
	raw_request: dict | None = None
	raw_response: Any = None


@dataclass(frozen=True)
class Health:
	ok: bool
	message: str = ""
	credit: float | None = None


def clean_param(value: object) -> str:
	"""A pattern parameter for the panel: every run of whitespace becomes a half-space."""
	return re.sub(r"\s+", ZWNJ, str(value if value is not None else "").strip())


class SmsDriver(ABC):
	code: str = ""  # stored with the account and the templates, e.g. "smsir"
	label: str = ""
	kind: str = "sms"
	# What the account form asks for: {"api_key": {"type": "secret", "label": "...", "required": True}}.
	# Types: string, secret, boolean, integer.
	config_schema: ClassVar[dict[str, dict[str, Any]]] = {}
	capabilities: frozenset[str] = frozenset({BULK, PATTERN})
	# requires_line_number: a pattern also needs the panel's service number;
	# param_style: named or positional; max_params: variables a pattern may carry
	pattern_schema: ClassVar[dict[str, Any]] = {
		"requires_line_number": False,
		"param_style": NAMED,
		"max_params": 10,
	}

	def __init__(self, config: dict[str, Any]):
		self.config = config

	def validate_config(self) -> None:
		"""Required fields must not be empty (checked before any network call)."""
		for key, spec in self.config_schema.items():
			if spec.get("required") and not str(self.config.get(key) or "").strip():
				raise ConfigurationError(_("The setting «{0}» is required"), spec.get("label", key))

	def validate_pattern_code(self, code: str) -> str | None:
		"""An English message when the panel cannot use this pattern code, else None."""
		return None

	@abstractmethod
	def test_connection(self) -> Health:
		"""The settings page's «Test connection»; raises ProviderError/ConfigurationError."""

	def prepare_params(self, params: dict[str, str] | list[str]) -> dict[str, str] | list[str]:
		"""The pattern parameters exactly as the panel gets them: a named panel wants the bare
		variable name (no surrounding ``#``) and no plain space in a value."""
		if isinstance(params, dict):
			return {str(k).strip().strip("#"): clean_param(v) for k, v in params.items()}
		return [clean_param(v) for v in params]

	def send_bulk(self, to: str, text: str, line_number: str | None = None) -> SendResult:
		raise ProviderError(_("{0} cannot send a full text"), self.label)

	def send_pattern(
		self, to: str, pattern_code: str, params: dict[str, str] | list[str], line_number: str | None = None
	) -> SendResult:
		raise ProviderError(_("{0} cannot send a pattern"), self.label)

	def get_credit(self) -> float | None:
		return None

	def check_status(self, provider_message_id: str) -> str:
		"""The delivery status the panel reports: delivered / failed / unknown."""
		return "unknown"


REGISTRY: dict[str, type[SmsDriver]] = {}


def register(cls: type[SmsDriver]) -> type[SmsDriver]:
	if not cls.code:
		raise ValueError(f"{cls.__name__} has no code")
	if cls.code in REGISTRY:
		raise ValueError(f"SMS driver code {cls.code!r} is registered twice")
	REGISTRY[cls.code] = cls
	return cls


def get_driver_class(code: str) -> type[SmsDriver]:
	try:
		return REGISTRY[code]
	except KeyError:
		raise ConfigurationError(_("No SMS driver is registered for «{0}»"), code) from None
