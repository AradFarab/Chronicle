"""Splitting the payroll PDF and reading the personnel code and national id of each page."""

from __future__ import annotations

import io

import pytest
from payslipfactory import blank_page_pdf, slip_pdf

from chronicle.payslips.pdf import read_national, split_pdf


def test_each_page_becomes_a_pdf_with_its_code_and_national_id():
	pages = split_pdf(io.BytesIO(slip_pdf(("42", "0012345678"), ("0007", "0087654321"))))
	assert [(p.page_no, p.code, p.national, p.error) for p in pages] == [
		(1, "42", "0012345678", None),
		(2, "7", "0087654321", None),
	]
	assert all(p.pdf_bytes.startswith(b"%PDF") for p in pages)


def test_a_page_without_a_national_id_still_has_its_code():
	[page] = split_pdf(io.BytesIO(slip_pdf(("15", None))))
	assert page.code == "15" and page.national is None and page.error is None


def test_a_page_with_no_text_is_reported_not_guessed():
	[page] = split_pdf(io.BytesIO(blank_page_pdf()))
	assert page.code is None and page.error


def test_a_file_that_is_not_a_pdf_is_a_value_error():
	with pytest.raises(ValueError):
		split_pdf(io.BytesIO(b"this is not a pdf"))


def test_the_national_id_of_a_stored_page_can_be_read_again():
	[page] = split_pdf(io.BytesIO(slip_pdf(("42", "0012345678"))))
	assert read_national(page.pdf_bytes) == "0012345678"
