"""ZKTeco adapter (pyzk, TCP/UDP 4370). Also works for brands that speak the ZK protocol (e.g. eSSL).

The connection is wrapped so that only read commands and, on explicit request, set_time
can reach the device. Logs are never cleared.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from datetime import datetime

from chronicle.devices.base import (
	IN,
	OUT,
	UNKNOWN,
	DeviceAdapter,
	DeviceError,
	DeviceHealth,
	DevicePunch,
	DeviceUser,
	_,
	register,
)

READ_METHODS = frozenset(
	{
		"disconnect",
		"get_firmware_version",
		"get_serialnumber",
		"get_platform",
		"get_device_name",
		"get_mac",
		"get_time",
		"read_sizes",
		"get_users",
		"get_attendance",
	}
)
WRITE_METHODS = frozenset({"set_time"})  # allowed only through sync_time()

# Attendance state ("punch" in pyzk) -> direction.
STATE_DIRECTION = {0: IN, 1: OUT, 2: OUT, 3: IN, 4: IN, 5: OUT}
VERIFY_TYPES = {0: "Password", 1: "Fingerprint", 2: "Card", 3: "Password", 4: "Card", 15: "Face", 25: "Palm"}


class _GuardedConnection:
	def __init__(self, conn, allow_write: bool = False):
		self._conn = conn
		self._allowed = READ_METHODS | (WRITE_METHODS if allow_write else frozenset())

	def __getattr__(self, name):
		value = getattr(self._conn, name)
		if callable(value) and name not in self._allowed:
			raise PermissionError(f"chronicle never calls {name}() on a device")
		return value


@register
class ZKTecoAdapter(DeviceAdapter):
	code = "zkteco"
	label = "ZKTeco (TCP 4370)"
	network = True

	def _zk(self):
		from zk import ZK

		try:
			password = int(self.config.comm_key or 0)
		except ValueError:
			raise DeviceError(_("The ZKTeco comm key must be a number")) from None
		return ZK(
			self.config.host,
			port=int(self.config.port or 4370),
			timeout=int(self.config.timeout or 10),
			password=password,
			force_udp=bool(self.config.use_udp),
			ommit_ping=True,
		)

	@contextmanager
	def _connect(self, allow_write: bool = False):
		if not self.config.host:
			raise DeviceError(_("Device IP address is not set"))
		port = int(self.config.port or 4370)
		if not self.config.use_udp:
			# One quick probe: pyzk retries several times before giving up on a dead address.
			try:
				socket.create_connection(
					(self.config.host, port), timeout=int(self.config.timeout or 10)
				).close()
			except OSError as e:
				raise DeviceError(_("Cannot connect to {0}:{1}: {2}"), self.config.host, port, e) from e
		try:
			conn = self._zk().connect()
		except Exception as e:
			raise DeviceError(_("Cannot connect to {0}:{1}: {2}"), self.config.host, port, e) from e
		guarded = _GuardedConnection(conn, allow_write)
		try:
			yield guarded
		except PermissionError:
			raise
		except Exception as e:
			raise DeviceError(_("Device error: {0}"), e) from e
		finally:
			try:
				conn.disconnect()
			except Exception:
				pass

	def fetch_since(self, since: datetime | None) -> list[DevicePunch]:
		with self._connect() as conn:
			records = conn.get_attendance()
		punches = []
		for a in records:
			if since is not None and a.timestamp < since:
				continue
			punches.append(
				DevicePunch(
					device_user_id=str(a.user_id),
					timestamp=a.timestamp,
					direction=STATE_DIRECTION.get(a.punch, UNKNOWN),
					verify_type=VERIFY_TYPES.get(a.status, str(a.status)),
					raw={
						"uid": a.uid,
						"user_id": str(a.user_id),
						"status": a.status,
						"punch": a.punch,
						"timestamp": a.timestamp.isoformat(sep=" "),
					},
				)
			)
		punches.sort(key=lambda p: p.timestamp)
		return punches

	def list_users(self) -> list[DeviceUser]:
		with self._connect() as conn:
			users = conn.get_users()
		return [
			DeviceUser(
				device_user_id=str(u.user_id),
				name=(u.name or "").strip(),
				card=str(u.card) if u.card else None,
				privilege=str(u.privilege),
			)
			for u in users
		]

	def sync_time(self, now: datetime) -> None:
		with self._connect(allow_write=True) as conn:
			conn.set_time(now)

	def health(self) -> DeviceHealth:
		with self._connect() as conn:
			conn.read_sizes()
			name, platform = conn.get_device_name(), conn.get_platform()
			return DeviceHealth(
				ok=True,
				message="",
				model=" / ".join(x for x in (name, platform) if x),
				serial_number=conn.get_serialnumber(),
				firmware=conn.get_firmware_version(),
				user_count=conn.users,
				record_count=conn.records,
				record_capacity=conn.rec_cap,
				device_time=conn.get_time(),
			)
