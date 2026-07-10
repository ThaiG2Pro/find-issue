"""ETag conditional-request cache adapter (V2, AC-V2-007-002..008).

``JsonFileETagStore`` — persists per-``"{repo}:{endpoint}"`` HTTP validators to a
**separate** ``etags.json`` file (NOT ``state.json``).

⚠️  DELIBERATE OPPOSITE of ``state/json_store.py``:
    - ``state.json`` is FATAL on corruption → ``StateError`` (idempotency-critical).
    - ``etags.json`` is BEST-EFFORT on corruption → empty cache + WARN, never raise
      (it is a pure rate-limit optimisation; losing it costs one unconditional refetch,
      never correctness — ADR-001, BR-V2-007-002).
Do NOT copy ``json_store.load()``'s raise-on-corrupt here.

Security: only ``"{repo}:{endpoint}"`` keys and opaque validator strings are stored —
never the ``GITHUB_TOKEN``, response bodies, or any PII (BR-V2-007-001, AC-V2-007-006).
Imports: stdlib + ``osspulse.ports`` only — NEVER imports ``state.json_store``
or any stage module (AC-V2-007-008, BR-V2-007-003).

``_NullConditionalCache`` lives in ``osspulse.ports`` and is re-exported here
for convenience; the collector imports it from ``osspulse.ports`` directly so the
pure-I/O boundary (AC-2-015) is respected.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

# Re-export from ports so existing `from osspulse.cache.etag_store import _NullConditionalCache`
# still works, without the collector having to import from osspulse.cache.
from osspulse.ports import _NullConditionalCache

__all__ = ["JsonFileETagStore", "_NullConditionalCache"]

logger = logging.getLogger(__name__)


class JsonFileETagStore:
    """Concrete ``ConditionalCache`` adapter backed by a flat JSON file (ADR-001/002).

    ``get``/``set`` operate on an in-memory dict; the durable write only occurs when
    ``commit()`` is called explicitly (ADR-002, AC-V2-007-005).

    ``load()`` is called lazily on the first ``get``/``set`` call.  On any load
    failure (missing file, empty file, corrupt JSON, non-dict root, OSError) the
    store silently degrades to an empty in-memory cache — no exception is raised,
    only a WARN is logged when the failure is unexpected (AC-V2-007-004).

    ``commit()`` writes the current in-memory cache atomically via
    ``tempfile.mkstemp(dir=path.parent)`` → ``fsync`` → ``os.replace``
    (mirrors ``state/json_store.py`` ``save()``; AC-V2-007-003).  On any write
    failure it logs WARN and swallows — best-effort, the run already succeeded.
    """

    def __init__(self, etag_path: str | Path) -> None:
        self._path = Path(etag_path)
        self._cache: dict[str, str] | None = None  # None = not yet loaded

    # ------------------------------------------------------------------
    # Internal load — lazy, best-effort (ADR-001)
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load ``etags.json`` into ``self._cache`` exactly once, best-effort.

        Missing file  → empty cache (normal first run, no WARN needed).
        Empty/whitespace → empty cache (no WARN — could be an intentional reset).
        Corrupt / non-dict / unreadable → empty cache + WARN (unexpected).
        Never raises (AC-V2-007-004, ADR-001).
        """
        if self._cache is not None:
            return  # already loaded

        # Default: start empty
        self._cache = {}

        if not self._path.exists():
            return  # AC-V2-007-004a: missing → empty, no WARN (normal first run)

        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            # Unreadable (permissions, etc.) — WARN + empty
            logger.warning(
                "etags.json unreadable (%s); starting with empty cache",
                type(exc).__name__,
            )
            return

        if not raw.strip():
            return  # empty / whitespace-only → empty cache, no WARN

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Corrupt JSON — WARN + empty (AC-V2-007-004b, ADR-001)
            logger.warning(
                "etags.json is corrupt (%s); starting with empty cache",
                type(exc).__name__,
            )
            return

        if not isinstance(data, dict):
            # Non-dict root (e.g. a JSON array) — WARN + empty
            logger.warning(
                "etags.json has unexpected root type %s; starting with empty cache",
                type(data).__name__,
            )
            return

        # Valid dict — accept it, but only keep str→str entries (defensive)
        self._cache = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    # ------------------------------------------------------------------
    # ConditionalCache port (AC-V2-007-001..005)
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        """Return the cached validator for *key*, or ``None`` on a miss (AC-V2-007-001)."""
        self._ensure_loaded()
        assert self._cache is not None  # guaranteed by _ensure_loaded  # noqa: S101
        return self._cache.get(key)

    def set(self, key: str, validator: str) -> None:  # noqa: A003
        """Update *key* → *validator* in the IN-MEMORY cache only (AC-V2-007-005).

        Nothing is written to disk until ``commit()`` is called.
        Security: only opaque validator strings — never the token (AC-V2-007-006).
        """
        self._ensure_loaded()
        assert self._cache is not None  # guaranteed by _ensure_loaded  # noqa: S101
        self._cache[key] = validator

    def commit(self) -> None:
        """Flush the in-memory cache to ``etags.json`` atomically, best-effort (AC-V2-007-003).

        Uses ``tempfile.mkstemp(dir=path.parent)`` → ``fsync`` → ``os.replace``
        (mirrors ``state/json_store.py`` ``save()`` — same-dir temp for atomic rename).
        Any write failure → WARN + swallow; the run already succeeded (BR-V2-007-002).
        """
        if self._cache is None:
            return  # nothing was ever loaded/set — nothing to commit

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "etags.json commit: cannot create directory (%s); cache not persisted",
                type(exc).__name__,
            )
            return

        tmp_name: str | None = None
        try:
            # AC-V2-007-003: temp in same dir → os.replace is atomic on POSIX
            fd, tmp_name = tempfile.mkstemp(dir=self._path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._cache, fh, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self._path)
            tmp_name = None  # successfully renamed; do not unlink
        except OSError as exc:
            logger.warning(
                "etags.json commit failed (%s); cache not persisted (best-effort)",
                type(exc).__name__,
            )
        finally:
            # Clean up orphaned temp file on any failure (mirrors json_store.save)
            if tmp_name is not None:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass  # best-effort cleanup — a leftover temp is harmless
