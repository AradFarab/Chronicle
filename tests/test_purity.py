"""The engine and the Jalali core must stay pure Python (CLAUDE.md rule 3)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PURE_PACKAGES = ["hozur/jalali", "hozur/engine"]


def _imports(path: Path) -> set[str]:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	names = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			names.update(alias.name.split(".")[0] for alias in node.names)
		elif isinstance(node, ast.ImportFrom) and node.module:
			names.add(node.module.split(".")[0])
	return names


@pytest.mark.parametrize("package", PURE_PACKAGES)
def test_pure_packages_do_not_import_frappe(package):
	files = list((ROOT / package).rglob("*.py"))
	offenders = [str(f.relative_to(ROOT)) for f in files if "frappe" in _imports(f)]
	assert not offenders, f"frappe imported in pure package: {offenders}"
