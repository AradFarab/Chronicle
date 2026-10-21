"""Idempotent install: reference data a fresh database needs. Safe to run after every upgrade."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronicle.db.models import (
	ApprovalDefault,
	ApprovalProcess,
	ApprovalProcessStep,
	AppSetting,
	Designation,
	LaborRuleSet,
	LeaveType,
	Province,
	PunchImportTemplate,
	ReportTemplate,
)
from chronicle.engine.rules import load_baseline
from chronicle.setup import data


def run(session: Session) -> None:
	ensure_provinces(session)
	ensure_ceo_designation(session)
	ensure_approval_processes(session)
	ensure_leave_types(session)
	ensure_rule_set_baseline(session)
	ensure_import_templates(session)
	ensure_report_templates(session)
	ensure_settings(session)
	ensure_sms_events(session)
	from chronicle.calendar.service import ensure_bundled_years

	ensure_bundled_years(session)
	session.flush()


def ensure_sms_events(session: Session) -> None:
	from chronicle.services import sms

	sms.sync_events(session)


def ensure_provinces(session: Session) -> None:
	existing = set(session.scalars(select(Province.name)))
	session.add_all(Province(name=name) for name in data.PROVINCES if name not in existing)


def ensure_ceo_designation(session: Session) -> None:
	"""The designation whose holder approves the "CEO" steps. Rename it, never delete it."""
	if not session.scalar(select(Designation.id).where(Designation.is_ceo)):
		session.add(Designation(name=data.CEO_DESIGNATION, is_ceo=True))


def ensure_approval_processes(session: Session) -> None:
	by_name = {p.name: p for p in session.scalars(select(ApprovalProcess))}
	for name, steps in data.STANDARD_PROCESSES.items():
		if name in by_name:
			continue
		process = ApprovalProcess(name=name, is_standard=True)
		process.steps = [ApprovalProcessStep(position=i + 1, approver_type=t) for i, t in enumerate(steps)]
		session.add(process)
		by_name[name] = process
	session.flush()
	have = set(session.scalars(select(ApprovalDefault.request_type)))
	for request_type, name in data.DEFAULT_PROCESSES.items():
		if request_type not in have:
			session.add(ApprovalDefault(request_type=request_type, process_id=by_name[name].id))


def ensure_leave_types(session: Session) -> None:
	existing = set(session.scalars(select(LeaveType.name)))
	for name, category, paid, deducts, hourly, limit, once in data.LEAVE_TYPES:
		if name not in existing:
			session.add(
				LeaveType(
					name=name,
					category=category,
					is_paid=paid,
					deducts_from_balance=deducts,
					allow_hourly=hourly,
					rule_limit=limit,
					once_in_service=once,
					is_standard=True,
				)
			)


def ensure_rule_set_baseline(session: Session) -> None:
	if session.scalar(select(LaborRuleSet.id).where(LaborRuleSet.is_legal_baseline)):
		return
	baseline = load_baseline()
	session.add(
		LaborRuleSet(
			name=baseline["name"],
			effective_from=baseline["effective_from"],
			is_legal_baseline=True,
			description=baseline["source"],
			parameters={k: v["value"] for k, v in baseline["parameters"].items()},
		)
	)


def ensure_import_templates(session: Session) -> None:
	existing = set(session.scalars(select(PunchImportTemplate.name)))
	for template in data.IMPORT_TEMPLATES:
		if template["name"] not in existing:
			session.add(PunchImportTemplate(**template, has_header=False))


def ensure_report_templates(session: Session) -> None:
	existing = set(session.scalars(select(ReportTemplate.name)))
	for template in data.REPORT_TEMPLATES:
		if template["name"] not in existing:
			columns = [{"field": key} for key in template["columns"]]
			session.add(ReportTemplate(**{**template, "columns": columns}, is_standard=True))


def ensure_settings(session: Session) -> None:
	existing = set(session.scalars(select(AppSetting.key)))
	session.add_all(AppSetting(key=k, value=v) for k, v in data.SETTINGS.items() if k not in existing)
