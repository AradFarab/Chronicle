"""Attendance devices: adapter interface (base), built-in adapters, Frappe service (service)."""

# Importing the built-in adapters registers them.
from hozur.devices import file_import, zkteco
from hozur.devices.base import REGISTRY, DeviceAdapter, DeviceError, get_adapter_class, register
