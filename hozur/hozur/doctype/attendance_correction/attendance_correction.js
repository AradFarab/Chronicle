// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Correction", {
	refresh(frm) {
		hozur.approvals.setup_form(frm);
		frm.set_query("raw_punch", "items", () => ({
			filters: { jdate: frm.doc.jdate || "" },
		}));
	},
});
