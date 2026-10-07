"""The company, branches, the department tree, job titles and personnel."""

from __future__ import annotations

from sqlalchemy import (
	BigInteger,
	Boolean,
	CheckConstraint,
	Computed,
	ForeignKey,
	Index,
	SmallInteger,
	String,
	Text,
	false,
	true,
)
from sqlalchemy.orm import Mapped, mapped_column

from hozur.db.base import Base, IdMixin, TimestampMixin
from hozur.db.types import JDate, enum_check

ACTIVE, SUSPENDED, LEFT = "active", "suspended", "left"
EMPLOYEE_STATUSES = (ACTIVE, SUSPENDED, LEFT)
CONTRACT_TYPES = ("full_time", "part_time", "hourly")
GENDERS = ("male", "female")


class Organization(TimestampMixin, Base):
	"""The company running the app (exactly one row, id = 1)."""

	__tablename__ = "organization"
	__table_args__ = (CheckConstraint("id = 1", name="single_row"),)

	id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
	name: Mapped[str] = mapped_column(String(200))
	legal_name: Mapped[str | None] = mapped_column(String(200))
	national_id: Mapped[str | None] = mapped_column(String(20))
	economic_code: Mapped[str | None] = mapped_column(String(20))
	insurance_workshop_code: Mapped[str | None] = mapped_column(String(20))
	ceo_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id", use_alter=True, ondelete="SET NULL"))
	phone: Mapped[str | None] = mapped_column(String(30))
	address: Mapped[str | None] = mapped_column(Text)
	logo_file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_file.id", ondelete="SET NULL"))


class Province(IdMixin, Base):
	__tablename__ = "province"

	name: Mapped[str] = mapped_column(String(100), unique=True)


class Branch(IdMixin, TimestampMixin, Base):
	__tablename__ = "branch"

	name: Mapped[str] = mapped_column(String(150), unique=True)
	province_id: Mapped[int] = mapped_column(ForeignKey("province.id"))
	city: Mapped[str | None] = mapped_column(String(100))
	address: Mapped[str | None] = mapped_column(Text)
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Department(IdMixin, TimestampMixin, Base):
	"""Department tree (adjacency list). Managers approve requests of their subtree."""

	__tablename__ = "department"
	__table_args__ = (
		CheckConstraint("parent_id <> id", name="not_own_parent"),
		CheckConstraint(
			"deputy_to IS NULL OR deputy_from IS NULL OR deputy_to >= deputy_from", name="deputy_range"
		),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	parent_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"), index=True)
	is_group: Mapped[bool] = mapped_column(Boolean, server_default=false())
	manager_id: Mapped[int | None] = mapped_column(
		ForeignKey("employee.id", use_alter=True, ondelete="SET NULL")
	)
	default_approver_id: Mapped[int | None] = mapped_column(
		ForeignKey("employee.id", use_alter=True, ondelete="SET NULL")
	)
	deputy_id: Mapped[int | None] = mapped_column(
		ForeignKey("employee.id", use_alter=True, ondelete="SET NULL")
	)
	deputy_from: Mapped[str | None] = mapped_column(JDate)
	deputy_to: Mapped[str | None] = mapped_column(JDate)


class Designation(IdMixin, TimestampMixin, Base):
	__tablename__ = "designation"

	name: Mapped[str] = mapped_column(String(150), unique=True)
	description: Mapped[str | None] = mapped_column(Text)
	# Only with a ruling of the hard-and-harmful jobs committee (Articles 52, 61).
	hard_and_harmful: Mapped[bool] = mapped_column(Boolean, server_default=false())
	committee_ruling_no: Mapped[str | None] = mapped_column(String(50))
	committee_ruling_date: Mapped[str | None] = mapped_column(JDate)


class Employee(IdMixin, TimestampMixin, Base):
	__tablename__ = "employee"
	__table_args__ = (
		enum_check("status", EMPLOYEE_STATUSES),
		enum_check("contract_type", CONTRACT_TYPES),
		CheckConstraint("gender IS NULL OR gender IN ('male', 'female')", name="gender_valid"),
		CheckConstraint("national_id ~ '^[0-9]{10}$'", name="national_id_digits"),
		CheckConstraint("end_date IS NULL OR end_date >= start_date", name="employment_range"),
		CheckConstraint("reports_to_id <> id", name="not_own_manager"),
		Index("ix_employee_department_id_status", "department_id", "status"),
	)

	code: Mapped[str] = mapped_column(String(30), unique=True)
	first_name: Mapped[str] = mapped_column(String(100))
	last_name: Mapped[str] = mapped_column(String(100))
	full_name: Mapped[str] = mapped_column(
		String(201), Computed("first_name || ' ' || last_name", persisted=True)
	)
	national_id: Mapped[str | None] = mapped_column(String(10), unique=True)
	gender: Mapped[str | None] = mapped_column(String(10))
	mobile: Mapped[str | None] = mapped_column(String(20))
	email: Mapped[str | None] = mapped_column(String(150))
	user_id: Mapped[int | None] = mapped_column(
		BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), unique=True
	)
	status: Mapped[str] = mapped_column(String(20), server_default=ACTIVE)
	contract_type: Mapped[str] = mapped_column(String(20), server_default="full_time")
	start_date: Mapped[str] = mapped_column(JDate)
	end_date: Mapped[str | None] = mapped_column(JDate)
	branch_id: Mapped[int | None] = mapped_column(ForeignKey("branch.id"))
	department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
	designation_id: Mapped[int | None] = mapped_column(ForeignKey("designation.id"))
	reports_to_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id", ondelete="SET NULL"))
	# Written general consent to overtime (Article 59).
	overtime_consent_on_file: Mapped[bool] = mapped_column(Boolean, server_default=false())
	overtime_consent_date: Mapped[str | None] = mapped_column(JDate)
	# Sensitive: only for the young-worker rules (Articles 80-84).
	birth_date: Mapped[str | None] = mapped_column(JDate)
	biometric_consent_date: Mapped[str | None] = mapped_column(JDate)
	biometric_consent_file_id: Mapped[int | None] = mapped_column(
		ForeignKey("stored_file.id", ondelete="SET NULL")
	)
	uses_card_instead_of_biometrics: Mapped[bool] = mapped_column(Boolean, server_default=false())
	# Nursing breaks until this day (Article 78).
	nursing_until: Mapped[str | None] = mapped_column(JDate)
