"""Split the multi-page payslip PDF and read the personnel code and national id of each page.

The finance software's PDF has a text layer (the numbers are real characters, not pictures), so
no OCR is needed and a misread is practically impossible. Instead of fixed coordinates the
label «کد پرسنلی» is found on the page and the number written beside it is read, so a slightly
moved layout or a changed font does not break it. Each page is stored as its own PDF without
converting it to an image, so the employee sees the original quality.

Ported from the standalone «fish» payslip app.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

import pdfplumber
from pypdf import PdfReader, PdfWriter

from chronicle.i18n import _

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# The labels in "visual" order: characters are sorted by their x position, so Persian words
# come out reversed.
_LABELS = {"code": "کد پرسنلی", "national": "کد ملی"}
LINE_TOLERANCE = 3.0  # allowed difference of the `top` of characters of one line (points)
MAX_LABEL_GAP = 150.0  # the farthest a number may be from its label (points)
MAX_DIGIT_GAP = 6.0  # the widest gap between the digits of one number (points)


def _label_regex(label: str) -> re.Pattern:
	visual = label[::-1]
	return re.compile(r"\s*".join(re.escape(w) for w in visual.split(" ")))


_LABEL_RE = {k: _label_regex(v) for k, v in _LABELS.items()}


def _norm_char(t: str) -> str:
	t = unicodedata.normalize("NFKC", t)  # Arabic presentation forms -> base letters
	return t.replace("ي", "ی").replace("ك", "ک").replace("ى", "ی")


def _is_digit(t: str) -> bool:
	return len(t) == 1 and t.translate(DIGITS).isdigit()


def _lines(chars):
	rows = []
	for c in sorted(chars, key=lambda c: c["top"]):
		if rows and abs(rows[-1][0] - c["top"]) <= LINE_TOLERANCE:
			rows[-1][1].append(c)
		else:
			rows.append([c["top"], [c]])
	return [sorted(r[1], key=lambda c: c["x0"]) for r in rows]


def _find_values(chars, key: str) -> list[str]:
	"""Every number beside the label on the page (normally exactly one)."""
	found = []
	for line in _lines(chars):
		text, idx = "", []
		for i, c in enumerate(line):
			n = _norm_char(c["text"])
			text += n
			idx.extend([i] * len(n))
		for m in _LABEL_RE[key].finditer(text):
			label_x0 = line[idx[m.start()]]["x0"]
			cluster = []
			for c in reversed(line[: idx[m.start()]]):
				t = c["text"]
				if _is_digit(t):
					if cluster and cluster[-1]["x0"] - c["x1"] > MAX_DIGIT_GAP:
						break
					if not cluster and label_x0 - c["x1"] > MAX_LABEL_GAP:
						break
					cluster.append(c)
				elif t.strip() in ("", ":", "："):
					if cluster and t.strip() == ":":
						break
					continue
				else:
					break  # reached another label or text
			if cluster:
				cluster.sort(key=lambda c: c["x0"])
				found.append("".join(c["text"] for c in cluster).translate(DIGITS))
			else:
				found.append("")
	return found


@dataclass
class SlipPage:
	page_no: int  # 1-based, in the uploaded file
	pdf_bytes: bytes  # this page as a PDF of its own
	code: str | None = None  # personnel code without leading zeros
	national: str | None = None  # the 10-digit national id printed on the page (to compare only)
	error: tuple | None = None  # (English template, *params) when the page cannot be used


def read_page_fields(chars) -> tuple[str | None, str | None, tuple | None]:
	"""(code, national id, error) from the characters of one page."""
	if not any(_is_digit(c["text"]) for c in chars):
		return None, None, (_("The page has no readable text (probably a scan or a picture)"),)
	codes = _find_values(chars, "code")
	if not codes:
		return None, None, (_("The label «کد پرسنلی» was not found on the page"),)
	if len(codes) > 1:
		return None, None, (_("{0} payslips are on one page; each must be on its own page"), len(codes))
	code = codes[0].lstrip("0")
	if not codes[0] or not code:
		return None, None, (_("The number beside «کد پرسنلی» could not be read"),)
	nats = [n for n in _find_values(chars, "national") if n]
	national = nats[0] if len(nats) == 1 and len(nats[0]) == 10 else None
	return code, national, None


def split_pdf(source) -> list[SlipPage]:
	"""Split an uploaded PDF (path or file object) page by page and read each page's code.
	Raises ValueError when the file is not a valid PDF."""
	try:
		reader = PdfReader(source)
		count = len(reader.pages)
	except Exception as e:
		raise ValueError(_("The file is not a valid PDF, or it has a password")) from e
	if hasattr(source, "seek"):
		source.seek(0)
	pages = []
	with pdfplumber.open(source) as plumb:
		for i in range(count):
			writer = PdfWriter()
			writer.add_page(reader.pages[i])
			buf = io.BytesIO()
			writer.write(buf)
			try:
				code, national, error = read_page_fields(plumb.pages[i].chars)
			except Exception:
				code, national, error = None, None, (_("Reading the text of the page failed"),)
			pages.append(SlipPage(i + 1, buf.getvalue(), code, national, error))
	return pages


def read_national(pdf: bytes) -> str | None:
	"""The national id printed on a stored single-page payslip."""
	try:
		with pdfplumber.open(io.BytesIO(pdf)) as plumb:
			if not plumb.pages:
				return None
			return read_page_fields(plumb.pages[0].chars)[1]
	except Exception:
		return None
