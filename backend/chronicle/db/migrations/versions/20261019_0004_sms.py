"""sms: provider accounts, events, templates, messages, opt-outs and short links

The SMS module: panel accounts (one primary and one fallback, enforced by partial unique
indexes), the events that send messages, how each event is sent through a panel, every message
with its raw request and answer, opt-outs per category and short links for the SMS.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"short_link",
		sa.Column("code", sa.String(length=16), nullable=False),
		sa.Column("target_path", sa.String(length=500), nullable=False),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_short_link")),
		sa.UniqueConstraint("code", name=op.f("uq_short_link_code")),
	)
	op.create_table(
		"sms_event",
		sa.Column("code", sa.String(length=50), nullable=False),
		sa.Column("label", sa.String(length=150), nullable=False),
		sa.Column(
			"variables",
			postgresql.ARRAY(sa.String(length=40)),
			server_default=sa.text("'{}'"),
			nullable=False,
		),
		sa.Column("category", sa.String(length=20), server_default="transactional", nullable=False),
		sa.Column("bypasses_send_window", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"category IN ('transactional', 'promotional')", name=op.f("ck_sms_event_category_valid")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_event")),
		sa.UniqueConstraint("code", name=op.f("uq_sms_event_code")),
	)
	op.create_table(
		"sms_opt_out",
		sa.Column("mobile", sa.String(length=20), nullable=False),
		sa.Column("category", sa.String(length=20), nullable=False),
		sa.Column("reason", sa.Text(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"category IN ('transactional', 'promotional')", name=op.f("ck_sms_opt_out_category_valid")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_opt_out")),
		sa.UniqueConstraint("mobile", "category", name=op.f("uq_sms_opt_out_mobile_category")),
	)
	op.create_table(
		"sms_provider_config",
		sa.Column("provider_code", sa.String(length=30), nullable=False),
		sa.Column(
			"config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False
		),
		sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("is_fallback", sa.Boolean(), server_default=sa.text("false"), nullable=False),
		sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"NOT (is_primary AND is_fallback)", name=op.f("ck_sms_provider_config_not_both_roles")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_provider_config")),
		sa.UniqueConstraint("provider_code", name=op.f("uq_sms_provider_config_provider_code")),
	)
	op.create_index(
		"uq_sms_provider_config_one_fallback",
		"sms_provider_config",
		["is_fallback"],
		unique=True,
		postgresql_where=sa.text("is_fallback AND is_active"),
	)
	op.create_index(
		"uq_sms_provider_config_one_primary",
		"sms_provider_config",
		["is_primary"],
		unique=True,
		postgresql_where=sa.text("is_primary AND is_active"),
	)
	op.create_table(
		"sms_message",
		sa.Column("to_number", sa.String(length=20), nullable=False),
		sa.Column("event_id", sa.BigInteger(), nullable=False),
		sa.Column("provider_code", sa.String(length=30), nullable=True),
		sa.Column("status", sa.String(length=10), server_default="queued", nullable=False),
		sa.Column("provider_message_id", sa.String(length=100), nullable=True),
		sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
		sa.Column(
			"context", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False
		),
		sa.Column("raw_request", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("error", sa.Text(), nullable=True),
		sa.Column("cost", sa.Numeric(precision=14, scale=4), nullable=True),
		sa.Column("entity_key", sa.String(length=120), nullable=True),
		sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("send_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint(
			"status IN ('queued', 'sending', 'sent', 'delivered', 'failed', 'skipped', 'unknown')",
			name=op.f("ck_sms_message_status_valid"),
		),
		sa.CheckConstraint("attempts >= 0", name=op.f("ck_sms_message_attempts_non_negative")),
		sa.ForeignKeyConstraint(
			["event_id"], ["sms_event.id"], name=op.f("fk_sms_message_event_id_sms_event")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_message")),
	)
	op.create_index("ix_sms_message_status_send_after", "sms_message", ["status", "send_after"], unique=False)
	op.create_index("ix_sms_message_to_number", "sms_message", ["to_number"], unique=False)
	op.create_index(
		"uq_sms_message_once",
		"sms_message",
		["event_id", "entity_key"],
		unique=True,
		postgresql_where=sa.text("entity_key IS NOT NULL"),
	)
	op.create_table(
		"sms_template",
		sa.Column("event_id", sa.BigInteger(), nullable=False),
		sa.Column("provider_code", sa.String(length=30), nullable=False),
		sa.Column("mode", sa.String(length=10), nullable=False),
		sa.Column("body", sa.Text(), nullable=True),
		sa.Column("pattern_code", sa.String(length=100), nullable=True),
		sa.Column("line_number", sa.String(length=30), nullable=True),
		sa.Column("param_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"(mode = 'bulk' AND body IS NOT NULL) OR (mode = 'pattern' AND pattern_code IS NOT NULL)",
			name=op.f("ck_sms_template_mode_fields"),
		),
		sa.CheckConstraint("mode IN ('bulk', 'pattern')", name=op.f("ck_sms_template_mode_valid")),
		sa.ForeignKeyConstraint(
			["event_id"], ["sms_event.id"], name=op.f("fk_sms_template_event_id_sms_event")
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_template")),
	)
	op.create_index(op.f("ix_sms_template_event_id"), "sms_template", ["event_id"], unique=False)
	op.create_index(
		"uq_sms_template_one_active",
		"sms_template",
		["event_id", "provider_code"],
		unique=True,
		postgresql_where=sa.text("is_active"),
	)


def downgrade() -> None:
	op.drop_table("sms_template")
	op.drop_table("sms_message")
	op.drop_table("sms_provider_config")
	op.drop_table("sms_opt_out")
	op.drop_table("sms_event")
	op.drop_table("short_link")
