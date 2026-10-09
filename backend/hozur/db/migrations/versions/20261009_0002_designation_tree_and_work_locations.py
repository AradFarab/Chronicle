"""designation tree, employee = user, work locations, flat departments

The organization is now the tree of designations (سمت): a person's parent is whoever holds the
nearest filled designation above theirs, and the CEO is the holder of the one designation
flagged ``is_ceo``. Departments are plain tags, branches became work locations, every employee
has a login, and an approval step can have several approvers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import hozur.db.types

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SCOPES = "'country', 'province', 'branch', 'company'"
NEW_SCOPES = "'country', 'province', 'work_location', 'company'"
OLD_APPROVER_TYPES = "'direct_manager', 'parent_department_manager', 'ceo', 'specific_person'"
NEW_APPROVER_TYPES = "'parent', 'ceo', 'specific_person'"
REQUEST_TYPES = "'daily_leave', 'hourly_leave', 'mission', 'overtime', 'attendance_correction'"


def _replace_check(table: str, name: str, expression: str, *updates: str) -> None:
	"""Swap a CHECK constraint, running the data updates between the drop and the create so the
	rows are never judged by a constraint that does not fit them."""
	op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
	for statement in updates:
		op.execute(statement)
	op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, expression)


def upgrade() -> None:
	# --- branch -> work_location ------------------------------------------------------------
	op.rename_table("branch", "work_location")
	op.execute("ALTER SEQUENCE IF EXISTS branch_id_seq RENAME TO work_location_id_seq")
	op.execute("ALTER TABLE work_location RENAME CONSTRAINT pk_branch TO pk_work_location")
	op.execute("ALTER TABLE work_location RENAME CONSTRAINT uq_branch_name TO uq_work_location_name")
	op.execute(
		"ALTER TABLE work_location RENAME CONSTRAINT fk_branch_province_id_province "
		"TO fk_work_location_province_id_province"
	)
	for table in ("attendance_device", "employee", "holiday", "daily_attendance"):
		op.alter_column(table, "branch_id", new_column_name="work_location_id")
		op.execute(
			f"ALTER TABLE {table} RENAME CONSTRAINT fk_{table}_branch_id_branch "
			f"TO fk_{table}_work_location_id_work_location"
		)
	op.drop_constraint(op.f("ck_holiday_scope_valid"), "holiday", type_="check")
	op.drop_constraint(op.f("ck_holiday_branch_scope"), "holiday", type_="check")
	op.drop_index("uq_holiday_day_title_scope", table_name="holiday")
	op.execute("UPDATE holiday SET scope = 'work_location' WHERE scope = 'branch'")
	op.create_check_constraint(op.f("ck_holiday_scope_valid"), "holiday", f"scope IN ({NEW_SCOPES})")
	op.create_check_constraint(
		op.f("ck_holiday_work_location_scope"),
		"holiday",
		"(scope = 'work_location') = (work_location_id IS NOT NULL)",
	)
	op.create_index(
		"uq_holiday_day_title_scope",
		"holiday",
		[
			"jdate",
			"title",
			"scope",
			sa.literal_column("coalesce(province_id, 0)"),
			sa.literal_column("coalesce(work_location_id, 0)"),
		],
		unique=True,
	)
	op.execute(
		"UPDATE report_template SET columns = replace(columns::text, '\"branch\"', '\"work_location\"')::jsonb"
	)

	# --- designations: a tree, one of them the CEO ---------------------------------------------
	op.add_column("designation", sa.Column("parent_id", sa.BigInteger(), nullable=True))
	op.add_column("designation", sa.Column("is_ceo", sa.Boolean(), server_default=sa.false(), nullable=False))
	op.create_foreign_key(
		op.f("fk_designation_parent_id_designation"), "designation", "designation", ["parent_id"], ["id"]
	)
	op.create_index(op.f("ix_designation_parent_id"), "designation", ["parent_id"], unique=False)
	op.create_check_constraint(op.f("ck_designation_not_own_parent"), "designation", "parent_id <> id")
	op.create_check_constraint(
		op.f("ck_designation_ceo_is_root"), "designation", "NOT is_ceo OR parent_id IS NULL"
	)
	op.create_index(
		"uq_designation_one_ceo", "designation", ["is_ceo"], unique=True, postgresql_where=sa.text("is_ceo")
	)

	op.create_table(
		"designation_assignment",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("designation_id", sa.BigInteger(), nullable=False),
		sa.Column("valid_from", hozur.db.types.JDate(), nullable=False),
		sa.Column("valid_to", hozur.db.types.JDate(), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_designation_assignment_valid_range")
		),
		sa.ForeignKeyConstraint(
			["designation_id"],
			["designation.id"],
			name=op.f("fk_designation_assignment_designation_id_designation"),
		),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_designation_assignment_employee_id_employee"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_designation_assignment")),
	)
	op.create_index(
		"ix_designation_assignment_employee_id", "designation_assignment", ["employee_id"], unique=False
	)
	op.create_index(
		"ix_designation_assignment_designation_id", "designation_assignment", ["designation_id"], unique=False
	)
	# the CEO of the old organization row, and every employee's old designation, are kept
	op.execute(
		"INSERT INTO designation (name, is_ceo) "
		"SELECT 'مدیرعامل', true WHERE EXISTS (SELECT 1 FROM organization WHERE ceo_id IS NOT NULL) "
		"AND NOT EXISTS (SELECT 1 FROM designation WHERE name = 'مدیرعامل')"
	)
	op.execute(
		"UPDATE designation SET is_ceo = true WHERE name = 'مدیرعامل' "
		"AND EXISTS (SELECT 1 FROM organization WHERE ceo_id IS NOT NULL)"
	)
	op.execute(
		"INSERT INTO designation_assignment (employee_id, designation_id, valid_from) "
		"SELECT e.id, e.designation_id, e.start_date FROM employee e WHERE e.designation_id IS NOT NULL"
	)
	op.execute(
		"INSERT INTO designation_assignment (employee_id, designation_id, valid_from) "
		"SELECT o.ceo_id, d.id, e.start_date FROM organization o "
		"JOIN employee e ON e.id = o.ceo_id JOIN designation d ON d.is_ceo "
		"WHERE NOT EXISTS (SELECT 1 FROM designation_assignment a WHERE a.employee_id = o.ceo_id AND a.designation_id = d.id)"
	)

	# --- departments become tags -------------------------------------------------------------------
	for fk in ("default_approver_id", "deputy_id", "manager_id"):
		op.drop_constraint(op.f(f"fk_department_{fk}_employee"), "department", type_="foreignkey")
	op.drop_constraint(op.f("fk_department_parent_id_department"), "department", type_="foreignkey")
	op.drop_constraint(op.f("ck_department_deputy_range"), "department", type_="check")
	op.drop_constraint(op.f("ck_department_not_own_parent"), "department", type_="check")
	op.drop_index(op.f("ix_department_parent_id"), table_name="department")
	for column in (
		"parent_id",
		"is_group",
		"manager_id",
		"default_approver_id",
		"deputy_id",
		"deputy_from",
		"deputy_to",
	):
		op.drop_column("department", column)

	# --- employees are users -------------------------------------------------------------------
	op.execute(
		"INSERT INTO app_user (username, full_name, language, is_active) "
		"SELECT CASE WHEN EXISTS (SELECT 1 FROM app_user u WHERE u.username = lower(e.code)) "
		"THEN lower(e.code) || '-' || e.id ELSE lower(e.code) END, e.full_name, 'fa', e.status = 'active' "
		"FROM employee e WHERE e.user_id IS NULL"
	)
	op.execute(
		"UPDATE employee e SET user_id = u.id FROM app_user u "
		"WHERE e.user_id IS NULL AND (u.username = lower(e.code) OR u.username = lower(e.code) || '-' || e.id)"
	)
	op.execute(
		"INSERT INTO user_role (user_id, role) SELECT e.user_id, 'employee' FROM employee e ON CONFLICT DO NOTHING"
	)
	op.drop_constraint(op.f("fk_employee_user_id_app_user"), "employee", type_="foreignkey")
	op.alter_column("employee", "user_id", existing_type=sa.BigInteger(), nullable=False)
	op.create_foreign_key(op.f("fk_employee_user_id_app_user"), "employee", "app_user", ["user_id"], ["id"])
	op.add_column("employee", sa.Column("detail_code", sa.String(length=30), nullable=True))
	op.create_index(
		"uq_employee_detail_code",
		"employee",
		["detail_code"],
		unique=True,
		postgresql_where=sa.text("detail_code IS NOT NULL"),
	)
	op.drop_constraint(op.f("fk_employee_designation_id_designation"), "employee", type_="foreignkey")
	op.drop_constraint(op.f("fk_employee_reports_to_id_employee"), "employee", type_="foreignkey")
	op.drop_constraint(op.f("ck_employee_not_own_manager"), "employee", type_="check")
	op.drop_column("employee", "designation_id")
	op.drop_column("employee", "reports_to_id")
	op.drop_constraint(op.f("fk_organization_ceo_id_employee"), "organization", type_="foreignkey")
	op.drop_column("organization", "ceo_id")

	# --- roles: system admin and employee --------------------------------------------------------------
	op.execute(
		"INSERT INTO user_role (user_id, role) SELECT user_id, 'admin' FROM user_role WHERE role = 'operator' "
		"ON CONFLICT DO NOTHING"
	)
	op.execute("DELETE FROM user_role WHERE role IN ('operator', 'ceo', 'manager')")
	_replace_check("user_role", "role_valid", "role IN ('admin', 'employee')")

	# --- approvals: several approvers per step, parent / CEO steps, delegation ---------------------------
	op.create_table(
		"request_approval_approver",
		sa.Column("approval_id", sa.BigInteger(), nullable=False),
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("user_id", sa.BigInteger(), nullable=False),
		sa.ForeignKeyConstraint(
			["approval_id"],
			["request_approval.id"],
			name=op.f("fk_request_approval_approver_approval_id_request_approval"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["employee_id"], ["employee.id"], name=op.f("fk_request_approval_approver_employee_id_employee")
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["app_user.id"], name=op.f("fk_request_approval_approver_user_id_app_user")
		),
		sa.PrimaryKeyConstraint("approval_id", "employee_id", name=op.f("pk_request_approval_approver")),
	)
	op.create_index(
		"ix_request_approval_approver_user_id", "request_approval_approver", ["user_id"], unique=False
	)
	op.execute(
		"INSERT INTO request_approval_approver (approval_id, employee_id, user_id) "
		"SELECT a.id, a.approver_id, e.user_id FROM request_approval a JOIN employee e ON e.id = a.approver_id "
		"WHERE a.approver_id IS NOT NULL"
	)
	op.drop_constraint(
		op.f("fk_request_approval_approver_id_employee"), "request_approval", type_="foreignkey"
	)
	op.drop_constraint(
		op.f("fk_request_approval_approver_user_id_app_user"), "request_approval", type_="foreignkey"
	)
	op.drop_column("request_approval", "approver_id")
	op.drop_column("request_approval", "approver_user_id")
	op.drop_index("ix_request_inbox", table_name="request", postgresql_where=sa.text("status = 'pending'"))
	op.drop_constraint(op.f("ck_request_pending_only_when_pending"), "request", type_="check")
	op.drop_constraint(op.f("fk_request_pending_approver_id_employee"), "request", type_="foreignkey")
	op.drop_constraint(op.f("fk_request_pending_approver_user_id_app_user"), "request", type_="foreignkey")
	op.drop_column("request", "pending_approver_id")
	op.drop_column("request", "pending_approver_user_id")
	op.create_index(
		"ix_request_status",
		"request",
		["status"],
		unique=False,
		postgresql_where=sa.text("status = 'pending'"),
	)
	op.alter_column("request", "entered_by_operator", new_column_name="entered_by_admin")
	op.alter_column("holiday", "edited_by_operator", new_column_name="edited_by_admin")

	_replace_check(
		"approval_process_step",
		"approver_type_valid",
		f"approver_type IN ({NEW_APPROVER_TYPES})",
		"UPDATE approval_process_step SET approver_type = 'parent' "
		"WHERE approver_type IN ('direct_manager', 'parent_department_manager')",
	)
	_replace_check(
		"request_approval",
		"approver_type_valid",
		f"approver_type IN ({NEW_APPROVER_TYPES}, 'employee_acceptance')",
		"UPDATE request_approval SET approver_type = 'parent' "
		"WHERE approver_type IN ('direct_manager', 'parent_department_manager')",
	)
	_replace_check(
		"approval_default",
		"request_type_valid",
		f"request_type IN ({REQUEST_TYPES}, 'admin_entry')",
		"UPDATE approval_default SET request_type = 'admin_entry' WHERE request_type = 'operator_entry'",
	)
	op.execute(
		"UPDATE approval_process SET name = 'تأیید مافوق مستقیم' WHERE name = 'مدیر مستقیم' AND is_standard"
	)
	op.execute(
		"UPDATE approval_process SET name = 'مافوق مستقیم، سپس مدیرعامل' "
		"WHERE name = 'مدیر مستقیم، سپس مدیرعامل' AND is_standard"
	)

	op.create_table(
		"approval_delegation",
		sa.Column("delegator_id", sa.BigInteger(), nullable=False),
		sa.Column("delegate_id", sa.BigInteger(), nullable=False),
		sa.Column("valid_from", hozur.db.types.JDate(), nullable=False),
		sa.Column("valid_to", hozur.db.types.JDate(), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint("delegator_id <> delegate_id", name=op.f("ck_approval_delegation_not_self")),
		sa.CheckConstraint(
			"valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_approval_delegation_valid_range")
		),
		sa.ForeignKeyConstraint(
			["delegate_id"],
			["employee.id"],
			name=op.f("fk_approval_delegation_delegate_id_employee"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["delegator_id"],
			["employee.id"],
			name=op.f("fk_approval_delegation_delegator_id_employee"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_delegation")),
	)
	op.create_index(
		"ix_approval_delegation_delegate_id", "approval_delegation", ["delegate_id"], unique=False
	)

	# --- rotating patterns: groups of people can start at different points of the cycle -----------------
	op.add_column(
		"work_pattern_assignment",
		sa.Column("cycle_offset_days", sa.Integer(), server_default="0", nullable=False),
	)
	op.create_check_constraint(
		op.f("ck_work_pattern_assignment_cycle_offset_non_negative"),
		"work_pattern_assignment",
		"cycle_offset_days >= 0",
	)


def downgrade() -> None:
	op.drop_constraint(
		op.f("ck_work_pattern_assignment_cycle_offset_non_negative"), "work_pattern_assignment", type_="check"
	)
	op.drop_column("work_pattern_assignment", "cycle_offset_days")
	op.drop_table("approval_delegation")

	op.execute(
		"UPDATE approval_process SET name = 'مدیر مستقیم، سپس مدیرعامل' WHERE name = 'مافوق مستقیم، سپس مدیرعامل' AND is_standard"
	)
	op.execute(
		"UPDATE approval_process SET name = 'مدیر مستقیم' WHERE name = 'تأیید مافوق مستقیم' AND is_standard"
	)
	_replace_check(
		"approval_default",
		"request_type_valid",
		f"request_type IN ({REQUEST_TYPES}, 'operator_entry')",
		"UPDATE approval_default SET request_type = 'operator_entry' WHERE request_type = 'admin_entry'",
	)
	_replace_check(
		"approval_process_step",
		"approver_type_valid",
		f"approver_type IN ({OLD_APPROVER_TYPES})",
		"UPDATE approval_process_step SET approver_type = 'direct_manager' WHERE approver_type = 'parent'",
	)
	_replace_check(
		"request_approval",
		"approver_type_valid",
		f"approver_type IN ({OLD_APPROVER_TYPES}, 'employee_acceptance')",
		"UPDATE request_approval SET approver_type = 'direct_manager' WHERE approver_type = 'parent'",
	)
	op.alter_column("request", "entered_by_admin", new_column_name="entered_by_operator")
	op.alter_column("holiday", "edited_by_admin", new_column_name="edited_by_operator")
	op.drop_index("ix_request_status", table_name="request", postgresql_where=sa.text("status = 'pending'"))
	op.add_column("request", sa.Column("pending_approver_user_id", sa.BigInteger(), nullable=True))
	op.add_column("request", sa.Column("pending_approver_id", sa.BigInteger(), nullable=True))
	op.create_foreign_key(
		op.f("fk_request_pending_approver_user_id_app_user"),
		"request",
		"app_user",
		["pending_approver_user_id"],
		["id"],
	)
	op.create_foreign_key(
		op.f("fk_request_pending_approver_id_employee"),
		"request",
		"employee",
		["pending_approver_id"],
		["id"],
	)
	op.create_check_constraint(
		op.f("ck_request_pending_only_when_pending"),
		"request",
		"(status = 'pending') OR pending_approver_user_id IS NULL",
	)
	op.create_index(
		"ix_request_inbox",
		"request",
		["pending_approver_user_id"],
		unique=False,
		postgresql_where=sa.text("status = 'pending'"),
	)
	op.add_column("request_approval", sa.Column("approver_user_id", sa.BigInteger(), nullable=True))
	op.add_column("request_approval", sa.Column("approver_id", sa.BigInteger(), nullable=True))
	op.execute(
		"UPDATE request_approval a SET approver_id = x.employee_id, approver_user_id = x.user_id FROM "
		"(SELECT DISTINCT ON (approval_id) approval_id, employee_id, user_id FROM request_approval_approver "
		"ORDER BY approval_id, employee_id) x WHERE x.approval_id = a.id"
	)
	op.create_foreign_key(
		op.f("fk_request_approval_approver_user_id_app_user"),
		"request_approval",
		"app_user",
		["approver_user_id"],
		["id"],
	)
	op.create_foreign_key(
		op.f("fk_request_approval_approver_id_employee"),
		"request_approval",
		"employee",
		["approver_id"],
		["id"],
	)
	op.drop_table("request_approval_approver")

	_replace_check("user_role", "role_valid", "role IN ('admin', 'operator', 'ceo', 'manager', 'employee')")

	op.add_column("organization", sa.Column("ceo_id", sa.BigInteger(), nullable=True))
	op.create_foreign_key(
		op.f("fk_organization_ceo_id_employee"),
		"organization",
		"employee",
		["ceo_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.add_column("employee", sa.Column("reports_to_id", sa.BigInteger(), nullable=True))
	op.add_column("employee", sa.Column("designation_id", sa.BigInteger(), nullable=True))
	op.execute(
		"UPDATE employee e SET designation_id = a.designation_id FROM "
		"(SELECT DISTINCT ON (employee_id) employee_id, designation_id FROM designation_assignment "
		"ORDER BY employee_id, valid_from DESC, id DESC) a WHERE a.employee_id = e.id"
	)
	op.execute(
		"UPDATE organization SET ceo_id = (SELECT a.employee_id FROM designation_assignment a "
		"JOIN designation d ON d.id = a.designation_id AND d.is_ceo ORDER BY a.valid_from LIMIT 1)"
	)
	op.create_foreign_key(
		op.f("fk_employee_reports_to_id_employee"),
		"employee",
		"employee",
		["reports_to_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_foreign_key(
		op.f("fk_employee_designation_id_designation"), "employee", "designation", ["designation_id"], ["id"]
	)
	op.create_check_constraint(op.f("ck_employee_not_own_manager"), "employee", "reports_to_id <> id")
	op.drop_index(
		"uq_employee_detail_code", table_name="employee", postgresql_where=sa.text("detail_code IS NOT NULL")
	)
	op.drop_column("employee", "detail_code")
	op.drop_constraint(op.f("fk_employee_user_id_app_user"), "employee", type_="foreignkey")
	op.alter_column("employee", "user_id", existing_type=sa.BigInteger(), nullable=True)
	op.create_foreign_key(
		op.f("fk_employee_user_id_app_user"), "employee", "app_user", ["user_id"], ["id"], ondelete="SET NULL"
	)

	op.add_column("department", sa.Column("deputy_to", hozur.db.types.JDate(), nullable=True))
	op.add_column("department", sa.Column("deputy_from", hozur.db.types.JDate(), nullable=True))
	op.add_column("department", sa.Column("deputy_id", sa.BigInteger(), nullable=True))
	op.add_column("department", sa.Column("default_approver_id", sa.BigInteger(), nullable=True))
	op.add_column("department", sa.Column("manager_id", sa.BigInteger(), nullable=True))
	op.add_column(
		"department", sa.Column("is_group", sa.Boolean(), server_default=sa.false(), nullable=False)
	)
	op.add_column("department", sa.Column("parent_id", sa.BigInteger(), nullable=True))
	op.create_index(op.f("ix_department_parent_id"), "department", ["parent_id"], unique=False)
	op.create_foreign_key(
		op.f("fk_department_parent_id_department"), "department", "department", ["parent_id"], ["id"]
	)
	for fk in ("manager_id", "default_approver_id", "deputy_id"):
		op.create_foreign_key(
			op.f(f"fk_department_{fk}_employee"), "department", "employee", [fk], ["id"], ondelete="SET NULL"
		)
	op.create_check_constraint(op.f("ck_department_not_own_parent"), "department", "parent_id <> id")
	op.create_check_constraint(
		op.f("ck_department_deputy_range"),
		"department",
		"deputy_to IS NULL OR deputy_from IS NULL OR deputy_to >= deputy_from",
	)

	op.drop_table("designation_assignment")
	op.drop_index("uq_designation_one_ceo", table_name="designation", postgresql_where=sa.text("is_ceo"))
	op.drop_constraint(op.f("ck_designation_ceo_is_root"), "designation", type_="check")
	op.drop_constraint(op.f("ck_designation_not_own_parent"), "designation", type_="check")
	op.drop_index(op.f("ix_designation_parent_id"), table_name="designation")
	op.drop_constraint(op.f("fk_designation_parent_id_designation"), "designation", type_="foreignkey")
	op.drop_column("designation", "is_ceo")
	op.drop_column("designation", "parent_id")

	op.execute(
		"UPDATE report_template SET columns = replace(columns::text, '\"work_location\"', '\"branch\"')::jsonb"
	)
	op.drop_index("uq_holiday_day_title_scope", table_name="holiday")
	op.drop_constraint(op.f("ck_holiday_work_location_scope"), "holiday", type_="check")
	op.drop_constraint(op.f("ck_holiday_scope_valid"), "holiday", type_="check")
	op.execute("UPDATE holiday SET scope = 'branch' WHERE scope = 'work_location'")
	for table in ("daily_attendance", "holiday", "employee", "attendance_device"):
		op.execute(
			f"ALTER TABLE {table} RENAME CONSTRAINT fk_{table}_work_location_id_work_location "
			f"TO fk_{table}_branch_id_branch"
		)
		op.alter_column(table, "work_location_id", new_column_name="branch_id")
	op.create_check_constraint(op.f("ck_holiday_scope_valid"), "holiday", f"scope IN ({OLD_SCOPES})")
	op.create_check_constraint(
		op.f("ck_holiday_branch_scope"), "holiday", "(scope = 'branch') = (branch_id IS NOT NULL)"
	)
	op.create_index(
		"uq_holiday_day_title_scope",
		"holiday",
		[
			"jdate",
			"title",
			"scope",
			sa.literal_column("coalesce(province_id, 0)"),
			sa.literal_column("coalesce(branch_id, 0)"),
		],
		unique=True,
	)
	op.execute(
		"ALTER TABLE work_location RENAME CONSTRAINT fk_work_location_province_id_province TO fk_branch_province_id_province"
	)
	op.execute("ALTER TABLE work_location RENAME CONSTRAINT uq_work_location_name TO uq_branch_name")
	op.execute("ALTER TABLE work_location RENAME CONSTRAINT pk_work_location TO pk_branch")
	op.execute("ALTER SEQUENCE IF EXISTS work_location_id_seq RENAME TO branch_id_seq")
	op.rename_table("work_location", "branch")
