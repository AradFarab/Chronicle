"""ZKTeco adapter against a fake pyzk device: read-only guard, filtering, direction mapping."""

import sys
import types
from datetime import datetime
from typing import ClassVar

import pytest

from chronicle.devices import REGISTRY, get_adapter_class
from chronicle.devices.base import IN, OUT, UNKNOWN, DeviceConfig, DeviceError
from chronicle.devices.zkteco import ZKTecoAdapter


class FakeAttendance:
	def __init__(self, user_id, timestamp, status=15, punch=0, uid=1):
		self.user_id, self.timestamp, self.status, self.punch, self.uid = (
			user_id,
			timestamp,
			status,
			punch,
			uid,
		)


class FakeUser:
	def __init__(self, user_id, name, card=0):
		self.uid, self.user_id, self.name, self.card, self.privilege = 1, user_id, name, card, 0


class FakeConn:
	users, records, rec_cap = 2, 3, 100000
	calls: ClassVar[list] = []

	def get_attendance(self):
		return [
			FakeAttendance("101", datetime(2026, 10, 5, 7, 55), punch=0),
			FakeAttendance("101", datetime(2026, 10, 6, 7, 58, 11), punch=0),
			FakeAttendance("102", datetime(2026, 10, 6, 17, 0), punch=1, status=1),
			FakeAttendance("103", datetime(2026, 10, 6, 12, 0), punch=255),
		]

	def get_users(self):
		return [FakeUser("101", "Arad ", 123), FakeUser("102", "Sara")]

	def read_sizes(self):
		return True

	def get_device_name(self):
		return "VF600"

	def get_platform(self):
		return "ZMM220_TFT"

	def get_serialnumber(self):
		return "ABC123"

	def get_firmware_version(self):
		return "Ver 6.60"

	def get_time(self):
		return datetime(2026, 10, 6, 8, 0, 5)

	def set_time(self, value):
		FakeConn.calls.append(("set_time", value))

	def clear_attendance(self):
		FakeConn.calls.append(("clear_attendance",))

	def disconnect(self):
		FakeConn.calls.append(("disconnect",))


class FakeSocket:
	def close(self):
		pass


def fake_create_connection(address, timeout=None):
	if address[0] == "10.0.0.98":
		raise TimeoutError("timed out")
	return FakeSocket()


@pytest.fixture(autouse=True)
def fake_pyzk(monkeypatch):
	monkeypatch.setattr("chronicle.devices.zkteco.socket.create_connection", fake_create_connection)
	module = types.ModuleType("zk")

	class ZK:
		def __init__(self, ip, port=4370, timeout=60, password=0, force_udp=False, ommit_ping=False):
			self.args = (ip, port, timeout, password, force_udp, ommit_ping)

		def connect(self):
			if self.args[0] == "10.0.0.99":
				raise OSError("timed out")
			return FakeConn()

	module.ZK = ZK
	monkeypatch.setitem(sys.modules, "zk", module)
	FakeConn.calls = []


def adapter(host="10.0.0.1", comm_key=None):
	return ZKTecoAdapter(DeviceConfig(host=host, port=4370, comm_key=comm_key))


def test_registered():
	assert get_adapter_class("zkteco") is ZKTecoAdapter
	assert {"zkteco", "file_import"} <= set(REGISTRY)


def test_fetch_since_filters_and_maps_direction():
	punches = adapter().fetch_since(datetime(2026, 10, 6))
	assert [(p.device_user_id, p.direction) for p in punches] == [("101", IN), ("103", UNKNOWN), ("102", OUT)]
	assert punches[0].verify_type == "Face" and punches[2].verify_type == "Fingerprint"
	assert punches[0].timestamp == datetime(2026, 10, 6, 7, 58, 11)
	assert ("disconnect",) in FakeConn.calls


def test_fetch_all_when_since_is_none():
	assert len(adapter().fetch_since(None)) == 4


def test_users_and_health():
	users = adapter().list_users()
	assert [(u.device_user_id, u.name, u.card) for u in users] == [
		("101", "Arad", "123"),
		("102", "Sara", None),
	]
	health = adapter().health()
	assert health.model == "VF600 / ZMM220_TFT" and health.record_count == 3
	assert health.device_time == datetime(2026, 10, 6, 8, 0, 5)


def test_logs_are_never_cleared():
	ad = adapter()
	with pytest.raises(PermissionError), ad._connect() as conn:
		conn.clear_attendance()
	assert ("clear_attendance",) not in FakeConn.calls


def test_set_time_only_through_sync_time():
	ad = adapter()
	with pytest.raises(PermissionError), ad._connect() as conn:
		conn.set_time(datetime(2026, 1, 1))
	ad.sync_time(datetime(2026, 10, 6, 8, 0))
	assert ("set_time", datetime(2026, 10, 6, 8, 0)) in FakeConn.calls


def test_connection_errors_become_device_errors():
	with pytest.raises(DeviceError, match="Cannot connect"):
		adapter(host="10.0.0.99").health()
	with pytest.raises(DeviceError, match="Cannot connect"):
		adapter(host="10.0.0.98").health()  # fails at the quick probe
	with pytest.raises(DeviceError, match="IP address"):
		adapter(host=None).health()
	with pytest.raises(DeviceError, match="comm key"):
		adapter(comm_key="abc").health()
