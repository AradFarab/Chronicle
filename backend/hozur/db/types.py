"""Column types shared by the models."""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy.types import UserDefinedType

# The `jdate` domain (created in the first migration): a Jalali business date "1405/07/14".
# The regex is a cheap guard in the database; full validity (month lengths, leap years) is
# checked in Python with jdatetime before writing.
JDATE_PATTERN = r"^1[34][0-9]{2}/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])$"


class JDate(UserDefinedType):
	"""PostgreSQL domain `jdate`; Python value is the string itself."""

	cache_ok = True

	def get_col_spec(self, **kw) -> str:
		return "jdate"


def enum_check(column: str, values: tuple[str, ...] | list[str], name: str | None = None) -> CheckConstraint:
	"""CHECK (column IN (...)) named after the column, for text enumerations."""
	quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
	return CheckConstraint(f"{column} IN ({quoted})", name=name or f"{column}_valid")
