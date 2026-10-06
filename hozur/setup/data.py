"""Install-time reference data."""

# The 31 provinces of Iran (used for provincial holidays).
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

# Hozur roles. None of them opens the Frappe desk: people work in the PWA at /hozur.
ROLES = ("Hozur Employee", "Hozur Manager", "Hozur CEO", "Hozur Operator")

# Standard approval processes (design doc, approval section). Names are data, editable.
NO_APPROVAL = "بدون تأیید"
DIRECT_MANAGER = "مدیر مستقیم"
MANAGER_THEN_CEO = "مدیر مستقیم، سپس مدیرعامل"
CEO_ONLY = "فقط مدیرعامل"
STANDARD_PROCESSES = {
	NO_APPROVAL: [],
	DIRECT_MANAGER: ["Direct Manager"],
	MANAGER_THEN_CEO: ["Direct Manager", "CEO"],
	CEO_ONLY: ["CEO"],
}
# Defaults per request type, from the examples in the design doc. The operator changes them.
DEFAULT_PROCESSES = {
	"daily_leave_process": MANAGER_THEN_CEO,
	"hourly_leave_process": DIRECT_MANAGER,
	"overtime_process": DIRECT_MANAGER,
	"mission_process": MANAGER_THEN_CEO,
	"correction_process": DIRECT_MANAGER,
}
