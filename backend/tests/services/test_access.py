"""The designation tree: who is whose parent, who sees whom, delegation (rule 8)."""

from __future__ import annotations

import pytest
from orgfactory import TODAY, make_employee

from hozur.db.models import ApprovalDelegation, Designation, DesignationAssignment
from hozur.services import access, delegations
from hozur.services.errors import ValidationError


def test_parent_is_the_holder_of_the_designation_above(org):
	db = org.db
	assert access.parent_approvers(db, org.employee.id, TODAY) == [org.manager.id]
	assert access.parent_approvers(db, org.manager.id, TODAY) == [org.ceo.id]
	assert access.parent_approvers(db, org.other.id, TODAY) == [org.ceo.id]
	assert access.parent_approvers(db, org.ceo.id, TODAY) == []  # the CEO has no parent


def test_several_holders_of_a_designation_can_all_approve(org):
	second, _user = make_employee(org.db, "T-MGR2", org.manager_designation)
	assert access.parent_approvers(org.db, org.employee.id, TODAY) == sorted([org.manager.id, second.id])


def test_an_empty_parent_designation_is_skipped(org):
	end = DesignationAssignment
	for a in org.db.query(end).filter(end.employee_id == org.manager.id):
		a.valid_to = "1405/07/01"  # the sales manager left the position
	org.db.flush()
	assert access.parent_approvers(org.db, org.employee.id, TODAY) == [org.ceo.id]
	assert access.parent_approvers(org.db, org.employee.id, "1405/06/20") == [org.manager.id]


def test_someone_without_a_designation_reports_to_the_ceo(org):
	loose, _user = make_employee(org.db, "T-LOOSE")
	assert access.parent_approvers(org.db, loose.id, TODAY) == [org.ceo.id]


def test_a_person_who_left_does_not_approve(org):
	org.manager.status = "left"
	org.db.flush()
	assert access.parent_approvers(org.db, org.employee.id, TODAY) == [org.ceo.id]


def test_designations_can_be_given_and_taken(org):
	assert access.designations_on(org.db, org.employee.id, TODAY) == [org.expert_designation.id]
	org.db.add(
		DesignationAssignment(
			employee_id=org.employee.id, designation_id=org.accountant_designation.id, valid_from="1405/08/01"
		)
	)
	org.db.flush()
	assert access.designations_on(org.db, org.employee.id, TODAY) == [org.expert_designation.id]
	assert access.designations_on(org.db, org.employee.id, "1405/08/02") == [
		org.expert_designation.id,
		org.accountant_designation.id,
	]


def test_managers_see_the_people_below_them_only(org):
	db = org.db
	assert access.visible_employee_ids(db, org.mgr, TODAY) == {org.manager.id, org.employee.id}
	assert access.visible_employee_ids(db, org.emp, TODAY) == {org.employee.id}
	assert access.visible_employee_ids(db, org.boss, TODAY) is None  # the CEO
	assert access.visible_employee_ids(db, org.admin, TODAY) is None
	assert access.visible_employee_ids(db, org.op, TODAY) is None
	assert not access.can_see(db, org.mgr, org.other.id, TODAY)
	assert access.is_manager(db, org.mgr, TODAY) and not access.is_manager(db, org.emp, TODAY)


def test_designation_tree_helpers(org):
	d = org.db
	assert access.ancestors(d, org.expert_designation.id) == [
		org.manager_designation.id,
		org.ceo_designation.id,
	]
	assert access.descendants(d, {org.manager_designation.id}) == {
		org.manager_designation.id,
		org.expert_designation.id,
	}
	assert access.ceo_designation_id(d) == org.ceo_designation.id
	assert d.get(Designation, org.ceo_designation.id).parent_id is None


def test_delegation_gives_the_delegate_the_managers_authority(org):
	db = org.db
	peer, _user = make_employee(db, "T-PEER", org.accountant_designation)
	with pytest.raises(ValidationError):  # no one below the accountant: nothing to delegate
		delegations.create(db, org.anyone, {"delegate_id": org.employee.id}, TODAY)
	row = delegations.create(
		db, org.mgr, {"delegate_id": peer.id, "valid_from": "1405/07/10", "valid_to": "1405/07/20"}, TODAY
	)
	assert isinstance(row, ApprovalDelegation) and row.delegator_id == org.manager.id
	assert access.acting_employee_ids(db, peer.id, TODAY) == {peer.id, org.manager.id}
	assert access.acting_employee_ids(db, peer.id, "1405/07/21") == {peer.id}
	# the delegate sees the manager's team too, while the delegation lasts
	assert org.employee.id in access.subordinate_ids(db, peer.id, TODAY)
	assert org.employee.id not in access.subordinate_ids(db, peer.id, "1405/07/21")
