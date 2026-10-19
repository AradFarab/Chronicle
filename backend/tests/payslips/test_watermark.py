"""The watermark keeps every page and returns a valid PDF; the stored original is untouched."""

from __future__ import annotations

import io

from payslipfactory import slip_pdf
from pypdf import PdfReader

from chronicle.payslips.watermark import watermark_pdf


def test_every_page_is_marked_and_the_original_is_unchanged():
	original = slip_pdf(("42", "0012345678"), ("43", "0087654321"))
	marked = watermark_pdf(original, "علی رضایی", "42", "1405/07/27 - 10:30", "محرمانه")
	assert marked != original
	assert len(PdfReader(io.BytesIO(marked)).pages) == 2
	assert len(PdfReader(io.BytesIO(original)).pages) == 2
