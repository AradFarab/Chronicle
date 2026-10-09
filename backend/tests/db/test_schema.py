"""The database itself enforces the data model's invariants (CLAUDE.md rules 1, 4, 10)."""

from __future__ import annotations

from datetime import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from hozur.db.models import (
	AppUser,
	AttendanceDevice,
	CorrectionItem,
	Employee,
	Holiday,
	RawPunch,
	Request,
	WorkPatternAssignment,
)


def punch(device_id: int, key: str, jdate: str = "1405/07/14") -> RawPunch:
	return RawPunch(
		device_id=device_id,
		device_user_id="7",
		jdate=jdate,
		time=time(8, 1),
		direction="in",
		reported_direction="in",
		source="device",
		dedup_key=key,
	)


@pytest.fixture
def device(db):
	d = AttendanceDevice(name="T-Device", adapter_type="zkteco", host="10.0.0.1")
	db.add(d)
	db.flush()
	return d


@pytest.fixture
def employee(db):
	user = AppUser(username="t-1", full_name="سارا کریمی")
	db.add(user)
	db.flush()
	e = Employee(code="T-1", first_name="سارا", last_name="کریمی", start_date="1405/07/01", user_id=user.id)
	db.add(e)
	db.flush()
	return e


def test_jdate_domain_rejects_bad_dates(db, device):
	db.add(punch(device.id, "bad", "1405/13/01"))
	with pytest.raises(DBAPIError, match="jdate"):
		db.flush()


def test_raw_punch_is_append_only(db, device):
	p = punch(device.id, "k1")
	db.add(p)
	db.flush()
	assert (p.jyear, p.jmonth) == (1405, 7)  # generated columns
	with pytest.raises(DBAPIError, match="append-only"):
		db.execute(text("UPDATE raw_punch SET time = '09:00' WHERE id = :id"), {"id": p.id})


def test_raw_punch_cannot_be_deleted(db, device):
	p = punch(device.id, "k2")
	db.add(p)
	db.flush()
	with pytest.raises(DBAPIError, match="append-only"):
		db.execute(text("DELETE FROM raw_punch WHERE id = :id"), {"id": p.id})


def test_duplicate_punch_key_is_rejected(db, device):
	db.add_all([punch(device.id, "same"), punch(device.id, "same")])
	with pytest.raises(IntegrityError):
		db.flush()


def test_employee_full_name_is_generated(db, employee):
	assert employee.full_name == "سارا کریمی"


def test_request_type_must_match_kind(db, employee):
	db.add(
		Request(
			kind="leave",
			request_type="overtime",
			employee_id=employee.id,
			start_jdate="1405/07/14",
			end_jdate="1405/07/14",
		)
	)
	with pytest.raises(IntegrityError, match="type_matches_kind"):
		db.flush()


def test_request_number_follows_kind(db, employee):
	r = Request(
		kind="mission",
		request_type="mission",
		employee_id=employee.id,
		start_jdate="1405/07/14",
		end_jdate="1405/07/15",
	)
	db.add(r)
	db.flush()
	db.refresh(r)
	assert r.number == f"MS-{r.id:05d}"


def test_correction_item_fields_match_action(db, employee):
	r = Request(
		kind="correction",
		request_type="attendance_correction",
		employee_id=employee.id,
		start_jdate="1405/07/14",
		end_jdate="1405/07/14",
	)
	r.correction_items = [CorrectionItem(position=1, action="add_punch")]  # add needs a time
	db.add(r)
	with pytest.raises(IntegrityError, match="action_fields"):
		db.flush()


def test_assignment_target_must_match_type(db):
	db.add(WorkPatternAssignment(target_type="employee", work_pattern_id=1, valid_from="1405/07/01"))
	with pytest.raises(IntegrityError, match="target_matches_type"):
		db.flush()


def test_holiday_scope_needs_its_province(db):
	db.add(Holiday(jdate="1405/07/20", title="x", holiday_type="official_occasional", scope="province"))
	with pytest.raises(IntegrityError, match="province_scope"):
		db.flush()


def test_schema_matches_models(db_engine):
	"""No drift between the models and the migrations."""
	from alembic.autogenerate import compare_metadata
	from alembic.runtime.migration import MigrationContext

	from hozur.db.base import Base

	with db_engine.connect() as conn:
		diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
	assert diff == []


def test_append_only_tables_have_triggers(db):
	names = set(
		db.scalars(select(text("tgname")).select_from(text("pg_trigger")).where(text("NOT tgisinternal")))
	)
	for table in ("raw_punch", "leave_ledger_entry", "audit_entry"):
		assert f"{table}_append_only" in names
