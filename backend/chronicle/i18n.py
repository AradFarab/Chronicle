"""Translations. Source strings are English; Persian comes from locale/fa.po.

`_()` only marks a string for extraction and returns it unchanged; the API translates
messages for the user's language at the edge (`translate`). No gettext binaries needed."""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

LOCALE_DIR = Path(__file__).parent / "locale"
DEFAULT_LANGUAGE = "fa"


def _(text: str) -> str:
	return text


def _unquote(chunk: str) -> str:
	return ast.literal_eval(chunk)


@cache
def catalog(language: str) -> dict[str, str]:
	"""msgid -> msgstr from locale/<language>.po (context-free entries; fuzzy entries skipped)."""
	path = LOCALE_DIR / f"{language}.po"
	if not path.exists():
		return {}
	messages: dict[str, str] = {}
	msgid = msgstr = None
	field = None
	fuzzy = False
	context = None

	def flush():
		if msgid and msgstr and not fuzzy and context is None:
			messages[msgid] = msgstr

	for raw in path.read_text(encoding="utf-8").splitlines():
		line = raw.strip()
		if not line:
			flush()
			msgid = msgstr = field = context = None
			fuzzy = False
			continue
		if line.startswith("#,") and "fuzzy" in line:
			fuzzy = True
		elif line.startswith("#"):
			continue
		elif line.startswith("msgctxt "):
			context, field = _unquote(line[8:]), "ctx"
		elif line.startswith("msgid "):
			msgid, field = _unquote(line[6:]), "id"
		elif line.startswith("msgstr "):
			msgstr, field = _unquote(line[7:]), "str"
		elif line.startswith('"'):
			if field == "id":
				msgid = (msgid or "") + _unquote(line)
			elif field == "str":
				msgstr = (msgstr or "") + _unquote(line)
			elif field == "ctx":
				context = (context or "") + _unquote(line)
	flush()
	return messages


def translate(text: str, language: str = DEFAULT_LANGUAGE) -> str:
	if not text or language == "en":
		return text
	return catalog(language).get(text, text)
