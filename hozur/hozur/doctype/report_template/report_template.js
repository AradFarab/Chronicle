// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

const REPORT_API = "hozur.reports.api";

function ask_range(frm, title, callback) {
	frappe.prompt(
		[
			{
				fieldname: "from_date",
				fieldtype: "Data",
				label: __("From Jalali Date"),
				description: "1405/07/01",
			},
			{
				fieldname: "to_date",
				fieldtype: "Data",
				label: __("To Jalali Date"),
				description: "1405/07/30",
			},
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<p class="text-muted">${__("Leave empty for the default range")}</p>`,
			},
		],
		callback,
		title
	);
}

frappe.ui.form.on("Report Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Preview"), () =>
			ask_range(frm, __("Preview"), async (v) => {
				const r = await frappe.call({
					method: `${REPORT_API}.preview`,
					args: { template: frm.doc.name, filters: v, limit: 200 },
					freeze: true,
				});
				const data = r.message;
				const head = data.columns
					.map((c) => `<th>${frappe.utils.escape_html(c.label)}</th>`)
					.join("");
				const body = data.rows
					.map(
						(row) =>
							"<tr>" +
							data.columns
								.map(
									(c) =>
										`<td>${frappe.utils.escape_html(
											String(row[c.key] ?? "")
										)}</td>`
								)
								.join("") +
							"</tr>"
					)
					.join("");
				frappe.msgprint({
					title: `${__("Preview")} ${data.from_date} – ${data.to_date} (${
						data.total_rows
					})`,
					message: `<div style="overflow:auto;max-height:60vh"><table class="table table-bordered table-sm"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`,
					wide: true,
				});
			})
		);
		frm.add_custom_button(__("Export"), () =>
			ask_range(frm, __("Export"), (v) => {
				const params = new URLSearchParams({
					template: frm.doc.name,
					filters: JSON.stringify(v),
				});
				window.open(`/api/method/${REPORT_API}.export?${params.toString()}`);
			})
		).addClass("btn-primary");
	},
});

frappe.ui.form.on("Report Template Column", {
	field(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe
			.call({ method: `${REPORT_API}.fields`, args: { source: frm.doc.source } })
			.then((r) => {
				const f = (r.message || []).find((x) => x.key === row.field);
				if (f && !row.label) frappe.model.set_value(cdt, cdn, "label", f.label);
			});
	},
});
