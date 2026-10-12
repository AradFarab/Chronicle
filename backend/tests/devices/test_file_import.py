import io
from datetime import datetime

import pytest
from openpyxl import Workbook

from chronicle.devices.base import IN, OUT, UNKNOWN, DeviceError
from chronicle.devices.file_import import CSV, EXCEL, ZKTECO_USB, parse_rows, read_table

ATTLOG = b"""      1\t2026-10-06 07:58:11\t1\t0\t1\t0
      1\t2026-10-06 16:31:02\t1\t1\t1\t0
     12\t2026-10-06 08:03:45\t15\t0\t1\t0
"""


def test_zkteco_usb_export_converts_to_jalali_once():
	result = parse_rows(read_table(ATTLOG, ZKTECO_USB), {"file_format": ZKTECO_USB})
	assert not result.errors
	first, second, third = result.punches
	assert (first.device_user_id, first.jdate, first.time, first.direction) == (
		"1",
		"1405/07/14",
		"07:58:11",
		IN,
	)
	assert first.device_timestamp == datetime(2026, 10, 6, 7, 58, 11)
	assert second.direction == OUT
	assert third.device_user_id == "12"


def test_csv_with_jalali_date_and_time_columns_and_persian_digits():
	content = "کد,تاریخ,ساعت,نوع\n101,۱۴۰۵/۰۷/۱۴,۷:۵۸,ورود\n101,1405/7/14,16:31:02,خروج\n102,1405/07/14,08:10,\n".encode()
	template = {
		"file_format": CSV,
		"delimiter": "comma",
		"has_header": 1,
		"user_id_column": "کد",
		"date_column": "تاریخ",
		"time_column": "C",
		"date_calendar": "jalali",
		"direction_column": "4",
		"in_values": "ورود",
		"out_values": "خروج",
	}
	result = parse_rows(read_table(content, CSV, "comma"), template)
	assert not result.errors
	assert [(p.device_user_id, p.jdate, p.time, p.direction) for p in result.punches] == [
		("101", "1405/07/14", "07:58:00", IN),
		("101", "1405/07/14", "16:31:02", OUT),
		("102", "1405/07/14", "08:10:00", UNKNOWN),
	]
	# Jalali files carry no device clock value: nothing Gregorian is invented.
	assert all(p.device_timestamp is None for p in result.punches)


def test_bad_rows_are_reported_not_imported():
	content = b"id,date,time\n1,1405/07/31,08:00\n2,1405/07/14,25:00\n3,1405/07/14,08:00\n"
	template = {
		"file_format": CSV,
		"has_header": 1,
		"user_id_column": "1",
		"date_column": "2",
		"time_column": "3",
	}
	result = parse_rows(read_table(content, CSV), template)
	assert [p.device_user_id for p in result.punches] == ["3"]
	assert len(result.errors) == 2 and result.errors[0].startswith("row 2:")


def test_excel_with_gregorian_datetime_column():
	wb = Workbook()
	ws = wb.active
	ws.append(["Person", "When"])
	ws.append([7, datetime(2026, 3, 21, 9, 0, 0)])
	buf = io.BytesIO()
	wb.save(buf)
	template = {
		"file_format": EXCEL,
		"has_header": 1,
		"user_id_column": "A",
		"datetime_column": "When",
		"date_calendar": "gregorian",
		"date_format": "YYYY-MM-DD",
	}
	result = parse_rows(read_table(buf.getvalue(), EXCEL), template)
	assert [(p.device_user_id, p.jdate, p.time) for p in result.punches] == [("7", "1405/01/01", "09:00:00")]


def test_windows_1256_file_with_arabic_yeh_matches_persian_headers():
	# Old Persian software writes the Arabic yeh (U+064A): Windows-1256 has no Persian yeh.
	content = "کد پرسنلي,تاريخ,ساعت\n5,1405/07/14,08:00\n".encode("cp1256")
	template = {
		"file_format": CSV,
		"has_header": 1,
		"user_id_column": "کد پرسنلی",
		"date_column": "تاریخ",
		"time_column": "ساعت",
	}
	rows = read_table(content, CSV, "comma", "windows-1256")
	assert rows[0][1] == "تاریخ"
	result = parse_rows(rows, template)
	assert [p.device_user_id for p in result.punches] == ["5"]


def test_template_without_required_columns_fails_clearly():
	with pytest.raises(DeviceError):
		parse_rows([["a", "b"]], {"file_format": CSV, "has_header": 0, "user_id_column": "1"})
