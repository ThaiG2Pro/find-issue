"""JSON-file state store adapter — implements osspulse.ports.StateStore (AC-3-017, AC-3-018).

Only imports: osspulse.models, osspulse.state.errors, and stdlib.  No GitHub, LLM, or
network imports are allowed in this module (AC-3-017, BR-3-008).
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from osspulse.models import RawItem
from osspulse.state.errors import StateError

# The only supported version for V1 state files (AC-3-014).
_STATE_VERSION = 1

# Sentinel for an empty-but-valid state document.
_EMPTY_STATE: dict = {"version": _STATE_VERSION, "seen": {}}


def _identity_key(item_type: str, item_id: str) -> str:
    """Return the compound key used inside a repo bucket (AC-3-005).

    Empty ``item_id`` is valid and yields e.g. ``"issue:"`` — do not reject (EC-002).
    """
    return f"{item_type}:{item_id}"


def _now_utc_z() -> str:
    """Return the current UTC time as ISO-8601 with a trailing ``Z`` (AC-3-003).

    Format ``%Y-%m-%dT%H:%M:%SZ`` matches ``RawItem.created_at``.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JsonFileStateStore:
    """Concrete ``StateStore`` adapter backed by a single UTF-8 JSON file (ADR-002/003).

    Implements the ``osspulse.ports.StateStore`` Protocol structurally (no subclassing
    required — Python structural typing).  The helpers ``is_seen`` / ``mark_seen`` are
    intentionally NOT on the Protocol (ADR-001, AC-3-018).

    The in-memory state is lazily loaded on the first call that needs it and is cached
    for the lifetime of this instance — ``load`` is called at most once per run.
    """

    def __init__(self, state_path: str | Path) -> None:
        self._path = Path(state_path)
        self._cached: dict | None = None  # lazy; None = not yet loaded

    # ------------------------------------------------------------------
    # StateStore Protocol methods
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load state from the JSON file, returning a plain dict (AC-3-001/002).

        Sequence (design §Sequence Flow 1):
        1. File missing         → empty state           (AC-3-002)
        2. File 0-byte/spaces   → empty state           (AC-3-011)
        3. Bad JSON             → StateError            (AC-3-009)
        4. Unknown version      → StateError            (AC-3-010)
        5. Missing ``seen`` key → empty ``seen``        (AC-3-012)
        6. Valid               → return dict
        """
        # 1. Missing file → empty
        if not self._path.exists():
            state = {"version": _STATE_VERSION, "seen": {}}
            self._cached = state
            return dict(state)

        raw = self._path.read_text(encoding="utf-8")

        # 2. 0-byte / whitespace-only → empty (check BEFORE json.loads — AC-3-011)
        if not raw.strip():
            state = {"version": _STATE_VERSION, "seen": {}}
            self._cached = state
            return dict(state)

        # 3. Parse JSON; bad JSON → StateError (AC-3-009)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StateError(f"state file is corrupt: {exc}") from exc

        # 3b. Root must be a JSON object (dict); null/array/scalar → StateError (AC-3-009)
        if not isinstance(data, dict):
            raise StateError(
                f"state file is corrupt: expected a JSON object, got {type(data).__name__}"
            )

        # 4. Version check — bool-trap guard mirrors config.py:_validate_lookback (AC-3-010)
        version = data.get("version")
        if type(version) is not int:  # noqa: E721 — bool trap: isinstance(True, int) is True
            raise StateError(f"unsupported state version {version!r} (expected {_STATE_VERSION})")
        if version != _STATE_VERSION:
            raise StateError(f"unsupported state version {version} (expected {_STATE_VERSION})")

        # 5. Missing "seen" → tolerate as empty (AC-3-012)
        if "seen" not in data:
            data["seen"] = {}

        self._cached = data
        return data

    def save(self, state: dict) -> None:
        """Write state atomically: mkdir → temp-write → fsync → os.replace (ADR-002).

        The temp file is created in ``state_path.parent`` so that ``os.replace`` is a
        same-filesystem rename (atomic on POSIX and Windows same-volume — AC-3-007/008).
        Parent directory is created before opening the temp file there (AC-3-015).
        On any error the temp file is cleaned up and a ``StateError`` is raised (AC-3-016).
        """
        # AC-3-015: create parent dir before opening temp file there (ordering is critical)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateError(f"cannot write state to {self._path}: {exc}") from exc

        tmp_name: str | None = None
        try:
            # AC-3-007: temp file in the same directory as the target
            fd, tmp_name = tempfile.mkstemp(dir=self._path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            # AC-3-007: atomic rename — on POSIX this is atomic; same-vol on Windows
            os.replace(tmp_name, self._path)
            tmp_name = None  # successfully renamed; don't unlink
        except OSError as exc:
            raise StateError(f"cannot write state to {self._path}: {exc}") from exc
        finally:
            # AC-3-016: clean up orphaned temp file on any failure
            if tmp_name is not None:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass  # best-effort cleanup; leftover temp is harmless (ADR-002)

        # Keep the in-memory cache consistent
        self._cached = state

    # ------------------------------------------------------------------
    # Adapter-only helpers (NOT on the StateStore Protocol — ADR-001, AC-3-018)
    # ------------------------------------------------------------------

    def is_seen(self, repo: str, item_type: str, item_id: str) -> bool:
        """Return True if the item is already recorded in the loaded state (AC-3-003/005).

        Lazily loads state once if not yet loaded.
        """
        if self._cached is None:
            self.load()
        assert self._cached is not None  # noqa: S101 — guaranteed by load()
        key = _identity_key(item_type, item_id)
        return key in self._cached["seen"].get(repo, {})

    def mark_seen(self, items: list[RawItem]) -> None:
        """Record not-yet-seen items with the current UTC timestamp and persist (AC-3-003/004/006).

        - Empty list is a safe no-op (AC-3-006).
        - ``first_seen_at`` is write-once: never overwritten on re-mark (AC-3-004).
        - Empty ``item_id`` is valid and keys safely as ``"{item_type}:"`` (AC-3-005/EC-002).
        """
        if self._cached is None:
            self.load()
        assert self._cached is not None  # noqa: S101 — guaranteed by load()

        state = self._cached
        seen = state.setdefault("seen", {})
        changed = False
        for item in items:
            key = _identity_key(item.item_type, item.item_id)
            bucket = seen.setdefault(item.repo, {})
            if key not in bucket:  # AC-3-004: never overwrite first_seen_at
                bucket[key] = _now_utc_z()
                changed = True

        # Persist only when something actually changed (AC-3-006: empty list is a true no-op)
        if changed:
            self.save(state)
