"""A faint watermark over every page when a payslip is served: the viewer's name, personnel
code and the time of viewing (Jalali). The stored file is never changed; the result is built in
memory.

Ported from the standalone «fish» payslip app. The font (GNU FreeSerif, GPLv3 with the font
exception) has the Arabic presentation forms that reportlab needs after reshaping.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from arabic_reshaper import reshape
from bidi.algorithm import get_display
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_PATH = Path(__file__).parent / "fonts" / "FreeSerif.ttf"
_FONT_NAME = "ChroniclePayslipWatermark"
_registered = False


def _register_font() -> None:
	global _registered
	if not _registered:
		pdfmetrics.registerFont(TTFont(_FONT_NAME, str(FONT_PATH)))
		_registered = True


def _fa(text: str) -> str:
	"""Persian text for reportlab: shape the letters, then put them in visual order."""
	return get_display(reshape(text))


def watermark_pdf(pdf: bytes, name: str, code: str, when: str, label: str) -> bytes:
	"""`when` is the Jalali moment of viewing ("1405/07/27 - 10:30"); `label` the first line's
	lead-in ("Confidential")."""
	_register_font()
	line1 = _fa(f"{label} — {name} ({code})")
	line2 = _fa(when)

	reader = PdfReader(io.BytesIO(pdf))
	writer = PdfWriter()
	for page in reader.pages:
		w, h = float(page.mediabox.width), float(page.mediabox.height)
		buf = io.BytesIO()
		c = canvas.Canvas(buf, pagesize=(w, h))
		c.setFillColor(Color(0.55, 0.55, 0.55, alpha=0.18))
		c.saveState()
		c.translate(w / 2, h / 2)
		c.rotate(math.degrees(math.atan2(h, w)))
		c.setFont(_FONT_NAME, 26)
		c.drawCentredString(0, 12, line1)
		c.setFont(_FONT_NAME, 18)
		c.drawCentredString(0, -22, line2)
		c.restoreState()
		c.setFillColor(Color(0.45, 0.45, 0.45, alpha=0.55))
		c.setFont(_FONT_NAME, 8)
		c.drawCentredString(w / 2, 14, _fa(f"{name} — {code} — {when}"))
		c.save()
		buf.seek(0)
		writer.add_page(page)
		writer.pages[-1].merge_page(PdfReader(buf).pages[0])
	out = io.BytesIO()
	writer.write(out)
	return out.getvalue()
