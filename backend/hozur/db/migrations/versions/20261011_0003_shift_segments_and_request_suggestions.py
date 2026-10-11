"""shift segments (several breaks, overtime windows) and request suggestions

A shift's single break window (break_start_time / break_end_time) becomes rows of
``shift_segment``: any number of breaks (never working time, Article 51) and windows in which
extra work may become overtime. ``request_suggestion`` holds the requests the calculation
proposes to an employee (overtime, hourly leave, a punch correction) until they send or
dismiss them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import hozur.db.types

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _minute(t) -> int:
	return t.hour * 60 + t.minute


def upgrade() -> None:
	op.create_table(
		"shift_segment",
		sa.Column("shift_id", sa.BigInteger(), nullable=False),
		sa.Column("kind", sa.String(length=20), nullable=False),
		sa.Column("start_minute", sa.Integer(), nullable=False),
		sa.Column("end_minute", sa.Integer(), nullable=False),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.CheckConstraint("kind IN ('break', 'overtime')", name=op.f("ck_shift_segment_kind_valid")),
		sa.CheckConstraint(
			"start_minute >= 0 AND end_minute > start_minute AND end_minute <= 2880",
			name=op.f("ck_shift_segment_minute_range"),
		),
		sa.ForeignKeyConstraint(
			["shift_id"], ["shift.id"], name=op.f("fk_shift_segment_shift_id_shift"), ondelete="CASCADE"
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_shift_segment")),
	)
	op.create_index(op.f("ix_shift_segment_shift_id"), "shift_segment", ["shift_id"], unique=False)

	# Each shift's break window becomes a break segment, in minutes from the shift day's 00:00.
	bind = op.get_bind()
	rows = bind.execute(
		sa.text(
			"SELECT id, start_time, break_start_time, break_end_time FROM shift "
			"WHERE break_start_time IS NOT NULL AND break_end_time IS NOT NULL"
		)
	).all()
	for shift_id, start, b_start, b_end in rows:
		begin = _minute(b_start) + (1440 if b_start < start else 0)
		end = _minute(b_end)
		while end <= begin:
			end += 1440
		if end <= 2880:
			bind.execute(
				sa.text(
					"INSERT INTO shift_segment (shift_id, kind, start_minute, end_minute) "
					"VALUES (:s, 'break', :b, :e)"
				),
				{"s": shift_id, "b": begin, "e": end},
			)
	op.drop_constraint(op.f("ck_shift_break_window_pair"), "shift", type_="check")
	op.drop_column("shift", "break_end_time")
	op.drop_column("shift", "break_start_time")

	op.create_table(
		"request_suggestion",
		sa.Column("employee_id", sa.BigInteger(), nullable=False),
		sa.Column("jdate", hozur.db.types.JDate(), nullable=False),
		sa.Column("request_type", sa.String(length=30), nullable=False),
		sa.Column("key", sa.String(length=60), nullable=False),
		sa.Column("from_minute", sa.Integer(), nullable=True),
		sa.Column("to_minute", sa.Integer(), nullable=True),
		sa.Column("minutes", sa.Integer(), nullable=False),
		sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
		sa.Column("request_id", sa.BigInteger(), nullable=True),
		sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
		sa.CheckConstraint(
			"request_type IN ('overtime', 'hourly_leave', 'attendance_correction')",
			name=op.f("ck_request_suggestion_request_type_valid"),
		),
		sa.CheckConstraint(
			"status IN ('open', 'sent', 'dismissed')", name=op.f("ck_request_suggestion_status_valid")
		),
		sa.CheckConstraint(
			"from_minute IS NULL OR (to_minute IS NOT NULL AND to_minute > from_minute)",
			name=op.f("ck_request_suggestion_minute_range"),
		),
		sa.CheckConstraint("minutes >= 0", name=op.f("ck_request_suggestion_minutes_non_negative")),
		sa.ForeignKeyConstraint(
			["employee_id"],
			["employee.id"],
			name=op.f("fk_request_suggestion_employee_id_employee"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["request_id"],
			["request.id"],
			name=op.f("fk_request_suggestion_request_id_request"),
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("pk_request_suggestion")),
		sa.UniqueConstraint(
			"employee_id", "jdate", "key", name=op.f("uq_request_suggestion_employee_id_jdate_key")
		),
	)
	op.create_index(
		"ix_request_suggestion_employee_id_status",
		"request_suggestion",
		["employee_id", "status"],
		unique=False,
	)


def downgrade() -> None:
	op.drop_index("ix_request_suggestion_employee_id_status", table_name="request_suggestion")
	op.drop_table("request_suggestion")

	op.add_column("shift", sa.Column("break_start_time", sa.Time(), nullable=True))
	op.add_column("shift", sa.Column("break_end_time", sa.Time(), nullable=True))
	# Only one break window existed before: keep each shift's first break; overtime windows go.
	op.execute(
		"""
		UPDATE shift SET
			break_start_time = make_time((first.start_minute % 1440) / 60, (first.start_minute % 60), 0),
			break_end_time = make_time((first.end_minute % 1440) / 60, (first.end_minute % 60), 0)
		FROM (
			SELECT DISTINCT ON (shift_id) shift_id, start_minute, end_minute
			FROM shift_segment WHERE kind = 'break' ORDER BY shift_id, start_minute
		) AS first
		WHERE first.shift_id = shift.id
		"""
	)
	op.create_check_constraint(
		op.f("ck_shift_break_window_pair"), "shift", "(break_start_time IS NULL) = (break_end_time IS NULL)"
	)
	op.drop_index(op.f("ix_shift_segment_shift_id"), table_name="shift_segment")
	op.drop_table("shift_segment")
