"""SMS gateways: importing the package registers the adapters (like chronicle.devices)."""

from chronicle.sms import smsir  # noqa: F401  (registers "smsir")
from chronicle.sms.base import REGISTRY, SmsGateway, get_gateway_class

__all__ = ["REGISTRY", "SmsGateway", "get_gateway_class"]
