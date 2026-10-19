"""SMS gateway interface. Pure Python: no database or web imports.

Every SMS provider implements SmsGateway and registers itself with @register, as device
adapters do (CLAUDE.md rule 5): the provider, its key and its sender line are configuration in
the PWA, and the app only talks to this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


def _(text: str) -> str:
	"""Marks a message for translation extraction; the caller translates it."""
	return text


@dataclass(frozen=True)
class SmsConfig:
	api_key: str
	line_number: str = ""  # the sender line (شماره خط) of the account
	timeout: int = 20
	options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SmsMessage:
	mobile: str  # 09xxxxxxxxx
	text: str


@dataclass(frozen=True)
class SmsResult:
	mobile: str
	ok: bool
	provider_id: str | None = None  # the provider's id of the message, for delivery questions
	error: str | None = None


@dataclass(frozen=True)
class SmsHealth:
	ok: bool
	message: str = ""
	credit: float | None = None


class SmsError(Exception):
	"""A provider could not be reached or refused the request. The message is an English
	template with {0}-style arguments, so the caller can translate it."""

	def __init__(self, message: str, *params):
		super().__init__(message.format(*params) if params else message)
		self.template = message
		self.params = params

	def translated(self, translate) -> str:
		return translate(self.template).format(*self.params)


class SmsGateway(ABC):
	code: str = ""  # stored in the sms setting
	label: str = ""
	batch_size: int = 100  # messages per request

	def __init__(self, config: SmsConfig):
		self.config = config

	@abstractmethod
	def send(self, messages: list[SmsMessage]) -> list[SmsResult]:
		"""Send up to batch_size messages (each its own text); one result per message, in order.
		Raises SmsError when the whole request failed."""

	@abstractmethod
	def health(self) -> SmsHealth:
		"""Check the key (and report the credit where the provider says it). Raises SmsError when the
		provider cannot be reached or refuses the key."""


REGISTRY: dict[str, type[SmsGateway]] = {}


def register(cls: type[SmsGateway]) -> type[SmsGateway]:
	if not cls.code:
		raise ValueError(f"{cls.__name__} has no code")
	REGISTRY[cls.code] = cls
	return cls


def get_gateway_class(code: str) -> type[SmsGateway]:
	try:
		return REGISTRY[code]
	except KeyError:
		raise SmsError(_("No SMS gateway registered for {0}"), code) from None
