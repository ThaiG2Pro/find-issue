"""Static import-isolation tests for the Digest Renderer (AC-5-002, AC-5-003, EC-012).

Verifies that ``osspulse.render.renderer`` and ``osspulse.render.__init__`` do NOT
import any upstream pipeline modules (osspulse.github, osspulse.state,
osspulse.summarizer, osspulse.cache).  Uses ``ast`` to inspect source — no runtime
import side-effects.  Mirrors the summarizer AC-4-021 static test.

Rules:
- All test names carry their AC-ID (R3).
"""

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).parent.parent / "src" / "osspulse" / "render"

FORBIDDEN_PREFIXES = [
    "osspulse.github",
    "osspulse.state",
    "osspulse.summarizer",
    "osspulse.cache",
]


def _collect_imports(source_path: Path) -> list[str]:
    """Return a flat list of all imported module names in *source_path* via ``ast``."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _assert_no_forbidden(imports: list[str], source_label: str) -> None:
    """Raise AssertionError if any import starts with a forbidden prefix."""
    violations = [
        imp
        for imp in imports
        for prefix in FORBIDDEN_PREFIXES
        if imp == prefix or imp.startswith(prefix + ".")
    ]
    assert violations == [], (
        f"{source_label} must NOT import upstream pipeline modules; found: {violations!r}"
    )


# ---------------------------------------------------------------------------
# AC-5-003 / EC-012: renderer.py has no upstream imports
# ---------------------------------------------------------------------------


class TestRendererModuleImportIsolation:
    def test_renderer_py_no_upstream_imports_ac_5_003(self) -> None:
        """renderer.py does not import github/state/summarizer/cache (AC-5-003, EC-012)."""
        renderer_path = _SRC_ROOT / "renderer.py"
        assert renderer_path.exists(), f"renderer.py not found at {renderer_path}"
        imports = _collect_imports(renderer_path)
        _assert_no_forbidden(imports, "renderer.py")

    def test_renderer_py_imports_only_models_and_stdlib_ac_5_003(self) -> None:
        """renderer.py imports only osspulse.models and stdlib (AC-5-003)."""
        renderer_path = _SRC_ROOT / "renderer.py"
        imports = _collect_imports(renderer_path)
        osspulse_imports = [i for i in imports if i.startswith("osspulse.")]
        # Only osspulse.models is allowed
        disallowed = [
            i
            for i in osspulse_imports
            if i != "osspulse.models" and not i.startswith("osspulse.models.")
        ]
        assert disallowed == [], (
            f"renderer.py may only import from osspulse.models; found: {disallowed!r}"
        )


# ---------------------------------------------------------------------------
# AC-5-002 / EC-012: __init__.py has no upstream imports
# ---------------------------------------------------------------------------


class TestInitModuleImportIsolation:
    def test_init_py_no_upstream_imports_ac_5_003(self) -> None:
        """render/__init__.py has no import of osspulse.github/state/summarizer/cache (AC-5-003)."""
        init_path = _SRC_ROOT / "__init__.py"
        assert init_path.exists(), f"render/__init__.py not found at {init_path}"
        imports = _collect_imports(init_path)
        _assert_no_forbidden(imports, "render/__init__.py")

    def test_init_py_exports_render_and_adapter_ac_5_002(self) -> None:
        """render package exports both 'render' and 'MarkdownDigestRenderer' (AC-5-002)."""
        from osspulse.render import MarkdownDigestRenderer, render  # noqa: PLC0415

        assert callable(render)
        assert callable(MarkdownDigestRenderer)

    def test_port_structural_conformance_ac_5_002(self) -> None:
        """MarkdownDigestRenderer structurally satisfies DigestRenderer Protocol (AC-5-002)."""
        from osspulse.render import MarkdownDigestRenderer  # noqa: PLC0415

        # DigestRenderer is a Protocol — verify MarkdownDigestRenderer has the required method
        assert hasattr(MarkdownDigestRenderer, "render"), (
            "MarkdownDigestRenderer must have a 'render' method to satisfy DigestRenderer"
        )
        assert callable(getattr(MarkdownDigestRenderer, "render"))
