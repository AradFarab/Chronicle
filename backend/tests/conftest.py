"""Database fixtures. DB tests run against CHRONICLE_TEST_DATABASE_URL (a scratch database whose
schema is rebuilt once per run); each test runs in a transaction that is rolled back."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
	"CHRONICLE_TEST_DATABASE_URL", "postgresql+psycopg://hozur:hozur@localhost:5432/hozur_test"
)


@pytest.fixture(scope="session")
def db_engine():
	engine = create_engine(TEST_DATABASE_URL)
	try:
		with engine.connect():
			pass
	except OperationalError as e:
		pytest.skip(f"test database not reachable: {e.orig}")
	from chronicle.db.migrate import upgrade

	with engine.begin() as conn:
		conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
		upgrade(connection=conn)
	yield engine
	engine.dispose()


@pytest.fixture
def db(db_engine):
	"""A session inside a transaction that is rolled back after the test. Code under test may
	commit: commits become savepoints."""
	connection = db_engine.connect()
	transaction = connection.begin()
	session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
	try:
		yield session
	finally:
		session.close()
		transaction.rollback()
		connection.close()


@pytest.fixture
def org(db):
	"""A small company with users for every role (see orgfactory.build_org)."""
	from orgfactory import build_org

	return build_org(db)
