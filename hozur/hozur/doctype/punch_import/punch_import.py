# Copyright (c) 2026, Arad Farab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hozur.devices.base import DeviceError
from hozur.devices.file_import import parse_rows, read_table
from hozur.devices.service import ingest
from hozur.utils import now_jalali


class PunchImport(Document):
	@frappe.whitelist()
	def run_import(self):
		"""Read the attached file with the template and store its punches. Safe to run again:
		punches already stored are skipped."""
		frappe.only_for(["System Manager", "Hozur Operator"])
		self.check_permission("write")
		template = frappe.get_doc("Punch Import Template", self.template).as_dict()
		file_doc = frappe.get_doc("File", {"file_url": self.file})
		try:
			rows = read_table(_bytes(file_doc), template.file_format, template.delimiter, template.encoding)
			result = parse_rows(rows, template)
		except DeviceError as e:
			message = e.translated(_)
			self.db_set({"status": "Failed", "error_log": message, "error_count": 1})
			frappe.throw(message)
		items = [
			{
				"device_user_id": p.device_user_id,
				"jdate": p.jdate,
				"time": p.time,
				"device_timestamp": p.device_timestamp,
				"reported_direction": p.direction,
				"raw": p.raw,
			}
			for p in result.punches
		]
		device = frappe.get_doc("Attendance Device", self.device)
		stats = ingest(device, items, source="File Import", punch_import=self.name)
		jdate, time = now_jalali()
		self.db_set(
			{
				"status": "Imported",
				"imported_at": f"{jdate} {time}",
				"total_rows": len(result.punches),
				"created_count": stats["created"],
				"existing_count": stats["existing"],
				"duplicate_count": stats["duplicates"],
				"error_count": len(result.errors),
				"error_log": "\n".join(result.errors[:500]) or None,
			}
		)
		return stats


def _bytes(file_doc) -> bytes:
	"""Raw bytes: the template decides the encoding (UTF-8 or Windows-1256)."""
	with open(file_doc.get_full_path(), "rb") as f:
		return f.read()
