"""payslips: the pages of the finance software's PDF and the SMS links to them

``payslip`` is one stored PDF page per employee and Jalali month, ``payslip_rejection`` the pages
that could not be matched, ``payslip_link`` the private link sent by SMS (at most one active per
payslip, enforced by a partial unique index) and ``payslip_view`` each opening of a link.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"payslip",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("jyear", sa.SmallInteger(), nullable=False),
		sa.Column("jmonth", sa.SmallInteger(), nullable=False),
		sa.Column("file_id", sa.BigInteger(), nullable=False),
		sa.Column("source_name", sa.String(length=255), nullable=True),
		sa.Column("source_page", sa.Integer(), nullable=True),
		sa.Column("national_status", sa.String(length=10), server_default="unknown", nullable=False),
		sa.Column("uploaded_by_id", sa.BigInteger(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"national_status IN ('match', 'mismatch', 'unknown')",
			name=op.f("ck_payslip_national_status_valid"),
		),
		sa.CheckConstraint("jyear BETWEEN 1300 AND 1499", name=op.f("ck_payslip_jyear_valid")),
		sa.CheckConstraint("jmonth BETWEEN 1 AND 12", name=op.f("ck_payslip_jmonth_valid")),
		sa.ForeignKeyConstraint(
			["employee_id"], ["employee.id"], name=op.f("fk_payslip_employee_id_employee")
		),
		sa.ForeignKeyConstraint(["file_id"], ["stored_file.id"], name=op.f("fk_payslip_file_id_stored_file")),
		sa.ForeignKeyConstraint(
			["uploaded_by_id"],
			["app_user.id"],
			name=op.f("fk_payslip_uploaded_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_payslip")),
		sa.UniqueConstraint(
			"employee_id", "jyear", "jmonth", name=op.f("uq_payslip_employee_id_jyear_jmonth")
		),
	)
	op.create_index("ix_payslip_jyear_jmonth", "payslip", ["jyear", "jmonth"], unique=False)

	op.create_table(
		"payslip_rejection",
		sa.Column("jyear", sa.SmallInteger(), nullable=False),
		sa.Column("jmonth", sa.SmallInteger(), nullable=False),
		sa.Column("source_name", sa.String(length=255), nullable=False),
		sa.Column("page_no", sa.Integer(), nullable=True),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint("jmonth BETWEEN 1 AND 12", name=op.f("ck_payslip_rejection_jmonth_valid")),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_payslip_rejection")),
	)
	op.create_index(
		"ix_payslip_rejection_jyear_jmonth", "payslip_rejection", ["jyear", "jmonth"], unique=False
	)

	op.create_table(
		"payslip_link",
		sa.Column("payslip_id", sa.BigInteger(), nullable=False),
		sa.Column("token_hash", sa.String(length=64), nullable=False),
		sa.Column("token_encrypted", sa.Text(), nullable=True),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("max_views", sa.Integer(), nullable=False),
		sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
		sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
		sa.Column("locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("lock_reason", sa.String(length=20), nullable=True),
		sa.Column("sms_status", sa.String(length=10), server_default="pending", nullable=False),
		sa.Column("sms_provider_id", sa.String(length=100), nullable=True),
		sa.Column("sms_error", sa.Text(), nullable=True),
		sa.Column("sms_sent_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("created_by_id", sa.BigInteger(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"sms_status IN ('pending', 'sent', 'failed')", name=op.f("ck_payslip_link_sms_status_valid")
		),
		sa.CheckConstraint(
			"lock_reason IS NULL OR lock_reason IN ('voided', 'failed_attempts')",
			name=op.f("ck_payslip_link_lock_reason_valid"),
		),
		sa.CheckConstraint(
			"locked = (lock_reason IS NOT NULL)", name=op.f("ck_payslip_link_lock_matches_reason")
		),
		sa.CheckConstraint(
			"view_count >= 0 AND failed_attempts >= 0", name=op.f("ck_payslip_link_counters_non_negative")
		),
		sa.ForeignKeyConstraint(
			["created_by_id"],
			["app_user.id"],
			name=op.f("fk_payslip_link_created_by_id_app_user"),
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["payslip_id"],
			["payslip.id"],
			name=op.f("fk_payslip_link_payslip_id_payslip"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_payslip_link")),
		sa.UniqueConstraint("token_hash", name=op.f("uq_payslip_link_token_hash")),
	)
	op.create_index(op.f("ix_payslip_link_payslip_id"), "payslip_link", ["payslip_id"], unique=False)
	op.create_index(
		"uq_payslip_link_one_active",
		"payslip_link",
		["payslip_id"],
		unique=True,
		postgresql_where=sa.text("NOT locked"),
	)
	op.create_index(
		"ix_payslip_link_sms_status",
		"payslip_link",
		["sms_status"],
		unique=False,
		postgresql_where=sa.text("sms_status = 'pending'"),
	)

	op.create_table(
		"payslip_view",
		sa.Column("link_id", sa.BigInteger(), nullable=False),
		sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("ip", sa.String(length=64), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.ForeignKeyConstraint(
			["link_id"],
			["payslip_link.id"],
			name=op.f("fk_payslip_view_link_id_payslip_link"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_payslip_view")),
	)
	op.create_index(op.f("ix_payslip_view_link_id"), "payslip_view", ["link_id"], unique=False)


def downgrade() -> None:
	op.drop_table("payslip_view")
	op.drop_table("payslip_link")
	op.drop_table("payslip_rejection")
	op.drop_table("payslip")
