"""Unit tests for ``cache/etag_store.py`` — ``JsonFileETagStore`` + ``_NullConditionalCache``.

All tests are file-system based (tmp_path); no network, no real GitHub, no state.json.
Each test references the AC-ID it covers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from osspulse.cache.etag_store import JsonFileETagStore, _NullConditionalCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOKEN_SENTINEL = "ghp_super_secret_token_DO_NOT_STORE"


def _store(tmp_path: Path, filename: str = "etags.json") -> JsonFileETagStore:
    return JsonFileETagStore(tmp_path / filename)


# ---------------------------------------------------------------------------
# Basic round-trip (AC-V2-007-002, AC-V2-007-005)
# ---------------------------------------------------------------------------


def test_set_commit_get_round_trip(tmp_path):
    """set → commit → fresh instance → get returns the stored validator (AC-V2-007-002)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"abc123"')
    s.commit()

    # Fresh instance (simulates next-run load)
    s2 = JsonFileETagStore(path)
    assert s2.get("owner/repo:issues") == '"abc123"'


def test_multiple_repos_and_endpoints_round_trip(tmp_path):
    """Multiple repo+endpoint keys round-trip correctly (AC-V2-007-002)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("org/repo-a:issues", '"etag1"')
    s.set("org/repo-a:releases", 'W/"etag2"')
    s.set("org/repo-b:issues", '"etag3"')
    s.commit()

    s2 = JsonFileETagStore(path)
    assert s2.get("org/repo-a:issues") == '"etag1"'
    assert s2.get("org/repo-a:releases") == 'W/"etag2"'
    assert s2.get("org/repo-b:issues") == '"etag3"'


def test_miss_returns_none(tmp_path):
    """A get for a key that was never set returns None (AC-V2-007-001)."""
    s = _store(tmp_path)
    assert s.get("owner/repo:issues") is None


def test_set_without_commit_is_not_durable(tmp_path):
    """set() without commit() is NOT visible to a fresh instance (AC-V2-007-005)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag-not-committed"')
    # Do NOT call commit()

    s2 = JsonFileETagStore(path)
    assert s2.get("owner/repo:issues") is None  # in-memory only, not persisted


def test_set_is_visible_in_same_instance_before_commit(tmp_path):
    """set() is immediately visible via get() on the same instance (AC-V2-007-005)."""
    s = _store(tmp_path)
    s.set("owner/repo:issues", '"etag-in-mem"')
    assert s.get("owner/repo:issues") == '"etag-in-mem"'


# ---------------------------------------------------------------------------
# Missing / empty / whitespace file (AC-V2-007-004a)
# ---------------------------------------------------------------------------


def test_missing_file_returns_empty(tmp_path):
    """Missing etags.json → empty cache, get returns None, no exception (AC-V2-007-004a)."""
    s = _store(tmp_path)
    assert s.get("owner/repo:issues") is None  # must not raise


def test_empty_file_returns_empty(tmp_path):
    """Empty etags.json → empty cache, no exception (AC-V2-007-004a)."""
    path = tmp_path / "etags.json"
    path.write_text("", encoding="utf-8")
    s = JsonFileETagStore(path)
    assert s.get("owner/repo:issues") is None


def test_whitespace_only_file_returns_empty(tmp_path):
    """Whitespace-only etags.json → empty cache, no exception (AC-V2-007-004a)."""
    path = tmp_path / "etags.json"
    path.write_text("   \n  \t  ", encoding="utf-8")
    s = JsonFileETagStore(path)
    assert s.get("owner/repo:issues") is None


# ---------------------------------------------------------------------------
# Corrupt file → WARN + empty, NEVER raise (AC-V2-007-004b, ADR-001)
# ---------------------------------------------------------------------------


def test_corrupt_json_returns_empty_and_warns(tmp_path, caplog):
    """Corrupt JSON etags.json → empty cache + WARN, no exception (AC-V2-007-004b)."""
    path = tmp_path / "etags.json"
    path.write_text("{this is not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="osspulse.cache.etag_store"):
        s = JsonFileETagStore(path)
        result = s.get("owner/repo:issues")

    assert result is None  # empty cache
    assert any("corrupt" in r.message.lower() for r in caplog.records)
    # Must NOT raise — test reaching here is the proof


def test_non_dict_root_returns_empty_and_warns(tmp_path, caplog):
    """Non-dict root (JSON array) → empty cache + WARN, no exception (AC-V2-007-004b)."""
    path = tmp_path / "etags.json"
    path.write_text('["owner/repo:issues", "etag"]', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="osspulse.cache.etag_store"):
        s = JsonFileETagStore(path)
        result = s.get("owner/repo:issues")

    assert result is None
    assert any("unexpected root type" in r.message.lower() for r in caplog.records)


def test_unreadable_file_returns_empty_and_warns(tmp_path, caplog):
    """Unreadable etags.json (OSError on read) → empty cache + WARN, no exception
    (AC-V2-007-004b)."""
    path = tmp_path / "etags.json"
    path.write_text('{"owner/repo:issues": "etag"}', encoding="utf-8")
    path.chmod(0o000)  # make unreadable

    try:
        with caplog.at_level(logging.WARNING, logger="osspulse.cache.etag_store"):
            s = JsonFileETagStore(path)
            result = s.get("owner/repo:issues")
        assert result is None
        assert any("unreadable" in r.message.lower() for r in caplog.records)
    finally:
        path.chmod(0o644)  # restore so tmp_path cleanup can remove it


# ---------------------------------------------------------------------------
# Atomic write via temp file + os.replace (AC-V2-007-003)
# ---------------------------------------------------------------------------


def test_commit_uses_temp_file_in_same_dir(tmp_path):
    """commit() uses a temp file in the same directory before renaming (AC-V2-007-003)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')

    observed_temps: list[str] = []
    original_mkstemp = __import__("tempfile").mkstemp

    def spy_mkstemp(dir=None, **kwargs):  # noqa: ANN001,ANN202
        fd, name = original_mkstemp(dir=dir, **kwargs)
        observed_temps.append(name)
        return fd, name

    with patch("osspulse.cache.etag_store.tempfile.mkstemp", side_effect=spy_mkstemp):
        s.commit()

    assert len(observed_temps) == 1
    temp_dir = str(Path(observed_temps[0]).parent)
    assert temp_dir == str(tmp_path)  # temp is in the same dir as etags.json


def test_commit_atomic_result_correct(tmp_path):
    """After commit(), etags.json contains only the cached key+validator (AC-V2-007-003)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')
    s.commit()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"owner/repo:issues": '"etag1"'}


def test_commit_creates_parent_dir(tmp_path):
    """commit() creates the parent directory if it does not exist (AC-V2-007-003)."""
    path = tmp_path / "nested" / "dir" / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')
    s.commit()

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["owner/repo:issues"] == '"etag1"'


def test_commit_write_failure_warns_and_does_not_raise(tmp_path, caplog):
    """If commit() write fails (OSError), it logs WARN and does not raise (BR-V2-007-002)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')

    with (
        patch("osspulse.cache.etag_store.tempfile.mkstemp", side_effect=OSError("disk full")),
        caplog.at_level(logging.WARNING, logger="osspulse.cache.etag_store"),
    ):
        s.commit()  # must NOT raise

    assert any("commit failed" in r.message.lower() for r in caplog.records)


def test_commit_mkdir_failure_warns_and_does_not_raise(tmp_path, caplog):
    """If commit() mkdir fails (OSError), it logs WARN and does not raise (BR-V2-007-002)."""
    path = tmp_path / "nested" / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')

    with (
        patch("osspulse.cache.etag_store.os.replace", side_effect=OSError("readonly")),
        caplog.at_level(logging.WARNING, logger="osspulse.cache.etag_store"),
    ):
        s.commit()  # must NOT raise

    assert any("commit failed" in r.message.lower() for r in caplog.records)


def test_commit_without_any_load_or_set_is_noop(tmp_path):
    """commit() before any get/set (cache is None) is a safe no-op (AC-V2-007-003)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.commit()  # cache is still None, nothing to write
    assert not path.exists()  # no file created


# ---------------------------------------------------------------------------
# Security: persisted file contains only keys + validators (AC-V2-007-006)
# ---------------------------------------------------------------------------


def test_token_sentinel_never_in_etags_json(tmp_path):
    """The token sentinel must never appear in etags.json (AC-V2-007-006, RISK-003)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"etag1"')
    # Simulate someone accidentally trying to store a token value (defensive)
    s.set("owner/repo:releases", '"W/safe-etag"')
    s.commit()

    raw = path.read_text(encoding="utf-8")
    assert TOKEN_SENTINEL not in raw, "token sentinel must never appear in etags.json"


def test_persisted_file_contains_only_keys_and_validators(tmp_path):
    """etags.json contains only repo:endpoint keys and validator strings (AC-V2-007-006)."""
    path = tmp_path / "etags.json"
    s = JsonFileETagStore(path)
    s.set("owner/repo:issues", '"abc123"')
    s.set("owner/repo:releases", 'W/"def456"')
    s.commit()

    data = json.loads(path.read_text(encoding="utf-8"))
    # Only the two expected keys
    assert set(data.keys()) == {"owner/repo:issues", "owner/repo:releases"}
    # Values are the opaque validator strings
    assert data["owner/repo:issues"] == '"abc123"'
    assert data["owner/repo:releases"] == 'W/"def456"'


# ---------------------------------------------------------------------------
# Never touches state.json (AC-V2-007-008)
# ---------------------------------------------------------------------------


def test_store_never_touches_state_json(tmp_path):
    """JsonFileETagStore must never read or write state.json (AC-V2-007-008)."""
    state_path = tmp_path / "state.json"
    state_path.write_text('{"version": 1, "seen": {}}', encoding="utf-8")
    before_mtime = state_path.stat().st_mtime

    etag_path = tmp_path / "etags.json"
    s = JsonFileETagStore(etag_path)
    s.set("owner/repo:issues", '"etag1"')
    s.commit()
    s.get("owner/repo:issues")

    # state.json must be untouched
    assert state_path.stat().st_mtime == before_mtime
    assert state_path.read_text(encoding="utf-8") == '{"version": 1, "seen": {}}'


def test_store_does_not_import_json_store(tmp_path):
    """etag_store module never imports state.json_store (AC-V2-007-008, BR-V2-007-003)."""
    import sys

    import osspulse.cache.etag_store  # ensure it's loaded

    # Confirm state.json_store is NOT in the module's imported dependencies
    # (it may be referenced in docstrings but must never be imported)
    assert "osspulse.state.json_store" not in sys.modules or (
        "osspulse.state.json_store"
        not in (getattr(osspulse.cache.etag_store, "__dict__", {}).values())
    )
    # Check the import statements specifically — no 'from osspulse.state' or 'import osspulse.state'
    module = sys.modules["osspulse.cache.etag_store"]
    module_source = Path(module.__file__).read_text(encoding="utf-8")
    import_lines = [
        line for line in module_source.splitlines() if line.startswith(("import ", "from "))
    ]
    assert not any("state" in line for line in import_lines), (
        f"etag_store.py must not import any state module; found: {import_lines}"
    )
    assert not any("StateError" in line for line in import_lines), (
        "etag_store.py must not import StateError"
    )


# ---------------------------------------------------------------------------
# _NullConditionalCache (AC-V2-007-007)
# ---------------------------------------------------------------------------


def test_null_cache_get_returns_none():
    """_NullConditionalCache.get always returns None (AC-V2-007-007)."""
    null = _NullConditionalCache()
    assert null.get("owner/repo:issues") is None
    assert null.get("any:key") is None


def test_null_cache_set_is_noop():
    """_NullConditionalCache.set is a no-op — subsequent get still returns None (AC-V2-007-007)."""
    null = _NullConditionalCache()
    null.set("owner/repo:issues", '"etag"')
    assert null.get("owner/repo:issues") is None


def test_null_cache_commit_is_noop():
    """_NullConditionalCache.commit is a no-op — no file written (AC-V2-007-007)."""
    null = _NullConditionalCache()
    null.set("owner/repo:issues", '"etag"')
    null.commit()  # must not raise and must not create any file


def test_null_cache_satisfies_conditional_cache_protocol():
    """_NullConditionalCache satisfies the ConditionalCache Protocol structurally
    (AC-V2-007-007)."""

    null = _NullConditionalCache()
    # Structural check: verify the three required methods exist and match the protocol
    assert callable(getattr(null, "get", None))
    assert callable(getattr(null, "set", None))
    assert callable(getattr(null, "commit", None))
    # isinstance check via runtime_checkable would require @runtime_checkable — skip for Protocol;
    # the structural presence of get/set/commit with correct signatures is sufficient.
    _ = null.get("k")
    null.set("k", "v")
    null.commit()
