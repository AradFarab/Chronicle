"""Device adapter interface (CLAUDE.md rule 5). Pure Python: no database or web imports.

Every attendance source implements DeviceAdapter and registers itself with @register.
The app (chronicle.services.devices) only talks to this interface, so supporting a new
device brand means adding one adapter; configuring another device of a supported type is
pure data on the device settings.

Adapters must never clear or modify the logs stored on a device.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

IN, OUT, UNKNOWN = "in", "out", "unknown"


@dataclass(frozen=True)
class DeviceConfig:
	host: str | None = None
	port: int | None = None
	comm_key: str | None = None
	timeout: int = 10
	use_udp: bool = False
	options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DevicePunch:
	device_user_id: str
	timestamp: datetime  # device wall clock (Asia/Tehran), untouched
	direction: str = UNKNOWN  # what the device reported: In / Out / Unknown
	verify_type: str | None = None  # face, finger, card, password... as reported
	raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceUser:
	device_user_id: str
	name: str = ""
	card: str | None = None
	privilege: str | None = None


@dataclass(frozen=True)
class DeviceHealth:
	ok: bool
	message: str = ""
	model: str | None = None
	serial_number: str | None = None
	firmware: str | None = None
	user_count: int | None = None
	record_count: int | None = None
	record_capacity: int | None = None
	device_time: datetime | None = None


def _(text: str) -> str:
	"""Marks a message for translation extraction; the caller translates it ."""
	return text


class DeviceError(Exception):
	"""Raised by adapters for connection/protocol problems; the message is shown to the operator.
	It is an English template with {0}-style arguments, so the caller can translate it."""

	def __init__(self, message: str, *params):
		super().__init__(message.format(*params) if params else message)
		self.template = message
		self.params = params

	def translated(self, translate) -> str:
		return translate(self.template).format(*self.params)


class DeviceAdapter(ABC):
	code: str = ""  # stored in Attendance Device.adapter_type
	label: str = ""
	network: bool = True  # False for file-based sources (nothing to poll)

	def __init__(self, config: DeviceConfig):
		self.config = config

	@abstractmethod
	def fetch_since(self, since: datetime | None) -> list[DevicePunch]:
		"""Punches with timestamp >= since (all when None), oldest first."""

	@abstractmethod
	def list_users(self) -> list[DeviceUser]: ...

	@abstractmethod
	def sync_time(self, now: datetime) -> None:
		"""Set the device clock. Only on an explicit operator action."""

	@abstractmethod
	def health(self) -> DeviceHealth: ...


REGISTRY: dict[str, type[DeviceAdapter]] = {}


def register(cls: type[DeviceAdapter]) -> type[DeviceAdapter]:
	if not cls.code:
		raise ValueError(f"{cls.__name__} has no code")
	REGISTRY[cls.code] = cls
	return cls


def get_adapter_class(code: str) -> type[DeviceAdapter]:
	try:
		return REGISTRY[code]
	except KeyError:
		raise DeviceError(_("No adapter registered for device type {0}"), code) from None
