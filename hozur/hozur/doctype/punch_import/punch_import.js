// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Punch Import", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.file) return;
		frm.add_custom_button(
			frm.doc.status === "Draft" ? __("Import") : __("Import Again"),
			async () => {
				const r = await frm.call({
					method: "run_import",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Importing..."),
				});
				const s = r.message;
				frappe.msgprint(
					__("{0} new punches, {1} already stored, {2} duplicates.", [
						s.created,
						s.existing,
						s.duplicates,
					])
				);
				frm.reload_doc();
			}
		).addClass("btn-primary");
	},
});
