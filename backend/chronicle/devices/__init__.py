"""Attendance devices: the adapter interface (base) and the built-in adapters.

Importing this package registers the built-in adapters. Ingestion into the database lives
in chronicle.services.devices.
"""

from chronicle.devices import file_import, zkteco
from chronicle.devices.base import REGISTRY, DeviceAdapter, DeviceError, get_adapter_class, register

__all__ = [
	"REGISTRY",
	"DeviceAdapter",
	"DeviceError",
	"file_import",
	"get_adapter_class",
	"register",
	"zkteco",
]
