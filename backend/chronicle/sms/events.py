"""The events that can send an SMS. Fixed in code and synced into the database on install: a
template says *how* an event is sent, never *when*: the trigger is business code.

A variable ending in ``_path`` (``link_path``) is made from the full address in the variable
before it (``link``): it becomes a short ``l/<code>`` path, because the panel only accepts a
fixed domain in the approved text and a short parameter (see services/sms_dispatch.py).
"""

from __future__ import annotations

from dataclasses import dataclass

TRANSACTIONAL, PROMOTIONAL = "transactional", "promotional"


@dataclass(frozen=True)
class Event:
	code: str
	label: str
	variables: tuple[str, ...]
	category: str = TRANSACTIONAL
	bypasses_send_window: bool = False


EVENTS: tuple[Event, ...] = (
	Event("payslip_link", "لینک فیش حقوقی", ("name", "month", "expires", "link", "link_path")),
	Event("otp", "رمز یک‌بارمصرف ورود", ("code",), bypasses_send_window=True),
	Event("user_invite", "دعوت کارمند یا مدیر", ("name", "link", "link_path")),
	Event("password_reset", "بازیابی رمز", ("link", "link_path"), bypasses_send_window=True),
	Event("shift_reminder", "یادآوری شیفت فردا", ("name", "date", "time", "shift")),
	Event("missed_check_in", "ورود ثبت نشده", ("name", "date", "time")),
	Event("missed_check_out", "خروج ثبت نشده", ("name", "date")),
	Event("late_arrival", "اطلاع تأخیر به مدیر", ("name", "date", "minutes")),
	Event("absence_notice", "اطلاع غیبت به مدیر", ("name", "date")),
	Event("leave_requested", "درخواست مرخصی برای مدیر", ("name", "date", "leave_type")),
	Event("leave_approved", "تأیید مرخصی", ("name", "date", "leave_type")),
	Event("leave_rejected", "رد مرخصی", ("name", "date", "leave_type")),
	Event("correction_decided", "نتیجهٔ درخواست اصلاح تردد", ("name", "date", "status")),
	Event("monthly_summary", "خلاصهٔ ماهانهٔ حضور", ("name", "month", "hours", "link", "link_path")),
	Event("birthday", "تبریک تولد", ("name",), category=PROMOTIONAL),
)
BY_CODE = {e.code: e for e in EVENTS}


def link_variables(variables: tuple[str, ...] | list[str]) -> list[tuple[str, str]]:
	"""[(source variable, path variable)] for the event's ``x`` / ``x_path`` pairs."""
	return [
		(v[: -len("_path")], v) for v in variables if v.endswith("_path") and v[: -len("_path")] in variables
	]
