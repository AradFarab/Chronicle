"""SMS drivers: importing the package registers them (like chronicle.devices)."""

from chronicle.sms import mock, smsir  # noqa: F401  (register "mock" and "smsir")
from chronicle.sms.base import REGISTRY, SmsDriver, get_driver_class

__all__ = ["REGISTRY", "SmsDriver", "get_driver_class"]
