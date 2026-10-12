"""The company, work locations, departments (tags), the designation tree and personnel."""

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
	text,
	true,
)
from sqlalchemy.orm import Mapped, mapped_column

from chronicle.db.base import Base, IdMixin, TimestampMixin
from chronicle.db.types import JDate, enum_check

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
	phone: Mapped[str | None] = mapped_column(String(30))
	address: Mapped[str | None] = mapped_column(Text)
	logo_file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_file.id", ondelete="SET NULL"))


class Province(IdMixin, Base):
	__tablename__ = "province"

	name: Mapped[str] = mapped_column(String(100), unique=True)


class WorkLocation(IdMixin, TimestampMixin, Base):
	"""The physical place people work. Its province decides which provincial holidays apply."""

	__tablename__ = "work_location"

	name: Mapped[str] = mapped_column(String(150), unique=True)
	province_id: Mapped[int] = mapped_column(ForeignKey("province.id"))
	city: Mapped[str | None] = mapped_column(String(100))
	address: Mapped[str | None] = mapped_column(Text)
	is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Department(IdMixin, TimestampMixin, Base):
	"""A tag put on people to make reports easier. It has no hierarchy and no manager."""

	__tablename__ = "department"

	name: Mapped[str] = mapped_column(String(150), unique=True)


class Designation(IdMixin, TimestampMixin, Base):
	"""A position in the organization chart (سمت). Positions form a tree: the holders of the
	position above are the "parent" who approves requests. Exactly one root can be the CEO."""

	__tablename__ = "designation"
	__table_args__ = (
		CheckConstraint("parent_id <> id", name="not_own_parent"),
		CheckConstraint("NOT is_ceo OR parent_id IS NULL", name="ceo_is_root"),
		Index("uq_designation_one_ceo", "is_ceo", unique=True, postgresql_where=text("is_ceo")),
	)

	name: Mapped[str] = mapped_column(String(150), unique=True)
	parent_id: Mapped[int | None] = mapped_column(ForeignKey("designation.id"), index=True)
	is_ceo: Mapped[bool] = mapped_column(Boolean, server_default=false())
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
		Index("ix_employee_department_id_status", "department_id", "status"),
		Index(
			"uq_employee_detail_code",
			"detail_code",
			unique=True,
			postgresql_where=text("detail_code IS NOT NULL"),
		),
	)

	code: Mapped[str] = mapped_column(String(30), unique=True)
	# Accounting "detail code" (کد تفصیلی): the person's account in the books.
	detail_code: Mapped[str | None] = mapped_column(String(30))
	first_name: Mapped[str] = mapped_column(String(100))
	last_name: Mapped[str] = mapped_column(String(100))
	full_name: Mapped[str] = mapped_column(
		String(201), Computed("first_name || ' ' || last_name", persisted=True)
	)
	national_id: Mapped[str | None] = mapped_column(String(10), unique=True)
	gender: Mapped[str | None] = mapped_column(String(10))
	mobile: Mapped[str | None] = mapped_column(String(20))
	email: Mapped[str | None] = mapped_column(String(150))
	# Every employee is also a user: creating one creates the other.
	user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), unique=True)
	status: Mapped[str] = mapped_column(String(20), server_default=ACTIVE)
	contract_type: Mapped[str] = mapped_column(String(20), server_default="full_time")
	start_date: Mapped[str] = mapped_column(JDate)
	end_date: Mapped[str | None] = mapped_column(JDate)
	work_location_id: Mapped[int | None] = mapped_column(ForeignKey("work_location.id"))
	department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
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


class DesignationAssignment(IdMixin, TimestampMixin, Base):
	"""A person holds a designation from one Jalali day to another. Giving a designation adds a
	row; taking it away sets the end date, so the history stays."""

	__tablename__ = "designation_assignment"
	__table_args__ = (
		CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
		Index("ix_designation_assignment_employee_id", "employee_id"),
		Index("ix_designation_assignment_designation_id", "designation_id"),
	)

	employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"))
	designation_id: Mapped[int] = mapped_column(ForeignKey("designation.id"))
	valid_from: Mapped[str] = mapped_column(JDate)
	valid_to: Mapped[str | None] = mapped_column(JDate)
	note: Mapped[str | None] = mapped_column(Text)
