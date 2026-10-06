app_name = "hozur"
app_title = "Hozur"
app_publisher = "Arad Farab"
app_description = "Attendance for Iranian companies: Jalali calendar, Iranian Labor Law engine, Persian PWA"
app_email = "219307864+AradFarab@users.noreply.github.com"
app_license = "gpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "hozur",
# 		"logo": "/assets/hozur/logo.png",
# 		"title": "Hozur",
# 		"route": "/hozur",
# 		"has_permission": "hozur.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `hozur/dock/hozur/hozur.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/hozur/css/hozur.css"
app_include_js = ["/assets/hozur/js/approvals.js"]

# include js, css files in header of web template
# web_include_css = "/assets/hozur/css/hozur.css"
# web_include_js = "/assets/hozur/js/hozur.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "hozur/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "hozur/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "hozur.utils.jinja_methods",
# 	"filters": "hozur.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "hozur.install.before_install"
after_install = "hozur.setup.install.after_install"
after_migrate = "hozur.setup.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "hozur.uninstall.before_uninstall"
# after_uninstall = "hozur.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "hozur.utils.before_app_install"
# after_app_install = "hozur.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "hozur.utils.before_app_uninstall"
# after_app_uninstall = "hozur.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "hozur.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "hozur.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["hozur.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Role + department subtree (hozur.permissions). Doctypes with an `employee` field are
# added to EMPLOYEE_SCOPED_DOCTYPES as they are built.
EMPLOYEE_SCOPED_DOCTYPES = ["Daily Attendance", "Leave Ledger Entry", "Shift Override"]

# Requests (hozur.approvals.ApprovableRequest): visible to the employee scope and to the
# people in their approval chain; listed in the approval inbox.
hozur_request_doctypes = ["Attendance Correction", "Leave Application", "Mission", "Overtime Request"]

permission_query_conditions = {
	"Employee": "hozur.permissions.employee_query",
	"Report Template": "hozur.reports.api.template_query",
	**{dt: "hozur.permissions.employee_condition" for dt in EMPLOYEE_SCOPED_DOCTYPES},
	**{dt: "hozur.approvals.request_query" for dt in hozur_request_doctypes},
}

has_permission = {
	"Employee": "hozur.permissions.has_employee_doc_permission",
	"Report Template": "hozur.reports.api.has_template_permission",
	**{dt: "hozur.permissions.has_employee_permission" for dt in EMPLOYEE_SCOPED_DOCTYPES},
	**{dt: "hozur.approvals.has_request_permission" for dt in hozur_request_doctypes},
}

# Document Events
# ---------------
# Hook on document methods and events

# Configured records write an append-only Audit Entry on every change (hozur.audit).
AUDITED_DOCTYPES = [
	"Iran Holiday",
	"Hozur Settings",
	"Organization",
	"Branch",
	"Department",
	"Designation",
	"Employee",
	"Attendance Device",
	"Device User Map",
	"Punch Import Template",
	"Approval Process",
	"Approval Override",
	"Labor Rule Set",
	"Shift",
	"Work Pattern",
	"Work Pattern Assignment",
	"Shift Override",
	"Leave Type",
	"Attendance Period",
]

doc_events = {
	dt: {
		"validate": "hozur.audit.require_reason",
		"on_update": "hozur.audit.on_update",
		"on_trash": "hozur.audit.on_trash",
	}
	for dt in AUDITED_DOCTYPES
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		# each device is read at its own interval (Attendance Device.polling_interval_minutes)
		"* * * * *": ["hozur.devices.service.poll_devices"],
	},
	"daily": ["hozur.calendar_sync.warn_predicted_next_year", "hozur.attendance.nightly"],
}

# Device adapters contributed by other apps: dotted module paths whose import registers a
# hozur.devices.base.DeviceAdapter subclass with @register.
hozur_device_adapters = []

# Testing
# -------

# before_tests = "hozur.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "hozur.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "hozur.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "hozur.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# The audit trail outlives the documents it describes and must never block a delete.
ignore_links_on_delete = ["Audit Entry"]

# Request Events
# ----------------
# before_request = ["hozur.utils.before_request"]
# after_request = ["hozur.utils.after_request"]

# Job Events
# ----------
# before_job = ["hozur.utils.before_job"]
# after_job = ["hozur.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"hozur.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
