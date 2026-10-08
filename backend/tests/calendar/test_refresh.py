"""The yearly calendar refresh against PostgreSQL."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from hozur.calendar import service
from hozur.calendar.sources import SourceHoliday
from hozur.db.models import AttendancePeriod, AuditEntry, CalendarYear, Holiday, Job
from hozur.jalali import holidays as hol
from hozur.jalali.calendar import OFFICIAL_HOLIDAY, WORKDAY
from hozur.setup import install


class FakeSource:
	code = "time_ir"

	def __init__(self, rows):
		self.rows = rows

	def fetch(self, year):
		return [r for r in self.rows if int(r.jdate[:4]) == year]


def official(jdate, title, htype=hol.OFFICIAL_LUNAR, status=hol.CONFIRMED):
	return SourceHoliday(jdate=jdate, title=title, holiday_type=htype, status=status)


@pytest.fixture
def installed(db):
	install.run(db)
	return db


def year_holidays(db, year):
	start, end = f"{year}/01/01", f"{year}/12/30"
	return {
		(h.jdate, h.title): h for h in db.scalars(select(Holiday).where(Holiday.jdate.between(start, end)))
	}


def test_install_loads_the_bundled_years_once(installed):
	years = {y.jyear: y for y in installed.scalars(select(CalendarYear))}
	assert set(years) == set(range(1400, 1411))
	assert years[1405].status == hol.CONFIRMED and years[1407].status == hol.PREDICTED
	count = installed.scalar(select(func.count()).select_from(Holiday))
	install.run(installed)  # idempotent
	assert installed.scalar(select(func.count()).select_from(Holiday)) == count
	tehran = year_holidays(installed, 1405)[("1405/04/13", "تعطیل عمومی اعلامی هیئت دولت (مراسم تشییع)")]
	assert tehran.scope == hol.PROVINCE and tehran.province_id is not None


def test_day_info_reads_the_table(installed):
	assert service.day_info(installed, "1405/01/01").day_type == OFFICIAL_HOLIDAY
	assert service.day_info(installed, "1405/07/14").day_type == WORKDAY


def test_refresh_confirms_a_predicted_year(installed):
	predicted = {k: h for k, h in year_holidays(installed, 1407).items() if h.status == hol.PREDICTED}
	assert predicted
	# time.ir confirms every predicted holiday but one, which moves a day later
	(moved_date, moved_title), *rest = sorted(predicted)
	y, m, d = moved_date.split("/")
	later = f"{y}/{m}/{int(d) + 1:02d}" if int(d) < 28 else f"{y}/{m}/{int(d) - 1:02d}"
	incoming = [official(jd, t) for jd, t in rest] + [official(later, moved_title)]
	incoming += [
		official(jd, t, htype=h.holiday_type)
		for (jd, t), h in year_holidays(installed, 1407).items()
		if h.status == hol.CONFIRMED
	]
	plan = service.plan_refresh(installed, 1407, FakeSource(incoming))
	actions = {(i.action, i.jdate) for i in plan.items}
	assert ("add", later) in actions and ("remove", moved_date) in actions
	assert sum(i.action == "change" for i in plan.items) == len(rest)  # predicted -> confirmed
	result = service.apply_refresh(installed, plan, user_id=None)
	assert result["status"] == hol.CONFIRMED
	assert sorted(result["affected_dates"]) == sorted({later, moved_date})
	year = installed.get(CalendarYear, 1407)
	assert (year.status, year.source) == (hol.CONFIRMED, "time_ir") and year.refreshed_at
	job = installed.scalar(select(Job).where(Job.kind == "recalculate"))
	assert job.payload["dates"] == sorted({later, moved_date})
	entry = installed.scalar(
		select(AuditEntry).where(AuditEntry.entity == "calendar_year", AuditEntry.entity_id == "1407")
	)
	assert entry.action == "refresh" and entry.after["added"] == 1
	# running the same refresh again changes nothing
	again = service.plan_refresh(installed, 1407, FakeSource(incoming))
	assert again.items == []


def test_refresh_leaves_operator_edits_and_skipped_items(installed):
	rows = year_holidays(installed, 1406)
	edited = next(h for h in rows.values() if h.holiday_type == hol.OFFICIAL_LUNAR)
	edited.title, edited.edited_by_operator = "ویرایش اپراتور", True
	installed.flush()
	plan = service.plan_refresh(installed, 1406, FakeSource([official("1406/02/02", "تعطیلی جدید")]))
	assert edited.jdate not in {i.jdate for i in plan.items}
	assert plan.kept_edits == 1
	add = next(i for i in plan.items if i.action == "add")
	service.apply_refresh(installed, plan, user_id=None, skip_keys={add.key})
	assert ("1406/02/02", "تعطیلی جدید") not in year_holidays(installed, 1406)
	assert installed.get(Holiday, edited.id).title == "ویرایش اپراتور"


def test_refresh_never_changes_a_closed_period(installed):
	installed.add(AttendancePeriod(jyear=1406, jmonth=2, status="closed", closed_at=func.now()))
	installed.flush()
	plan = service.plan_refresh(installed, 1406, FakeSource([official("1406/02/02", "تعطیلی جدید")]))
	item = next(i for i in plan.items if i.jdate == "1406/02/02")
	assert item.locked
	service.apply_refresh(installed, plan, user_id=None)
	assert ("1406/02/02", "تعطیلی جدید") not in year_holidays(installed, 1406)


def test_refresh_warning(installed):
	assert service.refresh_warning(installed, "1405/07/14") is None
	installed.get(CalendarYear, 1406).status = hol.PREDICTED
	warning = service.refresh_warning(installed, "1405/12/01")
	assert warning is not None and "1406" in str(warning)
	assert service.refresh_warning(installed, "1405/11/01") is None


def test_operator_edits_holidays_with_audit_and_recalculation(installed):
	from hozur.services.errors import Conflict, ValidationError

	closure = service.create_holiday(
		installed,
		{
			"jdate": "1405/09/01",
			"title": "آلودگی هوا",
			"holiday_type": hol.OFFICE_CLOSURE,
			"closure_pay_mode": "employer_paid",
		},
		user_id=None,
	)
	assert service.day_info(installed, "1405/09/01").day_type == "company_holiday"
	with pytest.raises(ValidationError):
		service.create_holiday(
			installed, {"jdate": "1405/09/02", "title": "x", "holiday_type": hol.OFFICE_CLOSURE}, None
		)
	# editing a holiday that came from a source marks it, so a refresh leaves it alone
	nowruz = next(h for (jd, _t), h in year_holidays(installed, 1406).items() if jd == "1406/01/01")
	service.update_holiday(installed, nowruz.id, {"title": "نوروز ۱۴۰۶"}, "عنوان", user_id=None)
	assert nowruz.edited_by_operator
	with pytest.raises(ValidationError, match="reason"):
		service.delete_holiday(installed, closure.id, "", None)
	service.delete_holiday(installed, closure.id, "اشتباه", None)
	assert service.day_info(installed, "1405/09/01").day_type == WORKDAY
	actions = [
		e.action
		for e in installed.scalars(
			select(AuditEntry).where(AuditEntry.entity == "holiday").order_by(AuditEntry.id)
		)
	]
	assert actions == ["insert", "update", "delete"]
	assert installed.scalar(select(func.count()).select_from(Job).where(Job.kind == "recalculate")) >= 3
	installed.add(AttendancePeriod(jyear=1405, jmonth=10, status="closed", closed_at=func.now()))
	installed.flush()
	with pytest.raises(Conflict, match="closed"):
		service.create_holiday(
			installed, {"jdate": "1405/10/05", "title": "x", "holiday_type": hol.COMPANY_INTERNAL}, None
		)
