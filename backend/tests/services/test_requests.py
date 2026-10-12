"""Forms and processes: requests, approval chains, side effects."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest
from orgfactory import TODAY
from sqlalchemy import func, select

from chronicle.db.models import (
	ApprovalOverride,
	ApprovalProcess,
	AttendancePeriod,
	AuditEntry,
	Holiday,
	Job,
	LeaveLedgerEntry,
	LeaveType,
	RawPunch,
)
from chronicle.services import approvals, leave, requests
from chronicle.services.errors import Conflict, PermissionDenied, ValidationError
from chronicle.services.punches import effective_punches
from chronicle.setup import data

EARNED = "استحقاقی"


def leave_type(db, name=EARNED):
	return db.scalar(select(LeaveType).where(LeaveType.name == name))


def give_leave(org, days):
	leave.add_entry(org.db, org.employee.id, leave_type(org.db).id, leave.ALLOCATION, "1405/01/01", days)


def chain(request):
	"""The approvers of each step, as employee ids."""
	return [[p.employee_id for p in a.approvers] for a in request.approvals]


def daily_leave(org, start, end, actor=None, **kw):
	values = {
		"leave_type_id": leave_type(org.db).id,
		"unit": "daily",
		"from_date": start,
		"to_date": end,
		**kw,
	}
	return requests.submit(org.db, actor or org.emp, "leave", values, TODAY)


def test_daily_leave_goes_manager_then_ceo_and_uses_the_ledger(org):
	give_leave(org, 10)
	r = daily_leave(org, "1405/07/12", "1405/07/18")  # Sun..Sat: Thu, Fri are rest days
	assert (r.status, r.leave.total_days, r.number) == ("pending", Decimal(5), f"LV-{r.id:05d}")
	assert chain(r) == [[org.manager.id], [org.ceo.id]]
	assert approvals.waiting_for(r) == [org.manager.id]
	assert [x.id for x in requests.inbox(org.db, org.mgr, TODAY)] == [r.id]
	assert requests.inbox(org.db, org.boss, TODAY) == []  # not the CEO's turn yet
	with pytest.raises(PermissionDenied):
		requests.act(org.db, org.boss, r.id, "approve", None, TODAY)  # not their step yet
	requests.act(org.db, org.mgr, r.id, "approve", "ok", TODAY)
	assert approvals.waiting_for(r) == [org.ceo.id]
	requests.act(org.db, org.boss, r.id, "approve", None, TODAY)
	assert r.status == "approved" and r.decided_at
	assert leave.balance(org.db, org.employee.id, leave_type(org.db).id) == Decimal(5)
	job = org.db.scalar(select(Job).where(Job.kind == "recalculate").order_by(Job.id.desc()))
	assert job.payload["employee_ids"] == [org.employee.id] and "1405/07/12" in job.payload["dates"]
	actions = list(
		org.db.scalars(
			select(AuditEntry.action)
			.where(AuditEntry.entity == "request", AuditEntry.entity_id == str(r.id))
			.order_by(AuditEntry.id)
		)
	)
	assert actions == ["submit", "approve", "approve"]


def test_official_holidays_inside_a_leave_do_not_count(org):
	give_leave(org, 10)
	org.db.add(Holiday(jdate="1405/07/13", title="t", holiday_type="official_occasional", source="manual"))
	org.db.flush()
	assert daily_leave(org, "1405/07/12", "1405/07/14").leave.total_days == Decimal(2)


def test_balance_overlap_and_unknown_unit(org):
	give_leave(org, 1)
	with pytest.raises(ValidationError, match="Not enough leave"):
		daily_leave(org, "1405/07/12", "1405/07/13")
	daily_leave(org, "1405/07/12", "1405/07/12")
	with pytest.raises(ValidationError, match="Overlaps"):
		daily_leave(org, "1405/07/12", "1405/07/12")
	with pytest.raises(ValidationError, match="no working day"):
		daily_leave(org, "1405/07/16", "1405/07/17")  # Thursday + Friday


def test_hourly_leave_is_minutes_over_the_legal_day(org):
	give_leave(org, 2)
	r = requests.submit(
		org.db,
		org.emp,
		"leave",
		{
			"leave_type_id": leave_type(org.db).id,
			"unit": "hourly",
			"jdate": TODAY,
			"from_time": "10:00",
			"to_time": "12:00",
		},
		TODAY,
	)
	# Article 70: 7 h 20 min (440 minutes) is one day
	assert (r.request_type, r.leave.total_minutes, r.leave.total_days) == (
		"hourly_leave",
		120,
		Decimal("0.2727"),
	)
	assert chain(r) == [[org.manager.id]]  # hourly: the parent only
	with pytest.raises(ValidationError, match="cannot be taken by the hour"):
		requests.submit(
			org.db, org.emp, "leave",
			{"leave_type_id": leave_type(org.db, "استعلاجی").id, "unit": "hourly", "jdate": TODAY, "from_time": "10:00", "to_time": "11:00"},
			TODAY,
		)  # fmt: skip


def test_leave_limits_come_from_the_rule_set(org):
	hajj = leave_type(org.db, "حج واجب")
	values = {"leave_type_id": hajj.id, "unit": "daily", "from_date": "1405/07/01", "to_date": "1405/08/15"}
	with pytest.raises(ValidationError, match="at most"):
		requests.submit(org.db, org.emp, "leave", values, TODAY)
	requests.submit(org.db, org.emp, "leave", {**values, "to_date": "1405/07/20"}, TODAY)
	with pytest.raises(ValidationError, match="only once"):
		requests.submit(
			org.db, org.emp, "leave", {**values, "from_date": "1405/09/01", "to_date": "1405/09/05"}, TODAY
		)


def test_employees_file_only_for_themselves_the_admin_for_anyone(org):
	give_leave(org, 5)
	with pytest.raises(PermissionDenied):
		daily_leave(org, "1405/07/12", "1405/07/12", actor=org.mgr, employee_id=org.employee.id)
	no_approval = org.db.scalar(select(ApprovalProcess).where(ApprovalProcess.name == data.NO_APPROVAL))
	from chronicle.db.models import ApprovalDefault

	org.db.get(ApprovalDefault, "admin_entry").process_id = no_approval.id
	r = daily_leave(org, "1405/07/12", "1405/07/12", actor=org.op, employee_id=org.employee.id)
	assert (r.entered_by_admin, r.status) == (True, "approved")


def test_per_employee_override(org):
	ceo_only = org.db.scalar(select(ApprovalProcess).where(ApprovalProcess.name == data.CEO_ONLY))
	org.db.add(ApprovalOverride(employee_id=org.employee.id, request_type="mission", process_id=ceo_only.id))
	org.db.flush()
	r = requests.submit(
		org.db,
		org.emp,
		"mission",
		{"unit": "daily", "from_date": TODAY, "to_date": TODAY, "reason": "x"},
		TODAY,
	)
	assert chain(r) == [[org.ceo.id]]


def test_mission_needs_a_reason(org):
	with pytest.raises(ValidationError, match="reason for the mission"):
		requests.submit(
			org.db, org.emp, "mission", {"unit": "daily", "from_date": TODAY, "to_date": TODAY}, TODAY
		)


def test_madde_59_assigned_overtime_needs_the_employees_acceptance(org):
	r = requests.submit(
		org.db,
		org.mgr,
		"overtime",
		{"employee_id": org.employee.id, "jdate": TODAY, "from_time": "16:30", "to_time": "18:30"},
		TODAY,
	)
	assert (r.overtime.assigned_by_manager, r.overtime.minutes) == (True, 120)
	first, manager_step = r.approvals
	assert (first.approver_type, [p.employee_id for p in first.approvers]) == (
		"employee_acceptance",
		[org.employee.id],
	)
	assert manager_step.status == "approved"  # the assigning manager's own step
	assert approvals.waiting_for(r) == [org.employee.id]
	requests.act(org.db, org.emp, r.id, "approve", None, TODAY)
	assert r.status == "approved"


def test_overtime_assignment_is_only_for_the_own_team(org):
	with pytest.raises(PermissionDenied, match="own team"):
		requests.submit(
			org.db, org.mgr, "overtime", {"employee_id": org.other.id, "jdate": TODAY, "minutes": 60}, TODAY
		)


def test_exceptional_overtime_needs_a_reason(org):
	with pytest.raises(ValidationError, match="reason"):
		requests.submit(
			org.db,
			org.emp,
			"overtime",
			{"jdate": TODAY, "minutes": 60, "overtime_kind": "exceptional"},
			TODAY,
		)


def test_reject_needs_a_comment_and_admin_can_act_for_an_approver(org):
	r = requests.submit(org.db, org.emp, "overtime", {"jdate": TODAY, "minutes": 60}, TODAY)
	with pytest.raises(ValidationError, match="rejecting"):
		requests.act(org.db, org.mgr, r.id, "reject", "", TODAY)
	requests.act(org.db, org.admin, r.id, "reject", "زیاد است", TODAY)
	assert r.status == "rejected" and r.approvals[0].acted_by_id == org.users.admin.id


def test_manual_entry_adds_and_ignores_punches_after_approval(org):
	db = org.db
	wrong = RawPunch(
		device_id=org.device.id,
		device_user_id="77",
		jdate="1405/07/13",
		time=time(7, 2),
		direction="in",
		reported_direction="in",
		source="device",
		dedup_key="w1",
	)
	db.add(wrong)
	db.flush()
	with pytest.raises(ValidationError, match="future"):
		requests.submit(
			db,
			org.emp,
			"correction",
			{"jdate": "1405/07/20", "reason": "x", "items": [{"time": "08:00"}]},
			TODAY,
		)
	with pytest.raises(ValidationError, match="not a punch"):
		requests.submit(
			db,
			org.emp,
			"correction",
			{
				"jdate": "1405/07/13",
				"reason": "x",
				"items": [{"action": "ignore_punch", "raw_punch_id": 999999}],
			},
			TODAY,
		)
	r = requests.submit(
		db,
		org.emp,
		"correction",
		{
			"jdate": "1405/07/13",
			"reason": "دستگاه خاموش بود",
			"items": [
				{"action": "add_punch", "time": "08:00", "direction": "in"},
				{"action": "add_punch", "time": "16:30", "direction": "out"},
				{"action": "ignore_punch", "raw_punch_id": wrong.id},
			],
		},
		TODAY,
	)
	assert r.number.startswith("COR-")
	assert [p.time for p in effective_punches(db, org.employee.id, "1405/07/13")] == [time(7, 2)]
	requests.act(db, org.mgr, r.id, "approve", None, TODAY)
	punches = effective_punches(db, org.employee.id, "1405/07/13")
	assert [(p.time, p.source) for p in punches] == [(time(8), "manual"), (time(16, 30), "manual")]
	# the raw punch itself is untouched
	assert db.get(RawPunch, wrong.id).time == time(7, 2)


def test_cancel_own_pending_and_operator_cancels_approved_leave(org):
	give_leave(org, 5)
	r = daily_leave(org, "1405/07/12", "1405/07/12")
	requests.cancel(org.db, org.emp, r.id, None, TODAY)
	assert r.status == "cancelled"
	approved = daily_leave(org, "1405/07/13", "1405/07/13")
	requests.act(org.db, org.mgr, approved.id, "approve", None, TODAY)
	requests.act(org.db, org.boss, approved.id, "approve", None, TODAY)
	with pytest.raises(PermissionDenied):
		requests.cancel(org.db, org.emp, approved.id, "x", TODAY)
	with pytest.raises(ValidationError, match="reason"):
		requests.cancel(org.db, org.op, approved.id, "", TODAY)
	requests.cancel(org.db, org.op, approved.id, "اشتباه ثبت شد", TODAY)
	entries = list(
		org.db.scalars(
			select(LeaveLedgerEntry.entry_type)
			.where(LeaveLedgerEntry.request_id == approved.id)
			.order_by(LeaveLedgerEntry.id)
		)
	)
	assert entries == ["usage", "reversal"]
	assert leave.balance(org.db, org.employee.id, leave_type(org.db).id) == Decimal(5)


def test_nothing_changes_inside_a_closed_period(org):
	org.db.add(AttendancePeriod(jyear=1405, jmonth=6, status="closed", closed_at=func.now()))
	org.db.flush()
	with pytest.raises(Conflict, match="closed"):
		requests.submit(org.db, org.emp, "overtime", {"jdate": "1405/06/20", "minutes": 60}, TODAY)


def test_visibility_of_requests(org):
	r = requests.submit(org.db, org.emp, "overtime", {"jdate": TODAY, "minutes": 60}, TODAY)
	assert requests.get(org.db, org.mgr, r.id, TODAY).id == r.id
	assert [x.id for x in requests.list_requests(org.db, org.mgr, TODAY)] == [r.id]
	other = requests.submit(
		org.db, org.op, "overtime", {"employee_id": org.other.id, "jdate": TODAY, "minutes": 30}, TODAY
	)
	with pytest.raises(PermissionDenied):
		requests.get(org.db, org.emp, other.id, TODAY)
	assert other.id not in [x.id for x in requests.list_requests(org.db, org.mgr, TODAY)]


# the three processes and who they ask ---------------------------------------------------------------


def mission(org, actor, **kw):
	values = {"unit": "daily", "from_date": TODAY, "to_date": TODAY, "reason": "x", **kw}
	return requests.submit(org.db, actor, "mission", values, TODAY)


def test_parent_then_ceo_is_only_the_ceo_when_the_parent_is_the_ceo(org):
	"""Process 2: the manager's own parent is the CEO, so one approval is enough."""
	r = mission(org, org.mgr)
	assert [(a.approver_type, a.status) for a in r.approvals] == [("parent", "pending"), ("ceo", "skipped")]
	assert chain(r) == [[org.ceo.id], [org.ceo.id]]
	requests.act(org.db, org.boss, r.id, "approve", None, TODAY)
	assert r.status == "approved"


def test_the_ceos_own_requests_need_no_approval(org):
	r = mission(org, org.boss)
	assert r.status == "approved" and {a.status for a in r.approvals} == {"skipped"}


def test_any_holder_of_the_parent_designation_can_approve(org):
	from orgfactory import make_employee

	second, _user = make_employee(org.db, "T-MGR2", org.manager_designation)
	r = requests.submit(org.db, org.emp, "overtime", {"jdate": TODAY, "minutes": 60}, TODAY)
	assert chain(r) == [sorted([org.manager.id, second.id])]
	requests.act(org.db, org.mgr, r.id, "approve", None, TODAY)
	assert r.status == "approved"


def test_a_delegate_approves_in_the_managers_place_and_the_manager_still_can(org):
	from orgfactory import make_employee

	from chronicle.services import access, delegations

	peer, peer_user = make_employee(org.db, "T-PEER", org.accountant_designation)
	delegations.create(org.db, org.mgr, {"delegate_id": peer.id}, TODAY)
	r = requests.submit(org.db, org.emp, "overtime", {"jdate": TODAY, "minutes": 60}, TODAY)
	delegate = access.actor_for(org.db, peer_user, TODAY)
	assert [x.id for x in requests.inbox(org.db, delegate, TODAY)] == [r.id]
	assert [x.id for x in requests.inbox(org.db, org.mgr, TODAY)] == [r.id]
	requests.act(org.db, delegate, r.id, "approve", "ok", TODAY)
	assert r.status == "approved"
	assert r.approvals[0].acted_by_id == peer_user.id  # the history says who really approved


def test_someone_who_is_not_the_parent_or_a_delegate_cannot_approve(org):
	r = requests.submit(org.db, org.emp, "overtime", {"jdate": TODAY, "minutes": 60}, TODAY)
	with pytest.raises(PermissionDenied):
		requests.act(org.db, org.anyone, r.id, "approve", None, TODAY)
