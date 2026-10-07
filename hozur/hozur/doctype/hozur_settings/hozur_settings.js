// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hozur Settings", {
	refresh(frm) {
		frm.add_custom_button(
			__("Update Calendar"),
			() => {
				frappe.call({
					method: "hozur.calendar_sync.update_calendar",
					freeze: true,
					freeze_message: __("Downloading the holiday file..."),
					callback: (r) => {
						const s = r.message || {};
						frappe.msgprint(
							__("Created {0}, updated {1}, left {2} edited holidays untouched.", [
								s.created,
								s.updated,
								s.skipped_edited,
							])
						);
						frm.reload_doc();
					},
				});
			},
			__("Calendar")
		);

		frm.add_custom_button(
			__("Generate Year"),
			() => {
				frappe.prompt(
					{ fieldname: "year", fieldtype: "Int", label: __("Jalali Year"), reqd: 1 },
					(values) => {
						frappe.call({
							method: "hozur.calendar_sync.generate_year",
							args: { year: values.year },
							freeze: true,
							callback: (r) => {
								const s = r.message || {};
								frappe.msgprint(
									__("Created {0} days and {1} holidays.", [s.days, s.holidays])
								);
							},
						});
					},
					__("Generate Calendar Year")
				);
			},
			__("Calendar")
		);
	},
});
