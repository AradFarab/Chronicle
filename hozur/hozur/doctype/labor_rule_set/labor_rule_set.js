// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Labor Rule Set", {
	async onload(frm) {
		if (!frm.is_new() || frm.doc.is_legal_baseline) return;
		const r = await frappe.call("hozur.hozur.doctype.labor_rule_set.labor_rule_set.get_baseline_values");
		for (const [field, value] of Object.entries(r.message || {})) {
			if (!frm.doc[field]) frm.set_value(field, value);
		}
	},
	refresh(frm) {
		if (frm.doc.is_legal_baseline) {
			frm.disable_form();
			frm.set_intro(__("These are the values of the Labor Law. Create a company rule set to be more generous."), "blue");
		}
	},
});
