"""An API client on the test transaction, plus the small company of tests/services."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from orgfactory import PASSWORD
from sqlalchemy.orm import sessionmaker

from chronicle.api.app import create_app
from chronicle.services import users


@pytest.fixture
def app(db):
	app = create_app()
	app.state.session_factory = sessionmaker(
		bind=db.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False
	)
	return app


@pytest.fixture
def client_for(app, org):
	"""client_for("emp") -> a logged-in client for that test user."""

	def make(username: str) -> TestClient:
		user = getattr(org.users, username)
		user.password_hash = users.hash_password(PASSWORD)
		org.db.flush()
		client = TestClient(app, headers={"X-Chronicle": "1"})
		r = client.post("/api/auth/login", json={"username": user.username, "password": PASSWORD})
		assert r.status_code == 200, r.text
		return client

	return make
