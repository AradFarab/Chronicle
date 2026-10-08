"""The background worker (`hozur worker`): polls devices, runs queued jobs, does the nightly work.

No Redis and no external scheduler: jobs live in the `job` table and are taken with
FOR UPDATE SKIP LOCKED, so several workers can run side by side safely.
"""

from __future__ import annotations

import logging
import signal
import time as systime
import traceback
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from hozur.clock import now, today_jalali
from hozur.db.models import AttendanceDevice, Job
from hozur.jalali.dates import add_days, iter_days
from hozur.services import attendance, devices, jobs, leave

log = logging.getLogger("hozur.worker")

TICK_SECONDS = 15
NIGHTLY = "nightly"
RETRY_AFTER = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))


# job handlers ---------------------------------------------------------------------------------


def _recalculate(session: Session, payload: dict[str, Any], today: str) -> dict:
	reason = payload.get("reason") or "recalculate"
	if "pairs" in payload:
		outcome = attendance.Outcome()
		calc = attendance.Calculator(session, today)
		for employee_id, jdate in sorted({(int(e), d) for e, d in payload["pairs"]}):
			calc.calculate(employee_id, jdate, reason, outcome)
		return outcome.as_dict()
	if "range" in payload:
		start, end = payload["range"]
		dates = list(iter_days(start, min(end, today))) if start <= today else []
	else:
		dates = payload.get("dates") or []
	return attendance.recalculate(session, dates, today, reason, payload.get("employee_ids")).as_dict()


def _nightly(session: Session, payload: dict[str, Any], today: str) -> dict:
	"""Yesterday and today for everyone, the finished month's leave accrual, year-end expiry.
	Every step is idempotent, so a missed night is caught up by the next one."""
	yesterday = add_days(today, -1)
	out = {"recalculated": attendance.recalculate(session, [yesterday, today], today, "nightly").as_dict()}
	year, month = int(today[:4]), int(today[5:7])
	prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
	out["leave_allocations"] = leave.allocate_month(session, prev_year, prev_month)
	if month == 1:
		out["leave_expiries"] = leave.close_leave_year(session, year - 1)
	return out


HANDLERS: dict[str, Callable[[Session, dict[str, Any], str], Any]] = {
	jobs.RECALCULATE: _recalculate,
	NIGHTLY: _nightly,
}


# the queue ------------------------------------------------------------------------------------


def claim(factory: sessionmaker[Session]) -> int | None:
	"""Mark the next due job running and return its id (None when the queue is empty)."""
	with factory() as session, session.begin():
		job = session.scalar(
			select(Job)
			.where(Job.status == "queued", Job.run_after <= now())
			.order_by(Job.run_after, Job.id)
			.with_for_update(skip_locked=True)
			.limit(1)
		)
		if job is None:
			return None
		job.status, job.started_at, job.attempts = "running", now(), job.attempts + 1
		return job.id


def run_job(factory: sessionmaker[Session], job_id: int, today: str | None = None) -> bool:
	"""Run one claimed job in its own transaction; record the outcome. True on success."""
	today = today or today_jalali()
	with factory() as session:
		job = session.get(Job, job_id)
		handler = HANDLERS.get(job.kind)
		try:
			if handler is None:
				raise LookupError(f"unknown job kind {job.kind!r}")
			result = handler(session, job.payload or {}, today)
			session.commit()
		except Exception:
			session.rollback()
			error = traceback.format_exc(limit=8)
			log.exception("job %s (%s) failed", job_id, job.kind)
			job = session.get(Job, job_id)
			job.last_error = error[-4000:]
			if job.attempts < job.max_attempts and handler is not None:
				job.status = "queued"
				job.run_after = now() + RETRY_AFTER[min(job.attempts, len(RETRY_AFTER)) - 1]
			else:
				job.status, job.finished_at = "failed", now()
			session.commit()
			return False
		job.status, job.finished_at, job.last_error = "done", now(), None
		if result is not None:
			job.payload = {**(job.payload or {}), "result": result}
		session.commit()
		return True


def run_queue(factory: sessionmaker[Session], limit: int = 50, today: str | None = None) -> int:
	"""Run up to `limit` due jobs; returns how many ran."""
	count = 0
	while count < limit:
		job_id = claim(factory)
		if job_id is None:
			break
		run_job(factory, job_id, today)
		count += 1
	return count


def schedule_nightly(factory: sessionmaker[Session], today: str | None = None) -> bool:
	"""Queue the nightly job once per Jalali day."""
	today = today or today_jalali()
	key = f"{NIGHTLY}:{today}"
	with factory() as session, session.begin():
		if session.scalar(select(Job.id).where(Job.dedup_key == key).limit(1)):
			return False
		session.add(Job(kind=NIGHTLY, payload={"jdate": today}, dedup_key=key))
		return True


def poll_devices(factory: sessionmaker[Session]) -> int:
	"""Sync every enabled network device whose polling interval has passed. Each device has
	its own transaction, so one unreachable device never holds up the others."""
	with factory() as session:
		due = [d.id for d in devices.due_devices(session)]
	for device_id in due:
		with factory() as session:
			try:
				result = devices.sync_device(session, session.get(AttendanceDevice, device_id))
				session.commit()
			except Exception:
				session.rollback()
				log.exception("sync of device %s failed", device_id)
				continue
			if not result.ok:
				log.warning("device %s: %s", device_id, result.error)
	return len(due)


def tick(factory: sessionmaker[Session]) -> None:
	schedule_nightly(factory)
	poll_devices(factory)
	run_queue(factory)


def recover(factory: sessionmaker[Session]) -> None:
	"""Jobs left running by a worker that died go back to the queue."""
	with factory() as session, session.begin():
		for job in session.scalars(select(Job).where(Job.status == "running")):
			job.status = "queued" if job.attempts < job.max_attempts else "failed"


def run() -> None:
	from hozur.db.session import session_factory

	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
	factory = session_factory()
	stopping = False

	def stop(*_args):
		nonlocal stopping
		stopping = True

	signal.signal(signal.SIGTERM, stop)
	signal.signal(signal.SIGINT, stop)
	recover(factory)
	log.info("worker started")
	while not stopping:
		started = systime.monotonic()
		try:
			tick(factory)
		except Exception:
			log.exception("worker tick failed")
		while not stopping and systime.monotonic() - started < TICK_SECONDS:
			systime.sleep(0.5)
	log.info("worker stopped")
