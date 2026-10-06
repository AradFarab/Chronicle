// Approve / Reject buttons for hozur requests (hozur.approvals.ApprovableRequest).
frappe.provide("hozur.approvals");

hozur.approvals.setup_form = function (frm) {
	if (frm.doc.docstatus !== 1 || frm.doc.status !== "Pending") return;
	const me = frappe.session.user;
	const can_act = frm.doc.pending_approver_user === me || frappe.user.has_role("System Manager");
	if (!can_act) return;

	const act = (action) => {
		frappe.prompt(
			{ fieldname: "comment", fieldtype: "Small Text", label: __("Comment"), reqd: action === "Reject" },
			async (values) => {
				await frappe.call({
					method: "hozur.approvals.act_on_request",
					args: { doctype: frm.doctype, name: frm.doc.name, action, comment: values.comment },
					freeze: true,
				});
				frm.reload_doc();
			},
			action === "Approve" ? __("Approve") : __("Reject")
		);
	};
	frm.add_custom_button(__("Approve"), () => act("Approve")).addClass("btn-primary");
	frm.add_custom_button(__("Reject"), () => act("Reject")).addClass("btn-danger");
};
