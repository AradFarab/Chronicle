// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

const HOZUR_WARNINGS = {
	MISSING_PUNCH: __("A punch has no pair: correct the day"),
	ARTICLE_54_SPAN_EXCEEDED: __("More than 15 hours from first to last punch (Article 54)"),
	ARTICLE_51_SCHEDULE_OVER_DAILY_LIMIT: __("The shift is longer than the daily limit (Article 51)"),
	ARTICLE_52_SCHEDULE_OVER_HARD_HARMFUL_LIMIT: __("The shift is longer than 6 hours for hard and harmful work (Article 52)"),
	ARTICLE_59_OVERTIME_CAP: __("Overtime above the daily cap was not counted (Article 59)"),
	ARTICLE_60_EMERGENCY_CAP: __("Emergency overtime above 8 hours was not counted (Article 60)"),
	ARTICLE_61_NO_OVERTIME_HARD_HARMFUL: __("No overtime in hard and harmful work (Article 61)"),
	ARTICLE_84_NO_OVERTIME_JUVENILE: __("No overtime for young workers (Article 84)"),
	ARTICLE_84_NO_NIGHT_WORK_JUVENILE: __("No night work for young workers (Article 84)"),
	UNAPPROVED_EXTRA_WORK: __("Extra work without an approved overtime request"),
};

frappe.ui.form.on("Daily Attendance", {
	refresh(frm) {
		const codes = (frm.doc.warnings || "").split(",").map((c) => c.trim()).filter(Boolean);
		if (codes.length) {
			frm.set_intro(codes.map((c) => frappe.utils.escape_html(HOZUR_WARNINGS[c] || c)).join("<br>"), "orange");
		}
		if (frappe.user.has_role(["System Manager", "Hozur Operator"])) {
			frm.add_custom_button(__("Recalculate"), async () => {
				await frappe.call({
					method: "hozur.attendance.recalculate_range",
					args: { employee: frm.doc.employee, start: frm.doc.jdate, end: frm.doc.jdate },
					freeze: true,
				});
				frm.reload_doc();
			});
		}
	},
});
