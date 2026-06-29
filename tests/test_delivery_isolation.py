"""Static import-isolation tests for delivery/ (AC-6-002, AC-6-003).

Verifies that no file in ``osspulse.delivery`` imports upstream pipeline modules
(github, summarizer, cache, render) or references domain models (Digest, RawItem,
SummarizedItem). Uses AST inspection — no runtime import side-effects.
Mirrors renderer AC-5-003 / summarizer AC-4-021.
"""

import ast
from pathlib import Path

_DELIVERY_DIR = Path(__file__).parent.parent / "src" / "osspulse" / "delivery"

_FORBIDDEN_MODULES = [
    "osspulse.github",
    "osspulse.summarizer",
    "osspulse.cache",
    "osspulse.render",
]

_FORBIDDEN_NAMES = {"Digest", "RawItem", "SummarizedItem"}


def _imports_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def _names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _delivery_py_files() -> list[Path]:
    return list(_DELIVERY_DIR.glob("*.py"))


def test_delivery_imports_no_upstream_modules(AC="AC-6-002"):
    """delivery/*.py must not import github/summarizer/cache/render (AC-6-002)."""
    violations: list[str] = []
    for f in _delivery_py_files():
        for mod in _imports_in(f):
            if any(mod.startswith(forbidden) for forbidden in _FORBIDDEN_MODULES):
                violations.append(f"{f.name}: imports {mod}")
    assert violations == [], "\n".join(violations)


def test_delivery_does_not_reference_domain_models(AC="AC-6-003"):
    """delivery/*.py must not reference Digest, RawItem, or SummarizedItem (AC-6-003)."""
    violations: list[str] = []
    for f in _delivery_py_files():
        names = _names_in(f)
        bad = names & _FORBIDDEN_NAMES
        if bad:
            violations.append(f"{f.name}: references {bad}")
    assert violations == [], "\n".join(violations)


def test_delivery_dir_has_expected_files():
    """Sanity: expected delivery module files exist."""
    names = {f.name for f in _delivery_py_files()}
    assert "errors.py" in names
    assert "file_delivery.py" in names
    assert "stdout_delivery.py" in names
    assert "__init__.py" in names
