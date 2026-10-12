"""Engine inputs and outputs. Pure Python: no database or web imports.

Times inside the engine are minutes from the start of the attendance day (0-1440, and
beyond 1440 for the early hours of the next day in overnight shifts). Punches come in
seconds so that rounding can be done in the worker's favour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Day types (Calendar Day / chronicle.jalali.calendar.resolve_day_type)
WORKDAY, FRIDAY, OFFICIAL_HOLIDAY, COMPANY_HOLIDAY = (
	"workday",
	"friday",
	"official_holiday",
	"company_holiday",
)

# Overtime kinds (Overtime Request)
NORMAL, EXCEPTIONAL, EMERGENCY = "normal", "exceptional", "emergency"

# Day status (Daily Attendance.status)
PRESENT, ABSENT, INCOMPLETE, LEAVE, MISSION, HOLIDAY, REST, OFF = (
	"present",
	"absent",
	"incomplete",
	"leave",
	"mission",
	"holiday",
	"rest_day",
	"not_scheduled",
)


@dataclass(frozen=True)
class Shift:
	name: str
	start: int  # minute of day; for flexible shifts the earliest allowed start
	end: int  # minute of day, > start (add 1440 for shifts ending after midnight)
	# Breaks (lunch, prayer, tea) as (start, end) minutes: never working time (Article 51).
	breaks: tuple[tuple[int, int], ...] = ()
	break_minutes: int = 0  # break taken without punching, for flexible shifts without break times
	grace_late: int = 0  # arriving up to this late is forgiven; beyond it the whole delay counts
	grace_early: int = 0  # leaving up to this early is forgiven; beyond it the whole time counts
	overtime_after: int = 0  # work after the end up to this long is ignored; beyond it all counts
	# Where extra work may become overtime (with approval). Empty = anywhere outside the shift.
	overtime_windows: tuple[tuple[int, int], ...] = ()
	flexible: bool = False
	latest_start: int | None = None  # flexible: latest allowed start
	required_minutes: int | None = None  # flexible: daily work required

	@property
	def break_list(self) -> list[tuple[int, int]]:
		return [(a, b) for a, b in self.breaks if b > a]

	@property
	def scheduled_minutes(self) -> int:
		"""Required work: the shift minus its break."""
		if self.flexible and self.required_minutes is not None:
			return self.required_minutes
		inside = sum(max(0, min(b, self.end) - max(a, self.start)) for a, b in self.break_list)
		brk = inside if self.break_list else self.break_minutes
		return max(0, self.end - self.start - brk)


@dataclass(frozen=True)
class Punch:
	second: int  # seconds from the start of the attendance day (may exceed 86400)
	direction: str = "unknown"


@dataclass(frozen=True)
class Absence:
	"""An approved leave or mission. Daily when start/end are None, else an hourly window."""

	kind: str  # "leave" or "mission"
	type: str  # leave type key (the app passes the leave_type id as text) or "mission"
	start: int | None = None
	end: int | None = None
	paid: bool = True  # unpaid leave does not count as work time

	@property
	def daily(self) -> bool:
		return self.start is None or self.end is None


@dataclass(frozen=True)
class OvertimeApproval:
	minutes: int
	kind: str = NORMAL  # Normal / Exceptional (agreed beyond the daily cap) / Emergency (Article 60)


@dataclass(frozen=True)
class EmployeeFlags:
	juvenile: bool = False  # Articles 83, 84
	hard_harmful: bool = False  # Articles 52, 61
	nursing: bool = False  # Article 78
	rotating: bool = False  # on a rotating shift pattern: shift premium instead of night premium (Article 58)
	standing_overtime_consent: bool = False  # written general consent to overtime (Article 59)


@dataclass(frozen=True)
class Day:
	jdate: str
	weekday: int  # 0 = Saturday ... 6 = Friday
	day_type: str  # after work-location/province/company holidays are applied
	rest_day: bool = False  # the employee's weekly rest day (Article 62)


@dataclass
class DailyResult:
	jdate: str
	status: str
	shift: str | None = None
	required_minutes: int = 0
	worked_minutes: int = 0  # all work time (presence minus breaks)
	credited_minutes: int = 0  # work + paid leave + mission + nursing break, within the schedule
	first_in: int | None = None  # minute
	last_out: int | None = None
	late_minutes: int = 0
	early_leave_minutes: int = 0
	absence_minutes: int = 0  # unexcused gaps inside the schedule
	absent_day: bool = False
	leave_minutes: dict[str, int] = field(default_factory=dict)
	leave_days: dict[str, float] = field(default_factory=dict)
	mission_minutes: int = 0
	nursing_minutes: int = 0
	extra_minutes: int = 0  # work outside the schedule (raw, before approval)
	overtime_intervals: list[tuple[int, int]] = field(
		default_factory=list
	)  # extra work that may become overtime
	outside_window_minutes: int = 0  # extra work outside the shift's overtime windows
	overtime_minutes: dict[str, int] = field(default_factory=dict)  # Normal / Exceptional / Emergency
	unapproved_extra_minutes: int = 0
	night_work_minutes: int = 0
	rest_day_work_minutes: int = 0
	friday_premium_minutes: int = 0
	holiday_work_minutes: int = 0
	company_holiday_work_minutes: int = 0
	warnings: list[str] = field(default_factory=list)

	@property
	def total_overtime_minutes(self) -> int:
		return sum(self.overtime_minutes.values())
