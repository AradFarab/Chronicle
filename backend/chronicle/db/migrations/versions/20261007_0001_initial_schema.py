"""initial schema

The whole data model of docs/data-model.md: the jdate domain, 42 tables, and the triggers
that keep raw punches, the leave ledger and the audit trail append-only.

Revision ID: 0001
Revises:
Create Date: 2026-10-07 15:14:58.931053
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import chronicle.db.types
from chronicle.db.types import JDATE_PATTERN

APPEND_ONLY = ("raw_punch", "leave_ledger_entry", "audit_entry")
CIRCULAR_FKS = (
	("fk_department_default_approver_id_employee", "department"),
	("fk_department_deputy_id_employee", "department"),
	("fk_department_manager_id_employee", "department"),
	("fk_organization_ceo_id_employee", "organization"),
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
	op.execute(f"CREATE DOMAIN jdate AS char(10) CHECK (VALUE ~ '{JDATE_PATTERN}')")
	op.execute(
		"""
        CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END $$
        """
	)

	op.create_table(
		"app_user",
		sa.Column("username", sa.String(length=150), nullable=False),
		sa.Column("full_name", sa.String(length=200), nullable=False),
		sa.Column("password_hash", sa.Text(), nullable=True),
		sa.Column("language", sa.String(length=8), server_default="fa", nullable=False),
		sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint("username = lower(username)", name=op.f("ck_app_user_username_lower")),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
		sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
	)
	op.create_table(
		"approval_process",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("is_standard", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_process")),
		sa.UniqueConstraint("name", name=op.f("uq_approval_process_name")),
	)
	op.create_table(
		"department",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("parent_id", sa.BigInteger(), nullable=True),
		sa.Column("is_group", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("manager_id", sa.BigInteger(), nullable=True),
		sa.Column("default_approver_id", sa.BigInteger(), nullable=True),
		sa.Column("deputy_id", sa.BigInteger(), nullable=True),
		sa.Column("deputy_from", chronicle.db.types.JDate(), nullable=True),
		sa.Column("deputy_to", chronicle.db.types.JDate(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"deputy_to IS NULL OR deputy_from IS NULL OR deputy_to >= deputy_from",
			name=op.f("ck_department_deputy_range"),
		),
		sa.CheckConstraint("parent_id <> id", name=op.f("ck_department_not_own_parent")),
		sa.ForeignKeyConstraint(
			["parent_id"], ["department.id"], name=op.f("fk_department_parent_id_department")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_department")),
		sa.UniqueConstraint("name", name=op.f("uq_department_name")),
	)
	op.create_index(op.f("ix_department_parent_id"), "department", ["parent_id"], unique=False)
	op.create_table(
		"designation",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("hard_and_harmful", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("committee_ruling_no", sa.String(length=50), nullable=True),
		sa.Column("committee_ruling_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_designation")),
		sa.UniqueConstraint("name", name=op.f("uq_designation_name")),
	)
	op.create_table(
		"job",
		sa.Column("kind", sa.String(length=60), nullable=False),
		sa.Column(
			"payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False
		),
		sa.Column("dedup_key", sa.String(length=200), nullable=True),
		sa.Column("status", sa.String(length=10), server_default="queued", nullable=False),
		sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
		sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
		sa.Column("last_error", sa.Text(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_job_status_valid")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
	)
	op.create_index(
		"ix_job_queue", "job", ["run_after"], unique=False, postgresql_where=sa.text("status = 'queued'")
	)
	op.create_index(
		"uq_job_dedup_key_queued",
		"job",
		["dedup_key"],
		unique=True,
		postgresql_where=sa.text("status = 'queued'"),
	)
	op.create_table(
		"labor_rule_set",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("effective_from", chronicle.db.types.JDate(), nullable=False),
		sa.Column("is_legal_baseline", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("change_reason", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_labor_rule_set")),
		sa.UniqueConstraint("effective_from", name=op.f("uq_labor_rule_set_effective_from")),
		sa.UniqueConstraint("name", name=op.f("uq_labor_rule_set_name")),
	)
	op.create_index(
		"uq_labor_rule_set_baseline",
		"labor_rule_set",
		["is_legal_baseline"],
		unique=True,
		postgresql_where=sa.text("is_legal_baseline"),
	)
	op.create_table(
		"leave_type",
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("category", sa.String(length=30), nullable=False),
		sa.Column("is_paid", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("deducts_from_balance", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("allow_hourly", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("rule_limit", sa.String(length=60), nullable=True),
		sa.Column("max_days_per_request", sa.Numeric(precision=6, scale=2), nullable=True),
		sa.Column("once_in_service", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("is_standard", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"category IN ('earned', 'sick', 'unpaid', 'marriage_bereavement', 'hajj', 'maternity', 'paternity', 'other')",
			name=op.f("ck_leave_type_category_valid"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_type")),
		sa.UniqueConstraint("name", name=op.f("uq_leave_type_name")),
	)
	op.create_table(
		"province",
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_province")),
		sa.UniqueConstraint("name", name=op.f("uq_province_name")),
	)
	op.create_table(
		"punch_import_template",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("file_format", sa.String(length=20), server_default="excel", nullable=False),
		sa.Column("delimiter", sa.String(length=20), server_default="comma", nullable=False),
		sa.Column("encoding", sa.String(length=20), server_default="utf-8", nullable=False),
		sa.Column("has_header", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("skip_rows", sa.Integer(), server_default="0", nullable=False),
		sa.Column("user_id_column", sa.String(length=100), nullable=True),
		sa.Column("datetime_column", sa.String(length=100), nullable=True),
		sa.Column("date_column", sa.String(length=100), nullable=True),
		sa.Column("time_column", sa.String(length=100), nullable=True),
		sa.Column("date_calendar", sa.String(length=20), server_default="jalali", nullable=False),
		sa.Column("date_format", sa.String(length=20), server_default="YYYY/MM/DD", nullable=False),
		sa.Column("direction_column", sa.String(length=100), nullable=True),
		sa.Column("in_values", sa.String(length=200), nullable=True),
		sa.Column("out_values", sa.String(length=200), nullable=True),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"date_calendar IN ('jalali', 'gregorian')",
			name=op.f("ck_punch_import_template_date_calendar_valid"),
		),
		sa.CheckConstraint(
			"date_format IN ('YYYY/MM/DD', 'YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY')",
			name=op.f("ck_punch_import_template_date_format_valid"),
		),
		sa.CheckConstraint(
			"delimiter IN ('comma', 'tab', 'semicolon', 'pipe')",
			name=op.f("ck_punch_import_template_delimiter_valid"),
		),
		sa.CheckConstraint(
			"encoding IN ('utf-8', 'windows-1256')", name=op.f("ck_punch_import_template_encoding_valid")
		),
		sa.CheckConstraint(
			"file_format IN ('csv', 'excel', 'zkteco_usb')",
			name=op.f("ck_punch_import_template_file_format_valid"),
		),
		sa.CheckConstraint("skip_rows >= 0", name=op.f("ck_punch_import_template_skip_rows_non_negative")),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_punch_import_template")),
		sa.UniqueConstraint("name", name=op.f("uq_punch_import_template_name")),
	)
	op.create_table(
		"report_template",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("source", sa.String(length=20), server_default="summary", nullable=False),
		sa.Column("group_by", sa.String(length=20), nullable=True),
		sa.Column("time_unit", sa.String(length=20), server_default="hours_minutes", nullable=False),
		sa.Column("default_range", sa.String(length=20), server_default="current_month", nullable=False),
		sa.Column("export_format", sa.String(length=10), server_default="excel", nullable=False),
		sa.Column("text_delimiter", sa.String(length=20), server_default="comma", nullable=False),
		sa.Column("text_encoding", sa.String(length=20), server_default="utf-8", nullable=False),
		sa.Column("is_standard", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column(
			"shared_roles",
			postgresql.ARRAY(sa.String(length=20)),
			server_default=sa.text("'{}'"),
			nullable=False,
		),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"default_range IN ('current_month', 'previous_month', 'today', 'custom')",
			name=op.f("ck_report_template_default_range_valid"),
		),
		sa.CheckConstraint(
			"export_format IN ('excel', 'csv', 'text', 'pdf')",
			name=op.f("ck_report_template_export_format_valid"),
		),
		sa.CheckConstraint(
			"group_by IN ('employee', 'department', 'day')", name=op.f("ck_report_template_group_by_valid")
		),
		sa.CheckConstraint("source IN ('summary', 'daily')", name=op.f("ck_report_template_source_valid")),
		sa.CheckConstraint(
			"text_delimiter IN ('comma', 'tab', 'pipe', 'semicolon', 'fixed_width')",
			name=op.f("ck_report_template_text_delimiter_valid"),
		),
		sa.CheckConstraint(
			"text_encoding IN ('utf-8', 'utf-8-sig', 'windows-1256')",
			name=op.f("ck_report_template_text_encoding_valid"),
		),
		sa.CheckConstraint(
			"time_unit IN ('hours_minutes', 'decimal_hours', 'days')",
			name=op.f("ck_report_template_time_unit_valid"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_report_template")),
		sa.UniqueConstraint("name", name=op.f("uq_report_template_name")),
	)
	op.create_table(
		"shift",
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("shift_type", sa.String(length=20), server_default="fixed", nullable=False),
		sa.Column("color", sa.String(length=20), nullable=True),
		sa.Column("start_time", sa.Time(), nullable=False),
		sa.Column("end_time", sa.Time(), nullable=False),
		sa.Column("latest_start_time", sa.Time(), nullable=True),
		sa.Column("required_minutes", sa.Integer(), nullable=True),
		sa.Column("break_start_time", sa.Time(), nullable=True),
		sa.Column("break_end_time", sa.Time(), nullable=True),
		sa.Column("break_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("grace_late_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("grace_early_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("overtime_after_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"shift_type = 'fixed' OR required_minutes IS NOT NULL",
			name=op.f("ck_shift_flexible_needs_required_minutes"),
		),
		sa.CheckConstraint("shift_type IN ('fixed', 'flexible')", name=op.f("ck_shift_shift_type_valid")),
		sa.CheckConstraint(
			"(break_start_time IS NULL) = (break_end_time IS NULL)", name=op.f("ck_shift_break_window_pair")
		),
		sa.CheckConstraint(
			"grace_late_minutes >= 0 AND grace_early_minutes >= 0 AND overtime_after_minutes >= 0 AND break_minutes >= 0 AND (required_minutes IS NULL OR required_minutes > 0)",
			name=op.f("ck_shift_minutes_non_negative"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_shift")),
		sa.UniqueConstraint("name", name=op.f("uq_shift_name")),
	)
	op.create_table(
		"work_pattern",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("pattern_type", sa.String(length=20), server_default="weekly", nullable=False),
		sa.Column("weekly_rest_day", sa.SmallInteger(), server_default="6", nullable=True),
		sa.Column("cycle_start_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("change_reason", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"pattern_type = 'weekly' OR cycle_start_date IS NOT NULL",
			name=op.f("ck_work_pattern_rotating_needs_start"),
		),
		sa.CheckConstraint(
			"pattern_type IN ('weekly', 'rotating')", name=op.f("ck_work_pattern_pattern_type_valid")
		),
		sa.CheckConstraint(
			"weekly_rest_day BETWEEN 0 AND 6", name=op.f("ck_work_pattern_weekly_rest_day_range")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_work_pattern")),
		sa.UniqueConstraint("name", name=op.f("uq_work_pattern_name")),
	)
	op.create_table(
		"app_setting",
		sa.Column("key", sa.String(length=100), nullable=False),
		sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_by_id", sa.BigInteger(), nullable=True),
		sa.ForeignKeyConstraint(
			["updated_by_id"],
			["app_user.id"],
			name=op.f("fk_app_setting_updated_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
	)
	op.create_table(
		"approval_default",
		sa.Column("request_type", sa.String(length=30), nullable=False),
		sa.Column("process_id", sa.BigInteger(), nullable=False),
		sa.CheckConstraint(
			"request_type IN ('daily_leave', 'hourly_leave', 'mission', 'overtime', 'attendance_correction', 'operator_entry')",
			name=op.f("ck_approval_default_request_type_valid"),
		),
		sa.ForeignKeyConstraint(
			["process_id"],
			["approval_process.id"],
			name=op.f("fk_approval_default_process_id_approval_process"),
		),
		sa.PrimaryKeyConstraint("request_type", name=op.f("pk_approval_default")),
	)
	op.create_table(
		"attendance_period",
		sa.Column("jyear", sa.SmallInteger(), nullable=False),
		sa.Column("jmonth", sa.SmallInteger(), nullable=False),
		sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
		sa.Column("closed_by_id", sa.BigInteger(), nullable=True),
		sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"(status = 'closed') = (closed_at IS NOT NULL)", name=op.f("ck_attendance_period_closed_has_time")
		),
		sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_attendance_period_status_valid")),
		sa.CheckConstraint("jmonth BETWEEN 1 AND 12", name=op.f("ck_attendance_period_jmonth_range")),
		sa.ForeignKeyConstraint(
			["closed_by_id"],
			["app_user.id"],
			name=op.f("fk_attendance_period_closed_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_period")),
		sa.UniqueConstraint("jyear", "jmonth", name=op.f("uq_attendance_period_jyear_jmonth")),
	)
	op.create_table(
		"audit_entry",
		sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
		sa.Column("entity", sa.String(length=60), nullable=False),
		sa.Column("entity_id", sa.String(length=60), nullable=False),
		sa.Column("action", sa.String(length=20), nullable=False),
		sa.Column("user_id", sa.BigInteger(), nullable=True),
		sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("reason", sa.Text(), nullable=True),
		sa.Column(
			"changed_fields",
			postgresql.ARRAY(sa.String(length=60)),
			server_default=sa.text("'{}'"),
			nullable=False,
		),
		sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.CheckConstraint(
			"action IN ('insert', 'update', 'delete', 'submit', 'cancel', 'approve', 'reject', 'lock', 'reopen', 'refresh')",
			name=op.f("ck_audit_entry_action_valid"),
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["app_user.id"], name=op.f("fk_audit_entry_user_id_app_user"), ondelete="SET NULL"
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_entry")),
	)
	op.create_index("ix_audit_entry_entity", "audit_entry", ["entity", "entity_id"], unique=False)
	op.create_table(
		"branch",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("province_id", sa.BigInteger(), nullable=False),
		sa.Column("city", sa.String(length=100), nullable=True),
		sa.Column("address", sa.Text(), nullable=True),
		sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.ForeignKeyConstraint(
			["province_id"], ["province.id"], name=op.f("fk_branch_province_id_province")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_branch")),
		sa.UniqueConstraint("name", name=op.f("uq_branch_name")),
	)
	op.create_table(
		"calendar_year",
		sa.Column("jyear", sa.SmallInteger(), autoincrement=False, nullable=False),
		sa.Column("status", sa.String(length=20), server_default="predicted", nullable=False),
		sa.Column("source", sa.String(length=20), server_default="bundled", nullable=False),
		sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("refreshed_by_id", sa.BigInteger(), nullable=True),
		sa.Column("holiday_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("note", sa.Text(), nullable=True),
		sa.CheckConstraint(
			"source IN ('bundled', 'time_ir', 'file', 'manual')", name=op.f("ck_calendar_year_source_valid")
		),
		sa.CheckConstraint(
			"status IN ('confirmed', 'predicted')", name=op.f("ck_calendar_year_status_valid")
		),
		sa.CheckConstraint("jyear BETWEEN 1300 AND 1499", name=op.f("ck_calendar_year_jyear_range")),
		sa.ForeignKeyConstraint(
			["refreshed_by_id"],
			["app_user.id"],
			name=op.f("fk_calendar_year_refreshed_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("jyear", name=op.f("pk_calendar_year")),
	)
	op.create_table(
		"stored_file",
		sa.Column("filename", sa.String(length=255), nullable=False),
		sa.Column("content_type", sa.String(length=150), nullable=True),
		sa.Column("size", sa.BigInteger(), nullable=False),
		sa.Column("sha256", sa.String(length=64), nullable=False),
		sa.Column("storage_path", sa.String(length=255), nullable=False),
		sa.Column("is_private", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("created_by_id", sa.BigInteger(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.ForeignKeyConstraint(
			["created_by_id"],
			["app_user.id"],
			name=op.f("fk_stored_file_created_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_file")),
		sa.UniqueConstraint("storage_path", name=op.f("uq_stored_file_storage_path")),
	)
	op.create_table(
		"user_role",
		sa.Column("user_id", sa.BigInteger(), nullable=False),
		sa.Column("role", sa.String(length=20), nullable=False),
		sa.CheckConstraint(
			"role IN ('admin', 'operator', 'ceo', 'manager', 'employee')",
			name=op.f("ck_user_role_role_valid"),
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["app_user.id"], name=op.f("fk_user_role_user_id_app_user"), ondelete="CASCADE"
		),
		sa.PrimaryKeyConstraint("user_id", "role", name=op.f("pk_user_role")),
	)
	op.create_table(
		"user_session",
		sa.Column("token_hash", sa.String(length=64), nullable=False),
		sa.Column("user_id", sa.BigInteger(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column(
			"last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
		),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("user_agent", sa.Text(), nullable=True),
		sa.Column("ip", sa.String(length=64), nullable=True),
		sa.ForeignKeyConstraint(
			["user_id"], ["app_user.id"], name=op.f("fk_user_session_user_id_app_user"), ondelete="CASCADE"
		),
		sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_user_session")),
	)
	op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)
	op.create_table(
		"work_pattern_day",
		sa.Column("work_pattern_id", sa.BigInteger(), nullable=False),
		sa.Column("weekday", sa.SmallInteger(), nullable=True),
		sa.Column("cycle_day", sa.SmallInteger(), nullable=True),
		sa.Column("shift_id", sa.BigInteger(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"(weekday IS NULL) <> (cycle_day IS NULL)", name=op.f("ck_work_pattern_day_weekday_or_cycle_day")
		),
		sa.CheckConstraint("cycle_day >= 1", name=op.f("ck_work_pattern_day_cycle_day_positive")),
		sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_work_pattern_day_weekday_range")),
		sa.ForeignKeyConstraint(["shift_id"], ["shift.id"], name=op.f("fk_work_pattern_day_shift_id_shift")),
		sa.ForeignKeyConstraint(
			["work_pattern_id"],
			["work_pattern.id"],
			name=op.f("fk_work_pattern_day_work_pattern_id_work_pattern"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_work_pattern_day")),
		sa.UniqueConstraint(
			"work_pattern_id", "cycle_day", name=op.f("uq_work_pattern_day_work_pattern_id_cycle_day")
		),
		sa.UniqueConstraint(
			"work_pattern_id", "weekday", name=op.f("uq_work_pattern_day_work_pattern_id_weekday")
		),
	)
	op.create_table(
		"attendance_device",
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("adapter_type", sa.String(length=50), nullable=False),
		sa.Column("branch_id", sa.BigInteger(), nullable=True),
		sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("direction_mode", sa.String(length=20), server_default="from_device", nullable=False),
		sa.Column("host", sa.String(length=255), nullable=True),
		sa.Column("port", sa.Integer(), server_default="4370", nullable=False),
		sa.Column("comm_key_encrypted", sa.Text(), nullable=True),
		sa.Column("polling_interval_minutes", sa.Integer(), server_default="5", nullable=False),
		sa.Column("timeout_seconds", sa.Integer(), server_default="10", nullable=False),
		sa.Column("use_udp", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("last_sync_status", sa.String(length=10), nullable=True),
		sa.Column("punches_last_sync", sa.Integer(), server_default="0", nullable=False),
		sa.Column("last_punch_timestamp", sa.DateTime(), nullable=True),
		sa.Column("last_error", sa.Text(), nullable=True),
		sa.Column("model", sa.String(length=100), nullable=True),
		sa.Column("serial_number", sa.String(length=100), nullable=True),
		sa.Column("firmware", sa.String(length=100), nullable=True),
		sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("user_count", sa.Integer(), nullable=True),
		sa.Column("record_count", sa.Integer(), nullable=True),
		sa.Column("record_capacity", sa.Integer(), nullable=True),
		sa.Column("clock_drift_seconds", sa.Integer(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"direction_mode IN ('from_device', 'always_in', 'always_out', 'pair_by_order')",
			name=op.f("ck_attendance_device_direction_mode_valid"),
		),
		sa.CheckConstraint(
			"last_sync_status IN ('ok', 'error')", name=op.f("ck_attendance_device_last_sync_status_valid")
		),
		sa.CheckConstraint(
			"polling_interval_minutes >= 1 AND timeout_seconds >= 1",
			name=op.f("ck_attendance_device_intervals_positive"),
		),
		sa.CheckConstraint("port BETWEEN 1 AND 65535", name=op.f("ck_attendance_device_port_range")),
		sa.ForeignKeyConstraint(
			["branch_id"], ["branch.id"], name=op.f("fk_attendance_device_branch_id_branch")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_device")),
		sa.UniqueConstraint("name", name=op.f("uq_attendance_device_name")),
	)
	op.create_table(
		"employee",
		sa.Column("code", sa.String(length=30), nullable=False),
		sa.Column("first_name", sa.String(length=100), nullable=False),
		sa.Column("last_name", sa.String(length=100), nullable=False),
		sa.Column(
			"full_name",
			sa.String(length=201),
			sa.Computed("first_name || ' ' || last_name", persisted=True),
			nullable=False,
		),
		sa.Column("national_id", sa.String(length=10), nullable=True),
		sa.Column("gender", sa.String(length=10), nullable=True),
		sa.Column("mobile", sa.String(length=20), nullable=True),
		sa.Column("email", sa.String(length=150), nullable=True),
		sa.Column("user_id", sa.BigInteger(), nullable=True),
		sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
		sa.Column("contract_type", sa.String(length=20), server_default="full_time", nullable=False),
		sa.Column("start_date", chronicle.db.types.JDate(), nullable=False),
		sa.Column("end_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("branch_id", sa.BigInteger(), nullable=True),
		sa.Column("department_id", sa.BigInteger(), nullable=True),
		sa.Column("designation_id", sa.BigInteger(), nullable=True),
		sa.Column("reports_to_id", sa.BigInteger(), nullable=True),
		sa.Column("overtime_consent_on_file", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("overtime_consent_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("birth_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("biometric_consent_date", chronicle.db.types.JDate(), nullable=True),
		sa.Column("biometric_consent_file_id", sa.BigInteger(), nullable=True),
		sa.Column(
			"uses_card_instead_of_biometrics", sa.Boolean(), server_default=sa.text("false"), nullable=False
		),
		sa.Column("nursing_until", chronicle.db.types.JDate(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"contract_type IN ('full_time', 'part_time', 'hourly')",
			name=op.f("ck_employee_contract_type_valid"),
		),
		sa.CheckConstraint(
			"gender IS NULL OR gender IN ('male', 'female')", name=op.f("ck_employee_gender_valid")
		),
		sa.CheckConstraint("national_id ~ '^[0-9]{10}$'", name=op.f("ck_employee_national_id_digits")),
		sa.CheckConstraint(
			"status IN ('active', 'suspended', 'left')", name=op.f("ck_employee_status_valid")
		),
		sa.CheckConstraint(
			"end_date IS NULL OR end_date >= start_date", name=op.f("ck_employee_employment_range")
		),
		sa.CheckConstraint("reports_to_id <> id", name=op.f("ck_employee_not_own_manager")),
		sa.ForeignKeyConstraint(
			["biometric_consent_file_id"],
			["stored_file.id"],
			name=op.f("fk_employee_biometric_consent_file_id_stored_file"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(["branch_id"], ["branch.id"], name=op.f("fk_employee_branch_id_branch")),
		sa.ForeignKeyConstraint(
			["department_id"], ["department.id"], name=op.f("fk_employee_department_id_department")
		),
		sa.ForeignKeyConstraint(
			["designation_id"], ["designation.id"], name=op.f("fk_employee_designation_id_designation")
		),
		sa.ForeignKeyConstraint(
			["reports_to_id"],
			["employee.id"],
			name=op.f("fk_employee_reports_to_id_employee"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["app_user.id"], name=op.f("fk_employee_user_id_app_user"), ondelete="SET NULL"
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_employee")),
		sa.UniqueConstraint("code", name=op.f("uq_employee_code")),
		sa.UniqueConstraint("national_id", name=op.f("uq_employee_national_id")),
		sa.UniqueConstraint("user_id", name=op.f("uq_employee_user_id")),
	)
	op.create_index("ix_employee_department_id_status", "employee", ["department_id", "status"], unique=False)
	op.create_table(
		"holiday",
		sa.Column("jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column(
			"jyear",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 1, 4))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column(
			"jmonth",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 6, 2))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column("title", sa.String(length=200), nullable=False),
		sa.Column("holiday_type", sa.String(length=30), nullable=False),
		sa.Column("status", sa.String(length=20), server_default="confirmed", nullable=False),
		sa.Column("scope", sa.String(length=20), server_default="country", nullable=False),
		sa.Column("province_id", sa.BigInteger(), nullable=True),
		sa.Column("branch_id", sa.BigInteger(), nullable=True),
		sa.Column("closure_pay_mode", sa.String(length=20), nullable=True),
		sa.Column("source", sa.String(length=20), server_default="manual", nullable=False),
		sa.Column("source_key", sa.String(length=100), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("change_reason", sa.Text(), nullable=True),
		sa.Column("edited_by_operator", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"(scope = 'branch') = (branch_id IS NOT NULL)", name=op.f("ck_holiday_branch_scope")
		),
		sa.CheckConstraint(
			"(scope = 'province') = (province_id IS NOT NULL)", name=op.f("ck_holiday_province_scope")
		),
		sa.CheckConstraint(
			"closure_pay_mode IS NULL OR (holiday_type = 'office_closure' AND closure_pay_mode IN ('paid_holiday', 'employer_paid', 'workday'))",
			name=op.f("ck_holiday_closure_pay_mode_valid"),
		),
		sa.CheckConstraint(
			"holiday_type IN ('official_solar', 'official_lunar', 'official_occasional', 'office_closure', 'company_internal')",
			name=op.f("ck_holiday_holiday_type_valid"),
		),
		sa.CheckConstraint(
			"scope IN ('country', 'province', 'branch', 'company')", name=op.f("ck_holiday_scope_valid")
		),
		sa.CheckConstraint(
			"source IN ('bundled', 'time_ir', 'file', 'manual')", name=op.f("ck_holiday_source_valid")
		),
		sa.CheckConstraint("status IN ('confirmed', 'predicted')", name=op.f("ck_holiday_status_valid")),
		sa.ForeignKeyConstraint(["branch_id"], ["branch.id"], name=op.f("fk_holiday_branch_id_branch")),
		sa.ForeignKeyConstraint(
			["province_id"], ["province.id"], name=op.f("fk_holiday_province_id_province")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_holiday")),
	)
	op.create_index("ix_holiday_jdate", "holiday", ["jdate"], unique=False)
	op.create_index("ix_holiday_jyear", "holiday", ["jyear"], unique=False)
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
	op.create_table(
		"organization",
		sa.Column("id", sa.SmallInteger(), nullable=False),
		sa.Column("name", sa.String(length=200), nullable=False),
		sa.Column("legal_name", sa.String(length=200), nullable=True),
		sa.Column("national_id", sa.String(length=20), nullable=True),
		sa.Column("economic_code", sa.String(length=20), nullable=True),
		sa.Column("insurance_workshop_code", sa.String(length=20), nullable=True),
		sa.Column("ceo_id", sa.BigInteger(), nullable=True),
		sa.Column("phone", sa.String(length=30), nullable=True),
		sa.Column("address", sa.Text(), nullable=True),
		sa.Column("logo_file_id", sa.BigInteger(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint("id = 1", name=op.f("ck_organization_single_row")),
		sa.ForeignKeyConstraint(
			["logo_file_id"],
			["stored_file.id"],
			name=op.f("fk_organization_logo_file_id_stored_file"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_organization")),
	)
	op.create_table(
		"approval_override",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("request_type", sa.String(length=30), nullable=False),
		sa.Column("process_id", sa.BigInteger(), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"request_type IN ('daily_leave', 'hourly_leave', 'mission', 'overtime', 'attendance_correction')",
			name=op.f("ck_approval_override_request_type_valid"),
		),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_approval_override_employee_id_employee"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["process_id"],
			["approval_process.id"],
			name=op.f("fk_approval_override_process_id_approval_process"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_override")),
		sa.UniqueConstraint(
			"employee_id", "request_type", name=op.f("uq_approval_override_employee_id_request_type")
		),
	)
	op.create_table(
		"approval_process_step",
		sa.Column("process_id", sa.BigInteger(), nullable=False),
		sa.Column("position", sa.SmallInteger(), nullable=False),
		sa.Column("approver_type", sa.String(length=30), nullable=False),
		sa.Column("approver_id", sa.BigInteger(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"(approver_type = 'specific_person') = (approver_id IS NOT NULL)",
			name=op.f("ck_approval_process_step_person_matches_type"),
		),
		sa.CheckConstraint(
			"approver_type IN ('direct_manager', 'parent_department_manager', 'ceo', 'specific_person')",
			name=op.f("ck_approval_process_step_approver_type_valid"),
		),
		sa.ForeignKeyConstraint(
			["approver_id"], ["employee.id"], name=op.f("fk_approval_process_step_approver_id_employee")
		),
		sa.ForeignKeyConstraint(
			["process_id"],
			["approval_process.id"],
			name=op.f("fk_approval_process_step_process_id_approval_process"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_process_step")),
		sa.UniqueConstraint(
			"process_id", "position", name=op.f("uq_approval_process_step_process_id_position")
		),
	)
	op.create_table(
		"daily_attendance",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column(
			"jyear",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 1, 4))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column(
			"jmonth",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 6, 2))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column("weekday", sa.SmallInteger(), nullable=False),
		sa.Column("status", sa.String(length=20), nullable=False),
		sa.Column("day_type", sa.String(length=20), nullable=False),
		sa.Column("holiday_title", sa.Text(), nullable=True),
		sa.Column("department_id", sa.BigInteger(), nullable=True),
		sa.Column("branch_id", sa.BigInteger(), nullable=True),
		sa.Column("designation_id", sa.BigInteger(), nullable=True),
		sa.Column("work_pattern_id", sa.BigInteger(), nullable=True),
		sa.Column("shift_id", sa.BigInteger(), nullable=True),
		sa.Column("rest_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("rule_set_id", sa.BigInteger(), nullable=True),
		sa.Column("first_in", sa.Time(), nullable=True),
		sa.Column("last_out", sa.Time(), nullable=True),
		sa.Column("punch_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("required_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("worked_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("credited_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("late_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("early_leave_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("absence_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("absent_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("leave_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("leave_days", sa.Numeric(precision=7, scale=4), server_default="0", nullable=False),
		sa.Column("mission_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("nursing_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("extra_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("overtime_normal_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("overtime_exceptional_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("overtime_emergency_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("unapproved_extra_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("night_work_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("rest_day_work_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("friday_premium_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("holiday_work_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("company_holiday_work_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column(
			"warnings", postgresql.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False
		),
		sa.Column(
			"calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
		),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"day_type IN ('workday', 'friday', 'official_holiday', 'company_holiday')",
			name=op.f("ck_daily_attendance_day_type_valid"),
		),
		sa.CheckConstraint(
			"status IN ('present', 'absent', 'incomplete', 'leave', 'mission', 'holiday', 'rest_day', 'not_scheduled')",
			name=op.f("ck_daily_attendance_status_valid"),
		),
		sa.ForeignKeyConstraint(
			["branch_id"], ["branch.id"], name=op.f("fk_daily_attendance_branch_id_branch")
		),
		sa.ForeignKeyConstraint(
			["department_id"], ["department.id"], name=op.f("fk_daily_attendance_department_id_department")
		),
		sa.ForeignKeyConstraint(
			["designation_id"],
			["designation.id"],
			name=op.f("fk_daily_attendance_designation_id_designation"),
		),
		sa.ForeignKeyConstraint(
			["employee_id"], ["employee.id"], name=op.f("fk_daily_attendance_employee_id_employee")
		),
		sa.ForeignKeyConstraint(
			["rule_set_id"],
			["labor_rule_set.id"],
			name=op.f("fk_daily_attendance_rule_set_id_labor_rule_set"),
		),
		sa.ForeignKeyConstraint(["shift_id"], ["shift.id"], name=op.f("fk_daily_attendance_shift_id_shift")),
		sa.ForeignKeyConstraint(
			["work_pattern_id"],
			["work_pattern.id"],
			name=op.f("fk_daily_attendance_work_pattern_id_work_pattern"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_attendance")),
		sa.UniqueConstraint("employee_id", "jdate", name=op.f("uq_daily_attendance_employee_id_jdate")),
	)
	op.create_index(
		"ix_daily_attendance_department_id_jdate",
		"daily_attendance",
		["department_id", "jdate"],
		unique=False,
	)
	op.create_index("ix_daily_attendance_jdate", "daily_attendance", ["jdate"], unique=False)
	op.create_table(
		"device_user_map",
		sa.Column("device_id", sa.BigInteger(), nullable=False),
		sa.Column("device_user_id", sa.String(length=50), nullable=False),
		sa.Column("device_user_name", sa.String(length=150), nullable=True),
		sa.Column("card", sa.String(length=50), nullable=True),
		sa.Column("employee_id", sa.BigInteger(), nullable=True),
		sa.Column("valid_from", chronicle.db.types.JDate(), nullable=True),
		sa.Column("valid_to", chronicle.db.types.JDate(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
			name=op.f("ck_device_user_map_valid_range"),
		),
		sa.ForeignKeyConstraint(
			["device_id"],
			["attendance_device.id"],
			name=op.f("fk_device_user_map_device_id_attendance_device"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_device_user_map_employee_id_employee"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_device_user_map")),
		sa.UniqueConstraint(
			"device_id",
			"device_user_id",
			"valid_from",
			name=op.f("uq_device_user_map_device_id_device_user_id_valid_from"),
			postgresql_nulls_not_distinct=True,
		),
	)
	op.create_index("ix_device_user_map_employee_id", "device_user_map", ["employee_id"], unique=False)
	op.create_table(
		"punch_import",
		sa.Column("device_id", sa.BigInteger(), nullable=False),
		sa.Column("template_id", sa.BigInteger(), nullable=False),
		sa.Column("file_id", sa.BigInteger(), nullable=False),
		sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
		sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
		sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("existing_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("error_log", sa.Text(), nullable=True),
		sa.Column("created_by_id", sa.BigInteger(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"status IN ('pending', 'imported', 'failed')", name=op.f("ck_punch_import_status_valid")
		),
		sa.ForeignKeyConstraint(
			["created_by_id"],
			["app_user.id"],
			name=op.f("fk_punch_import_created_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["device_id"], ["attendance_device.id"], name=op.f("fk_punch_import_device_id_attendance_device")
		),
		sa.ForeignKeyConstraint(
			["file_id"], ["stored_file.id"], name=op.f("fk_punch_import_file_id_stored_file")
		),
		sa.ForeignKeyConstraint(
			["template_id"],
			["punch_import_template.id"],
			name=op.f("fk_punch_import_template_id_punch_import_template"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_punch_import")),
	)
	op.create_table(
		"request",
		sa.Column("kind", sa.String(length=20), nullable=False),
		sa.Column("request_type", sa.String(length=30), nullable=False),
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
		sa.Column("start_jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column("end_jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column(
			"jyear",
			sa.SmallInteger(),
			sa.Computed("(substr(start_jdate, 1, 4))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column("reason", sa.Text(), nullable=True),
		sa.Column("approval_process_id", sa.BigInteger(), nullable=True),
		sa.Column("entered_by_id", sa.BigInteger(), nullable=True),
		sa.Column("entered_by_operator", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("pending_approver_id", sa.BigInteger(), nullable=True),
		sa.Column("pending_approver_user_id", sa.BigInteger(), nullable=True),
		sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column(
			"number",
			sa.String(length=20),
			sa.Computed(
				"CASE kind WHEN 'leave' THEN 'LV-' WHEN 'mission' THEN 'MS-' WHEN 'overtime' THEN 'OT-' ELSE 'COR-' END || lpad(id::text, 5, '0')",
				persisted=True,
			),
			nullable=False,
		),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"(kind = 'leave' AND request_type IN ('daily_leave', 'hourly_leave')) OR (kind = 'mission' AND request_type = 'mission') OR (kind = 'overtime' AND request_type = 'overtime') OR (kind = 'correction' AND request_type = 'attendance_correction')",
			name=op.f("ck_request_type_matches_kind"),
		),
		sa.CheckConstraint(
			"(status = 'pending') OR pending_approver_user_id IS NULL",
			name=op.f("ck_request_pending_only_when_pending"),
		),
		sa.CheckConstraint(
			"kind IN ('leave', 'mission', 'overtime', 'correction')", name=op.f("ck_request_kind_valid")
		),
		sa.CheckConstraint(
			"request_type IN ('daily_leave', 'hourly_leave', 'mission', 'overtime', 'attendance_correction')",
			name=op.f("ck_request_request_type_valid"),
		),
		sa.CheckConstraint(
			"status IN ('pending', 'approved', 'rejected', 'cancelled')", name=op.f("ck_request_status_valid")
		),
		sa.CheckConstraint("end_jdate >= start_jdate", name=op.f("ck_request_date_range")),
		sa.ForeignKeyConstraint(
			["approval_process_id"],
			["approval_process.id"],
			name=op.f("fk_request_approval_process_id_approval_process"),
		),
		sa.ForeignKeyConstraint(
			["employee_id"], ["employee.id"], name=op.f("fk_request_employee_id_employee")
		),
		sa.ForeignKeyConstraint(
			["entered_by_id"],
			["app_user.id"],
			name=op.f("fk_request_entered_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["pending_approver_id"], ["employee.id"], name=op.f("fk_request_pending_approver_id_employee")
		),
		sa.ForeignKeyConstraint(
			["pending_approver_user_id"],
			["app_user.id"],
			name=op.f("fk_request_pending_approver_user_id_app_user"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_request")),
	)
	op.create_index(
		"ix_request_employee_id_start_jdate", "request", ["employee_id", "start_jdate"], unique=False
	)
	op.create_index(
		"ix_request_inbox",
		"request",
		["pending_approver_user_id"],
		unique=False,
		postgresql_where=sa.text("status = 'pending'"),
	)
	op.create_table(
		"shift_override",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column("shift_id", sa.BigInteger(), nullable=True),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_shift_override_employee_id_employee"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(["shift_id"], ["shift.id"], name=op.f("fk_shift_override_shift_id_shift")),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_shift_override")),
		sa.UniqueConstraint("employee_id", "jdate", name=op.f("uq_shift_override_employee_id_jdate")),
	)
	op.create_table(
		"work_pattern_assignment",
		sa.Column("target_type", sa.String(length=20), nullable=False),
		sa.Column("employee_id", sa.BigInteger(), nullable=True),
		sa.Column("designation_id", sa.BigInteger(), nullable=True),
		sa.Column("department_id", sa.BigInteger(), nullable=True),
		sa.Column("work_pattern_id", sa.BigInteger(), nullable=False),
		sa.Column("valid_from", chronicle.db.types.JDate(), nullable=False),
		sa.Column("valid_to", chronicle.db.types.JDate(), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"(target_type = 'employee') = (employee_id IS NOT NULL) AND (target_type = 'designation') = (designation_id IS NOT NULL) AND (target_type = 'department') = (department_id IS NOT NULL)",
			name=op.f("ck_work_pattern_assignment_target_matches_type"),
		),
		sa.CheckConstraint(
			"target_type IN ('employee', 'designation', 'department', 'company')",
			name=op.f("ck_work_pattern_assignment_target_type_valid"),
		),
		sa.CheckConstraint(
			"valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_work_pattern_assignment_valid_range")
		),
		sa.ForeignKeyConstraint(
			["department_id"],
			["department.id"],
			name=op.f("fk_work_pattern_assignment_department_id_department"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["designation_id"],
			["designation.id"],
			name=op.f("fk_work_pattern_assignment_designation_id_designation"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_work_pattern_assignment_employee_id_employee"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["work_pattern_id"],
			["work_pattern.id"],
			name=op.f("fk_work_pattern_assignment_work_pattern_id_work_pattern"),
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_work_pattern_assignment")),
	)
	op.create_index(
		op.f("ix_work_pattern_assignment_employee_id"),
		"work_pattern_assignment",
		["employee_id"],
		unique=False,
	)
	op.create_table(
		"daily_attendance_leave",
		sa.Column("attendance_id", sa.BigInteger(), nullable=False),
		sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
		sa.Column("minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("days", sa.Numeric(precision=7, scale=4), server_default="0", nullable=False),
		sa.ForeignKeyConstraint(
			["attendance_id"],
			["daily_attendance.id"],
			name=op.f("fk_daily_attendance_leave_attendance_id_daily_attendance"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["leave_type_id"],
			["leave_type.id"],
			name=op.f("fk_daily_attendance_leave_leave_type_id_leave_type"),
		),
		sa.PrimaryKeyConstraint("attendance_id", "leave_type_id", name=op.f("pk_daily_attendance_leave")),
	)
	op.create_table(
		"leave_ledger_entry",
		sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
		sa.Column("entry_type", sa.String(length=20), nullable=False),
		sa.Column("jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column(
			"jyear",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 1, 4))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column("days", sa.Numeric(precision=9, scale=4), nullable=False),
		sa.Column("request_id", sa.BigInteger(), nullable=True),
		sa.Column("note", sa.Text(), nullable=True),
		sa.Column("created_by_id", sa.BigInteger(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"entry_type IN ('allocation', 'usage', 'reversal', 'carry_over', 'expiry', 'adjustment')",
			name=op.f("ck_leave_ledger_entry_entry_type_valid"),
		),
		sa.ForeignKeyConstraint(
			["created_by_id"],
			["app_user.id"],
			name=op.f("fk_leave_ledger_entry_created_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["employee_id"], ["employee.id"], name=op.f("fk_leave_ledger_entry_employee_id_employee")
		),
		sa.ForeignKeyConstraint(
			["leave_type_id"], ["leave_type.id"], name=op.f("fk_leave_ledger_entry_leave_type_id_leave_type")
		),
		sa.ForeignKeyConstraint(
			["request_id"], ["request.id"], name=op.f("fk_leave_ledger_entry_request_id_request")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_ledger_entry")),
	)
	op.create_index(
		"ix_leave_ledger_entry_balance",
		"leave_ledger_entry",
		["employee_id", "leave_type_id", "jdate"],
		unique=False,
	)
	op.create_table(
		"leave_request",
		sa.Column("request_id", sa.BigInteger(), nullable=False),
		sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
		sa.Column("unit", sa.String(length=10), nullable=False),
		sa.Column("from_time", sa.Time(), nullable=True),
		sa.Column("to_time", sa.Time(), nullable=True),
		sa.Column("total_days", sa.Numeric(precision=7, scale=4), server_default="0", nullable=False),
		sa.Column("total_minutes", sa.Integer(), server_default="0", nullable=False),
		sa.Column("attachment_file_id", sa.BigInteger(), nullable=True),
		sa.CheckConstraint(
			"(unit = 'hourly') = (from_time IS NOT NULL AND to_time IS NOT NULL)",
			name=op.f("ck_leave_request_times_match_unit"),
		),
		sa.CheckConstraint("unit IN ('daily', 'hourly')", name=op.f("ck_leave_request_unit_valid")),
		sa.CheckConstraint(
			"from_time IS NULL OR to_time > from_time", name=op.f("ck_leave_request_time_range")
		),
		sa.ForeignKeyConstraint(
			["attachment_file_id"],
			["stored_file.id"],
			name=op.f("fk_leave_request_attachment_file_id_stored_file"),
		),
		sa.ForeignKeyConstraint(
			["leave_type_id"], ["leave_type.id"], name=op.f("fk_leave_request_leave_type_id_leave_type")
		),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_leave_request_request_id_request"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("request_id", name=op.f("pk_leave_request")),
	)
	op.create_table(
		"mission_request",
		sa.Column("request_id", sa.BigInteger(), nullable=False),
		sa.Column("unit", sa.String(length=10), nullable=False),
		sa.Column("destination", sa.String(length=200), nullable=True),
		sa.Column("from_time", sa.Time(), nullable=True),
		sa.Column("to_time", sa.Time(), nullable=True),
		sa.CheckConstraint(
			"(unit = 'hourly') = (from_time IS NOT NULL AND to_time IS NOT NULL)",
			name=op.f("ck_mission_request_times_match_unit"),
		),
		sa.CheckConstraint("unit IN ('daily', 'hourly')", name=op.f("ck_mission_request_unit_valid")),
		sa.CheckConstraint(
			"from_time IS NULL OR to_time > from_time", name=op.f("ck_mission_request_time_range")
		),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_mission_request_request_id_request"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("request_id", name=op.f("pk_mission_request")),
	)
	op.create_table(
		"overtime_request",
		sa.Column("request_id", sa.BigInteger(), nullable=False),
		sa.Column("overtime_kind", sa.String(length=20), server_default="normal", nullable=False),
		sa.Column("minutes", sa.Integer(), nullable=False),
		sa.Column("from_time", sa.Time(), nullable=True),
		sa.Column("to_time", sa.Time(), nullable=True),
		sa.Column("assigned_by_manager", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.CheckConstraint(
			"overtime_kind IN ('normal', 'exceptional', 'emergency')",
			name=op.f("ck_overtime_request_overtime_kind_valid"),
		),
		sa.CheckConstraint("minutes > 0", name=op.f("ck_overtime_request_minutes_positive")),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_overtime_request_request_id_request"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("request_id", name=op.f("pk_overtime_request")),
	)
	op.create_table(
		"raw_punch",
		sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
		sa.Column("device_id", sa.BigInteger(), nullable=False),
		sa.Column("device_user_id", sa.String(length=50), nullable=False),
		sa.Column("jdate", chronicle.db.types.JDate(), nullable=False),
		sa.Column(
			"jyear",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 1, 4))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column(
			"jmonth",
			sa.SmallInteger(),
			sa.Computed("(substr(jdate, 6, 2))::smallint", persisted=True),
			nullable=False,
		),
		sa.Column("time", sa.Time(), nullable=False),
		sa.Column("direction", sa.String(length=10), nullable=False),
		sa.Column("reported_direction", sa.String(length=10), nullable=False),
		sa.Column("is_duplicate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("source", sa.String(length=20), nullable=False),
		sa.Column("punch_import_id", sa.BigInteger(), nullable=True),
		sa.Column("verify_type", sa.String(length=30), nullable=True),
		sa.Column("device_timestamp", sa.DateTime(), nullable=True),
		sa.Column("dedup_key", sa.String(length=64), nullable=False),
		sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"direction IN ('in', 'out', 'unknown')", name=op.f("ck_raw_punch_direction_valid")
		),
		sa.CheckConstraint(
			"reported_direction IN ('in', 'out', 'unknown')",
			name=op.f("ck_raw_punch_reported_direction_valid"),
		),
		sa.CheckConstraint("source IN ('device', 'file_import')", name=op.f("ck_raw_punch_source_valid")),
		sa.ForeignKeyConstraint(
			["device_id"], ["attendance_device.id"], name=op.f("fk_raw_punch_device_id_attendance_device")
		),
		sa.ForeignKeyConstraint(
			["punch_import_id"], ["punch_import.id"], name=op.f("fk_raw_punch_punch_import_id_punch_import")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_punch")),
		sa.UniqueConstraint("dedup_key", name=op.f("uq_raw_punch_dedup_key")),
	)
	op.create_index(
		"ix_raw_punch_device_user_day", "raw_punch", ["device_id", "device_user_id", "jdate"], unique=False
	)
	op.create_index("ix_raw_punch_jdate", "raw_punch", ["jdate"], unique=False)
	op.create_table(
		"request_approval",
		sa.Column("request_id", sa.BigInteger(), nullable=False),
		sa.Column("step", sa.SmallInteger(), nullable=False),
		sa.Column("approver_type", sa.String(length=30), nullable=False),
		sa.Column("approver_id", sa.BigInteger(), nullable=True),
		sa.Column("approver_user_id", sa.BigInteger(), nullable=True),
		sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
		sa.Column("acted_by_id", sa.BigInteger(), nullable=True),
		sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("comment", sa.Text(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"approver_type IN ('direct_manager', 'parent_department_manager', 'ceo', 'specific_person', 'employee_acceptance')",
			name=op.f("ck_request_approval_approver_type_valid"),
		),
		sa.CheckConstraint(
			"status IN ('pending', 'approved', 'rejected', 'skipped')",
			name=op.f("ck_request_approval_status_valid"),
		),
		sa.ForeignKeyConstraint(
			["acted_by_id"], ["app_user.id"], name=op.f("fk_request_approval_acted_by_id_app_user")
		),
		sa.ForeignKeyConstraint(
			["approver_id"], ["employee.id"], name=op.f("fk_request_approval_approver_id_employee")
		),
		sa.ForeignKeyConstraint(
			["approver_user_id"], ["app_user.id"], name=op.f("fk_request_approval_approver_user_id_app_user")
		),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_request_approval_request_id_request"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_request_approval")),
		sa.UniqueConstraint("request_id", "step", name=op.f("uq_request_approval_request_id_step")),
	)
	op.create_table(
		"correction_item",
		sa.Column("request_id", sa.BigInteger(), nullable=False),
		sa.Column("position", sa.SmallInteger(), nullable=False),
		sa.Column("action", sa.String(length=20), nullable=False),
		sa.Column("time", sa.Time(), nullable=True),
		sa.Column("direction", sa.String(length=10), server_default="unknown", nullable=False),
		sa.Column("raw_punch_id", sa.BigInteger(), nullable=True),
		sa.Column("note", sa.String(length=200), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"(action = 'add_punch' AND time IS NOT NULL AND raw_punch_id IS NULL) OR (action = 'ignore_punch' AND raw_punch_id IS NOT NULL)",
			name=op.f("ck_correction_item_action_fields"),
		),
		sa.CheckConstraint(
			"action IN ('add_punch', 'ignore_punch')", name=op.f("ck_correction_item_action_valid")
		),
		sa.CheckConstraint(
			"direction IN ('in', 'out', 'unknown')", name=op.f("ck_correction_item_direction_valid")
		),
		sa.ForeignKeyConstraint(
			["raw_punch_id"], ["raw_punch.id"], name=op.f("fk_correction_item_raw_punch_id_raw_punch")
		),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_correction_item_request_id_request"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_correction_item")),
		sa.UniqueConstraint("request_id", "position", name=op.f("uq_correction_item_request_id_position")),
	)

	# Circular references (department and organization ↔ employee) are added after both tables exist.
	# Circular references (department and organization -> employee) are added once both tables exist.
	op.create_foreign_key(
		op.f("fk_department_default_approver_id_employee"),
		"department",
		"employee",
		["default_approver_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_foreign_key(
		op.f("fk_department_deputy_id_employee"),
		"department",
		"employee",
		["deputy_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_foreign_key(
		op.f("fk_department_manager_id_employee"),
		"department",
		"employee",
		["manager_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_foreign_key(
		op.f("fk_organization_ceo_id_employee"),
		"organization",
		"employee",
		["ceo_id"],
		["id"],
		ondelete="SET NULL",
	)
	for table in APPEND_ONLY:
		op.execute(
			f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
			"FOR EACH ROW EXECUTE FUNCTION forbid_change()"
		)
		op.execute(
			f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
			"FOR EACH STATEMENT EXECUTE FUNCTION forbid_change()"
		)


def downgrade() -> None:
	for table in APPEND_ONLY:
		op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
		op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
	for name, table in CIRCULAR_FKS:
		op.drop_constraint(name, table, type_="foreignkey")

	op.drop_table("correction_item")
	op.drop_table("request_approval")
	op.drop_index("ix_raw_punch_jdate", table_name="raw_punch")
	op.drop_index("ix_raw_punch_device_user_day", table_name="raw_punch")
	op.drop_table("raw_punch")
	op.drop_table("overtime_request")
	op.drop_table("mission_request")
	op.drop_table("leave_request")
	op.drop_index("ix_leave_ledger_entry_balance", table_name="leave_ledger_entry")
	op.drop_table("leave_ledger_entry")
	op.drop_table("daily_attendance_leave")
	op.drop_index(op.f("ix_work_pattern_assignment_employee_id"), table_name="work_pattern_assignment")
	op.drop_table("work_pattern_assignment")
	op.drop_table("shift_override")
	op.drop_index("ix_request_inbox", table_name="request", postgresql_where=sa.text("status = 'pending'"))
	op.drop_index("ix_request_employee_id_start_jdate", table_name="request")
	op.drop_table("request")
	op.drop_table("punch_import")
	op.drop_index("ix_device_user_map_employee_id", table_name="device_user_map")
	op.drop_table("device_user_map")
	op.drop_index("ix_daily_attendance_jdate", table_name="daily_attendance")
	op.drop_index("ix_daily_attendance_department_id_jdate", table_name="daily_attendance")
	op.drop_table("daily_attendance")
	op.drop_table("approval_process_step")
	op.drop_table("approval_override")
	op.drop_table("organization")
	op.drop_index("uq_holiday_day_title_scope", table_name="holiday")
	op.drop_index("ix_holiday_jyear", table_name="holiday")
	op.drop_index("ix_holiday_jdate", table_name="holiday")
	op.drop_table("holiday")
	op.drop_index("ix_employee_department_id_status", table_name="employee")
	op.drop_table("employee")
	op.drop_table("attendance_device")
	op.drop_table("work_pattern_day")
	op.drop_index(op.f("ix_user_session_user_id"), table_name="user_session")
	op.drop_table("user_session")
	op.drop_table("user_role")
	op.drop_table("stored_file")
	op.drop_table("calendar_year")
	op.drop_table("branch")
	op.drop_index("ix_audit_entry_entity", table_name="audit_entry")
	op.drop_table("audit_entry")
	op.drop_table("attendance_period")
	op.drop_table("approval_default")
	op.drop_table("app_setting")
	op.drop_table("work_pattern")
	op.drop_table("shift")
	op.drop_table("report_template")
	op.drop_table("punch_import_template")
	op.drop_table("province")
	op.drop_table("leave_type")
	op.drop_index(
		"uq_labor_rule_set_baseline",
		table_name="labor_rule_set",
		postgresql_where=sa.text("is_legal_baseline"),
	)
	op.drop_table("labor_rule_set")
	op.drop_index("uq_job_dedup_key_queued", table_name="job", postgresql_where=sa.text("status = 'queued'"))
	op.drop_index("ix_job_queue", table_name="job", postgresql_where=sa.text("status = 'queued'"))
	op.drop_table("job")
	op.drop_table("designation")
	op.drop_index(op.f("ix_department_parent_id"), table_name="department")
	op.drop_table("department")
	op.drop_table("approval_process")
	op.drop_table("app_user")

	op.execute("DROP FUNCTION IF EXISTS forbid_change()")
	op.execute("DROP DOMAIN IF EXISTS jdate")
