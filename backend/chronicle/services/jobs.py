"""Background jobs in PostgreSQL. The worker takes them with FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronicle.db.models import Job

RECALCULATE = "recalculate"  # payload: {"dates": [...], "employee_ids": [...] | None, "reason": str}


def enqueue(session: Session, kind: str, payload: dict[str, Any], dedup_key: str | None = None) -> Job:
	"""Queue a job; with a dedup_key, an identical job that is still queued is reused."""
	if dedup_key:
		existing = session.scalar(select(Job).where(Job.dedup_key == dedup_key, Job.status == "queued"))
		if existing:
			return existing
	job = Job(kind=kind, payload=payload, dedup_key=dedup_key)
	session.add(job)
	session.flush()
	return job
