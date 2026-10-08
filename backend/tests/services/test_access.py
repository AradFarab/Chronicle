"""Visibility (rule 8) and approver resolution."""

from orgfactory import TODAY, make_employee

from hozur.services import access


def test_direct_manager_walks_up_the_tree(org):
	db = org.db
	assert access.direct_manager(db, org.employee.id, TODAY) == org.manager.id
	# a manager's direct manager is above them (here reports_to)
	assert access.direct_manager(db, org.manager.id, TODAY) == org.ceo.id
	assert access.parent_department_manager(db, org.employee.id, TODAY) is None


def test_deputy_acts_for_the_manager_in_their_period(org):
	db = org.db
	deputy = make_employee(db, "T-DEP", org.sales)
	org.sales.deputy_id, org.sales.deputy_from, org.sales.deputy_to = deputy.id, "1405/07/10", "1405/07/20"
	db.flush()
	assert access.direct_manager(db, org.employee.id, TODAY) == deputy.id
	assert access.direct_manager(db, org.employee.id, "1405/07/21") == org.manager.id


def test_managers_see_their_subtree_only(org):
	db = org.db
	assert access.visible_employee_ids(db, org.mgr, TODAY) == {org.manager.id, org.employee.id}
	assert access.visible_employee_ids(db, org.emp, TODAY) == {org.employee.id}
	assert access.visible_employee_ids(db, org.boss, TODAY) is None
	assert access.visible_employee_ids(db, org.op, TODAY) is None
	assert not access.can_see(db, org.mgr, org.other.id, TODAY)
