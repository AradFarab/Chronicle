// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Period", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status === "Open") {
			frm.add_custom_button(__("Close Period"), () => {
				frappe.confirm(__("Recalculate and lock {0}? Nothing in it can change until it is reopened.", [frm.doc.period]), async () => {
					await frm.call({ method: "close", doc: frm.doc, freeze: true, freeze_message: __("Closing...") });
					frm.reload_doc();
				});
			}).addClass("btn-primary");
		} else {
			frm.add_custom_button(__("Reopen Period"), () => {
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }, async (v) => {
					await frm.call({ method: "reopen", doc: frm.doc, args: { reason: v.reason }, freeze: true });
					frm.reload_doc();
				}, __("Reopen Period"));
			});
		}
	},
});
