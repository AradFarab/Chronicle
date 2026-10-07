# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import ipaddress
import re

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.devices import REGISTRY
from hozur.devices.service import load_adapters

HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


class AttendanceDevice(Document):
	def validate(self):
		load_adapters()
		adapter = REGISTRY.get(self.adapter_type)
		if not adapter:
			frappe.throw(_("Unknown device type {0}").format(self.adapter_type))
		if not adapter.network:
			return
		self.host = (self.host or "").strip()
		if not self.host:
			frappe.throw(_("Enter the IP address of the device"))
		try:
			ipaddress.ip_address(self.host)
		except ValueError:
			if not HOSTNAME_RE.match(self.host):
				frappe.throw(_("{0} is not a valid IP address or host name").format(self.host))
		if not 1 <= (self.port or 0) <= 65535:
			frappe.throw(_("Port must be between 1 and 65535"))
		if (self.polling_interval_minutes or 0) < 1:
			frappe.throw(_("Read interval must be at least one minute"))
		if (self.timeout_seconds or 0) < 1:
			self.timeout_seconds = 10
