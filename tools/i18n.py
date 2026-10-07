"""Translation catalog maintenance (replaces Frappe's extractor).

    python tools/i18n.py              # extract, update main.pot and fa.po, list untranslated
    python tools/i18n.py --add f.json # also merge {"English": "فارسی"} translations from a JSON file

Sources: `_("...")` in backend Python (first argument, a string literal) and `__("...")` in
the PWA (.vue / .ts). Entries no longer used are kept in fa.po as obsolete (#~) so their
translations come back if the string is used again.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend" / "hozur"
FRONTEND = ROOT / "frontend" / "src"
LOCALE = BACKEND / "locale"
JS_CALL = re.compile(r"""\b__\(\s*(["'`])((?:\\.|(?!\1).)*)\1""", re.S)


def extract() -> dict[str, list[str]]:
	found: dict[str, list[str]] = {}

	def add(msgid: str, where: str) -> None:
		if msgid.strip():
			found.setdefault(msgid, []).append(where)

	for path in sorted(BACKEND.rglob("*.py")):
		rel = path.relative_to(ROOT)
		tree = ast.parse(path.read_text(encoding="utf-8"))
		for node in ast.walk(tree):
			if (
				isinstance(node, ast.Call)
				and isinstance(node.func, ast.Name)
				and node.func.id == "_"
				and node.args
				and isinstance(node.args[0], ast.Constant)
				and isinstance(node.args[0].value, str)
			):
				add(node.args[0].value, f"{rel}:{node.lineno}")
	if FRONTEND.exists():
		for path in sorted([*FRONTEND.rglob("*.vue"), *FRONTEND.rglob("*.ts")]):
			if path.name.endswith(".test.ts"):
				continue
			text = path.read_text(encoding="utf-8")
			rel = path.relative_to(ROOT)
			for m in JS_CALL.finditer(text):
				if m.group(1) == "`" and "${" in m.group(2):
					continue
				msgid = m.group(2).encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
				add(msgid, f"{rel}:{text.count(chr(10), 0, m.start()) + 1}")
	return found


def _q(text: str) -> str:
	return json.dumps(text, ensure_ascii=False)


def read_po(path: Path) -> dict[str, str]:
	"""msgid -> msgstr, including obsolete (#~) entries."""
	if not path.exists():
		return {}
	out: dict[str, str] = {}
	msgid = msgstr = None
	field = None
	for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
		line = raw[3:].strip() if raw.startswith("#~ ") else raw.strip()
		if not line or (line.startswith("#") and not raw.startswith("#~")):
			if not line and msgid:
				out[msgid] = msgstr or ""
				msgid = msgstr = field = None
			continue
		if line.startswith("msgctxt "):
			field = "ctx"
		elif line.startswith("msgid "):
			msgid, field = json.loads(line[6:]), "id"
		elif line.startswith("msgstr "):
			msgstr, field = json.loads(line[7:]), "str"
		elif line.startswith('"'):
			if field == "id":
				msgid += json.loads(line)
			elif field == "str":
				msgstr += json.loads(line)
	return {k: v for k, v in out.items() if k}


def header(language: str | None) -> str:
	stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M+0000")
	lines = [
		"# Hozur translations.",
		"# This file is distributed under the same license as the Hozur project (GPLv3).",
		"#",
		'msgid ""',
		'msgstr ""',
		'"Project-Id-Version: Hozur\\n"',
		'"Report-Msgid-Bugs-To: 219307864+AradFarab@users.noreply.github.com\\n"',
		f'"POT-Creation-Date: {stamp}\\n"',
		'"MIME-Version: 1.0\\n"',
		'"Content-Type: text/plain; charset=utf-8\\n"',
		'"Content-Transfer-Encoding: 8bit\\n"',
	]
	if language:
		lines.insert(-3, f'"Language: {language}\\n"')
	return "\n".join(lines) + "\n"


def write(found: dict[str, list[str]], existing: dict[str, str]) -> tuple[int, list[str]]:
	pot, po = [header(None)], [header("fa")]
	missing = []
	for msgid in sorted(found):
		refs = "#: " + " ".join(sorted(set(found[msgid])))
		pot.append(f"{refs}\nmsgid {_q(msgid)}\nmsgstr \"\"\n")
		translation = existing.get(msgid, "")
		if not translation:
			missing.append(msgid)
		po.append(f"{refs}\nmsgid {_q(msgid)}\nmsgstr {_q(translation)}\n")
	obsolete = sorted(k for k, v in existing.items() if k not in found and v)
	for msgid in obsolete:
		po.append(f"#~ msgid {_q(msgid)}\n#~ msgstr {_q(existing[msgid])}\n")
	(LOCALE / "main.pot").write_text("\n".join(pot), encoding="utf-8")
	(LOCALE / "fa.po").write_text("\n".join(po), encoding="utf-8")
	return len(obsolete), missing


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--add", type=Path, help="JSON file of English -> Persian translations to merge")
	parser.add_argument("--check", action="store_true", help="exit 1 when a string has no Persian translation")
	args = parser.parse_args()
	existing = read_po(LOCALE / "fa.po")
	if args.add:
		existing.update(json.loads(args.add.read_text(encoding="utf-8")))
	found = extract()
	obsolete, missing = write(found, existing)
	print(f"{len(found)} strings, {len(found) - len(missing)} translated, {obsolete} kept as obsolete")
	for msgid in missing:
		print("untranslated:", json.dumps(msgid, ensure_ascii=False))
	return 1 if (args.check and missing) else 0


if __name__ == "__main__":
	sys.exit(main())
