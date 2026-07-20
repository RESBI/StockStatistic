import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V31_ROOTS = (ROOT / "packages", ROOT / "services")
LEGACY_IMPORT_ROOTS = {"stockstat_backend", "stockstat_compute"}


def test_contracts_do_not_load_heavy_dependencies():
    before = set(sys.modules)
    importlib.import_module("stockstat_contracts")
    loaded = set(sys.modules) - before
    assert not ({"pandas", "numpy", "fastapi", "sqlalchemy", "httpx"} & loaded)


def test_v31_source_does_not_import_legacy_packages():
    violations = []
    for source_root in V31_ROOTS:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots = {node.module.split(".", 1)[0]}
                else:
                    continue
                if roots & LEGACY_IMPORT_ROOTS:
                    violations.append(str(path.relative_to(ROOT)))
    assert not violations


def test_dispatcher_and_storage_do_not_import_kernel():
    for relative in ("services/dispatcher", "services/storage"):
        for path in (ROOT / relative).rglob("*.py"):
            assert "stockstat_kernel" not in path.read_text(encoding="utf-8")
