"""A payroll-software-like PDF for the payslip tests: one page per slip, the personnel code and
the national id written to the left of their Persian labels (in visual order, as the real
files carry them), in a font that has the Arabic letters."""

from __future__ import annotations

import io

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from chronicle.payslips.watermark import FONT_PATH

FONT = "TestPayslipFont"
CODE_LABEL = "کد پرسنلی"[::-1]
NATIONAL_LABEL = "کد ملی"[::-1]
_registered = False


def slip_pdf(*pages: tuple[str, str | None]) -> bytes:
	"""pages: (personnel code, national id or None to leave it off the page)."""
	global _registered
	if not _registered:
		pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
		_registered = True
	buf = io.BytesIO()
	c = canvas.Canvas(buf, pagesize=(595, 842))
	for code, national in pages:
		c.setFont(FONT, 12)
		c.drawString(100, 700, str(code))
		c.drawString(200, 700, CODE_LABEL)
		if national:
			c.drawString(100, 670, national)
			c.drawString(200, 670, NATIONAL_LABEL)
		c.drawString(100, 500, "net pay 123")
		c.showPage()
	c.save()
	return buf.getvalue()


def blank_page_pdf() -> bytes:
	buf = io.BytesIO()
	c = canvas.Canvas(buf, pagesize=(595, 842))
	c.showPage()
	c.save()
	return buf.getvalue()
