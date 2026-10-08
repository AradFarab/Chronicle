"""Reference data seeded on install. Everything here is ordinary data the operator may edit."""

# The 31 provinces of Iran (for provincial holidays).
PROVINCES = (
	"آذربایجان شرقی",
	"آذربایجان غربی",
	"اردبیل",
	"اصفهان",
	"البرز",
	"ایلام",
	"بوشهر",
	"تهران",
	"چهارمحال و بختیاری",
	"خراسان جنوبی",
	"خراسان رضوی",
	"خراسان شمالی",
	"خوزستان",
	"زنجان",
	"سمنان",
	"سیستان و بلوچستان",
	"فارس",
	"قزوین",
	"قم",
	"کردستان",
	"کرمان",
	"کرمانشاه",
	"کهگیلویه و بویراحمد",
	"گلستان",
	"گیلان",
	"لرستان",
	"مازندران",
	"مرکزی",
	"هرمزگان",
	"همدان",
	"یزد",
)

ROOT_DEPARTMENT = "همه واحدها"

# Standard approval processes (design doc, approval section). Names are data, editable.
NO_APPROVAL = "بدون تأیید"
DIRECT_MANAGER = "مدیر مستقیم"
MANAGER_THEN_CEO = "مدیر مستقیم، سپس مدیرعامل"
CEO_ONLY = "فقط مدیرعامل"
STANDARD_PROCESSES = {
	NO_APPROVAL: [],
	DIRECT_MANAGER: ["direct_manager"],
	MANAGER_THEN_CEO: ["direct_manager", "ceo"],
	CEO_ONLY: ["ceo"],
}
# Default process per request type (design doc examples); the operator changes them.
DEFAULT_PROCESSES = {
	"daily_leave": MANAGER_THEN_CEO,
	"hourly_leave": DIRECT_MANAGER,
	"overtime": DIRECT_MANAGER,
	"mission": MANAGER_THEN_CEO,
	"attendance_correction": DIRECT_MANAGER,
	"operator_entry": DIRECT_MANAGER,
}

# name, category, paid, deducts from balance, hourly allowed, rule-set limit, once in service
LEAVE_TYPES = (
	("استحقاقی", "earned", True, True, True, None, False),
	("استعلاجی", "sick", False, False, False, None, False),
	("بدون حقوق", "unpaid", False, False, True, None, False),
	(
		"ازدواج یا فوت بستگان",
		"marriage_bereavement",
		True,
		False,
		False,
		"marriage_bereavement_leave_days",
		False,
	),
	("حج واجب", "hajj", True, False, False, "hajj_leave_days", True),
	("زایمان", "maternity", False, False, False, "maternity_leave_days", False),
	("پدری (تولد فرزند)", "paternity", True, False, False, "paternity_leave_days", False),
)

# Ready-made punch file template; the ZKTeco USB format is fixed by the device.
IMPORT_TEMPLATES = ({"name": "فلش ZKTeco (attlog.dat)", "file_format": "zkteco_usb"},)

# The four standard report templates of the design doc (columns are catalog keys).
REPORT_TEMPLATES = (
	{
		"name": "کارکرد ماهانه برای حقوق",
		"source": "summary",
		"default_range": "current_month",
		"export_format": "excel",
		"columns": [
			"employee",
			"employee_name",
			"national_id",
			"department",
			"employed_days",
			"paid_days",
			"absent_days",
			"credited_minutes",
			"worked_minutes",
			"overtime_total_minutes",
			"night_work_minutes",
			"rest_day_work_minutes",
			"friday_premium_minutes",
			"holiday_work_minutes",
			"late_minutes",
			"early_leave_minutes",
			"absence_minutes",
			"leave_days",
			"mission_days",
		],
	},
	{
		"name": "گزارش مرخصی",
		"source": "summary",
		"default_range": "current_month",
		"export_format": "excel",
		"columns": [
			"employee",
			"employee_name",
			"department",
			"leave:استحقاقی",
			"leave:استعلاجی",
			"leave:بدون حقوق",
			"leave:ازدواج یا فوت بستگان",
			"leave_days",
			"leave_balance",
		],
	},
	{
		"name": "گزارش اضافه‌کار",
		"source": "summary",
		"default_range": "current_month",
		"export_format": "excel",
		"columns": [
			"employee",
			"employee_name",
			"department",
			"overtime_normal_minutes",
			"overtime_exceptional_minutes",
			"overtime_emergency_minutes",
			"overtime_total_minutes",
			"unapproved_extra_minutes",
			"night_work_minutes",
			"holiday_work_minutes",
			"rest_day_work_minutes",
		],
	},
	{
		"name": "حاضرین امروز",
		"source": "daily",
		"default_range": "today",
		"export_format": "pdf",
		"columns": [
			"employee",
			"employee_name",
			"department",
			"status",
			"shift",
			"first_in",
			"last_out",
			"late_minutes",
		],
	},
)

# Default app settings (app_setting rows).
SETTINGS = {
	"dedup_window_seconds": 30,
	"clock_drift_warning_seconds": 60,
	"absence_warning_days": 3,
	"allow_negative_leave_balance": False,
	"calendar_source": "time_ir",
	"time_ir_url": "https://api.time.ir/v1/event/fa/events/calendar?year={year}&month={month}&day=0&base1=0&base2=1&base3=2",
	"time_ir_api_key": "ZAVdqwuySASubByCed5KYuYMzb9uB2f7",
}
