"""Iranian mobile numbers."""

from __future__ import annotations

import re

_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MOBILE = re.compile(r"^09\d{9}$")


def normalize_number(value: object) -> str | None:
	"""«+98 912 123 4567», «0098912…», «98912…», «912…» and «0912…» all become «09121234567»;
	None when the result is not a mobile number."""
	digits = re.sub(r"\D", "", str(value or "").translate(_TO_ASCII))
	for prefix in ("0098", "98", "0"):
		if digits.startswith(prefix):
			digits = digits[len(prefix) :]
			break
	number = "0" + digits
	return number if MOBILE.match(number) else None
