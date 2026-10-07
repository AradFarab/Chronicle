"""Attendance devices: the adapter interface (base) and the built-in adapters.

Importing this package registers the built-in adapters. Ingestion into the database lives
in hozur.devices.service.
"""

from hozur.devices import file_import, zkteco
from hozur.devices.base import REGISTRY, DeviceAdapter, DeviceError, get_adapter_class, register

__all__ = [
	"REGISTRY",
	"DeviceAdapter",
	"DeviceError",
	"file_import",
	"get_adapter_class",
	"register",
	"zkteco",
]
