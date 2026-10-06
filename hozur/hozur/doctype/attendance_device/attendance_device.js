// Copyright (c) 2026, Arad Farab and contributors
// For license information, please see license.txt

const DEVICE_API = "hozur.devices.service";

function device_call(frm, method, args, message) {
	return frappe.call({
		method: `${DEVICE_API}.${method}`,
		args: { device: frm.doc.name, ...(args || {}) },
		freeze: true,
		freeze_message: message || __("Talking to the device..."),
	});
}

frappe.ui.form.on("Attendance Device", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.adapter_type === "File Import") {
			if (!frm.is_new()) {
				frm.add_custom_button(__("Import a File"), () => {
					frappe.new_doc("Punch Import", { device: frm.doc.name });
				});
			}
			return;
		}

		frm.add_custom_button(__("Test Connection"), async () => {
			const r = await device_call(frm, "test_connection");
			const s = r.message;
			const time = s.device_time ? `${s.device_time[0]} ${s.device_time[1]}` : "-";
			frappe.msgprint({
				title: __("Connected"),
				indicator: "green",
				message: `
					<table class="table table-bordered">
						<tr><td>${__("Model")}</td><td>${frappe.utils.escape_html(s.model || "-")}</td></tr>
						<tr><td>${__("Serial Number")}</td><td>${frappe.utils.escape_html(s.serial_number || "-")}</td></tr>
						<tr><td>${__("Firmware")}</td><td>${frappe.utils.escape_html(s.firmware || "-")}</td></tr>
						<tr><td>${__("Users on Device")}</td><td>${s.user_count ?? "-"}</td></tr>
						<tr><td>${__("Log Records on Device")}</td><td>${s.record_count ?? "-"} / ${s.record_capacity ?? "-"}</td></tr>
						<tr><td>${__("Device Clock")}</td><td>${time}</td></tr>
						<tr><td>${__("Clock Difference (Seconds)")}</td><td>${s.clock_drift_seconds ?? "-"}</td></tr>
					</table>`,
			});
			frm.reload_doc();
		});

		frm.add_custom_button(__("Read Device Users"), async () => {
			const r = await device_call(frm, "read_device_users");
			const s = r.message;
			frappe.msgprint(
				__("{0} users on the device, {1} new, {2} matched to employees by employee code.", [
					s.users,
					s.created,
					s.auto_mapped,
				])
			);
		}, __("Device"));

		frm.add_custom_button(__("Read Punches Now"), async () => {
			const r = await device_call(frm, "sync_now", {}, __("Reading punches..."));
			const s = r.message;
			frappe.show_alert({
				message: __("{0} new punches, {1} already stored, {2} duplicates.", [s.created, s.existing, s.duplicates]),
				indicator: "green",
			});
			frm.reload_doc();
		}, __("Device"));

		frm.add_custom_button(__("Read Again From Date"), () => {
			frappe.prompt(
				{ fieldname: "jdate", fieldtype: "Data", label: __("From Jalali Date"), reqd: 1, description: "1405/07/01" },
				async (values) => {
					const r = await device_call(frm, "resync_from", { jdate: values.jdate }, __("Reading punches..."));
					const s = r.message;
					frappe.msgprint(__("{0} new punches, {1} already stored, {2} duplicates.", [s.created, s.existing, s.duplicates]));
					frm.reload_doc();
				},
				__("Read Again From Date")
			);
		}, __("Device"));

		frm.add_custom_button(__("Set Device Clock"), () => {
			frappe.confirm(__("Set the device clock to the server time?"), async () => {
				const r = await device_call(frm, "set_device_clock");
				frappe.show_alert({ message: __("Device clock set to {0}", [r.message.set_to.join(" ")]), indicator: "green" });
				frm.reload_doc();
			});
		}, __("Device"));

		frm.add_custom_button(__("Device Users"), () => {
			frappe.set_route("List", "Device User Map", { device: frm.doc.name });
		}, __("View"));
		frm.add_custom_button(__("Punches"), () => {
			frappe.set_route("List", "Raw Punch", { device: frm.doc.name });
		}, __("View"));

		if (frm.doc.last_sync_status === "Error") {
			frm.dashboard.set_headline_alert(
				`<div class="text-danger">${__("Last read failed")}: ${frappe.utils.escape_html(frm.doc.last_error || "")}</div>`
			);
		}
	},
});
