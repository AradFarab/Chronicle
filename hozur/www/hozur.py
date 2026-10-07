import frappe

from hozur.api.pwa import get_boot, translations

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/hozur"
		raise frappe.Redirect
	csrf_token = frappe.sessions.get_csrf_token()
	# the CSRF token must be saved before the page uses it
	frappe.db.commit()  # nosemgrep
	context.boot = {
		"csrf_token": csrf_token,
		"hozur_boot": get_boot(),
		"hozur_messages": translations(),
	}
	return context
