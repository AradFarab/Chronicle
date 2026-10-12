"""The worker: the job queue, retries and the nightly job."""

from __future__ import annotations

import pytest
from orgfactory import TODAY
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from chronicle import worker
from chronicle.db.models import DailyAttendance, Job
from chronicle.services import jobs


@pytest.fixture
def factory(org):
	org.db.commit()  # a savepoint: the worker's sessions see the company
	return sessionmaker(
		bind=org.db.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False
	)


def test_recalculate_job_runs_and_is_marked_done(org, factory):
	jobs.enqueue(
		org.db, jobs.RECALCULATE, {"dates": ["1405/07/12"], "employee_ids": [org.employee.id], "reason": "t"}
	)
	org.db.commit()
	assert worker.run_queue(factory, today=TODAY) == 1
	job = org.db.scalar(select(Job))
	org.db.refresh(job)
	assert job.status == "done" and job.payload["result"]["created"] == 1
	assert (
		org.db.scalar(select(DailyAttendance.status).where(DailyAttendance.employee_id == org.employee.id))
		== "absent"
	)


def test_pairs_and_range_payloads(org, factory):
	jobs.enqueue(org.db, jobs.RECALCULATE, {"pairs": [[org.other.id, "1405/07/12"]]})
	jobs.enqueue(
		org.db, jobs.RECALCULATE, {"range": ["1405/07/12", "1405/07/30"], "employee_ids": [org.ceo.id]}
	)
	org.db.commit()
	assert worker.run_queue(factory, today=TODAY) == 2
	ids = set(org.db.scalars(select(DailyAttendance.employee_id)))
	assert ids == {org.other.id, org.ceo.id}
	assert max(org.db.scalars(select(DailyAttendance.jdate))) == TODAY  # never after today


def test_a_failing_job_is_retried_then_failed(org, factory):
	org.db.add(Job(kind="no_such_kind", payload={}))
	org.db.commit()
	worker.run_queue(factory, today=TODAY)
	job = org.db.scalar(select(Job))
	org.db.refresh(job)
	assert job.status == "failed" and "unknown job kind" in job.last_error


def test_nightly_is_queued_once_per_day_and_allocates_leave(org, factory):
	assert worker.schedule_nightly(factory, "1405/08/01")
	assert not worker.schedule_nightly(factory, "1405/08/01")
	worker.run_queue(factory, today="1405/08/01")
	job = org.db.scalar(select(Job).where(Job.kind == worker.NIGHTLY))
	org.db.refresh(job)
	assert job.status == "done", job.last_error
	assert job.payload["result"]["leave_allocations"] == 4
