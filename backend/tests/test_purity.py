"""Pure layers stay free of the database and the web framework (CLAUDE.md rule 3)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PURE_MODULES = [
	"hozur/engine",
	"hozur/jalali",
	"hozur/devices/base.py",
	"hozur/devices/zkteco.py",
	"hozur/devices/file_import.py",
	"hozur/reports/catalog.py",
	"hozur/reports/exporters.py",
]
FORBIDDEN = {"frappe", "sqlalchemy", "fastapi", "starlette", "psycopg", "alembic"}
FORBIDDEN_HOZUR = ("hozur.db", "hozur.services", "hozur.api")


def _imports(path: Path) -> set[str]:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	names = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			names.update(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom) and node.module:
			names.add(node.module)
	return names


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_modules_stay_pure(module):
	target = ROOT / module
	files = [target] if target.is_file() else list(target.rglob("*.py"))
	offenders = []
	for f in files:
		for name in _imports(f):
			if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN_HOZUR):
				offenders.append(f"{f.relative_to(ROOT)}: {name}")
	assert not offenders, offenders
