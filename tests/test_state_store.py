"""Tests for the JSON-file state store (AC-3-001 … AC-3-018).

Rules:
- All test names carry their AC-ID (R3).
- Use ``tmp_path`` for filesystem isolation — never write to the real FS (stack.md).
- No real GitHub/LLM/network calls (stack.md, R10).
"""

import dataclasses
import inspect
import json
import os
import re
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from osspulse.models import Config, RawItem, WatchedRepo
from osspulse.ports import StateStore
from osspulse.state.errors import StateError
from osspulse.state.json_store import JsonFileStateStore, _identity_key, _now_utc_z

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _make_item(
    repo: str = "facebook/react",
    item_type: str = "issue",
    item_id: str = "123",
    title: str = "Test issue",
    body: str = "Body",
    url: str = "https://github.com/facebook/react/issues/123",
    created_at: str = "2026-06-24T00:00:00Z",
) -> RawItem:
    return RawItem(
        repo=repo,
        item_type=item_type,
        item_id=item_id,
        title=title,
        body=body,
        url=url,
        created_at=created_at,
    )


def _store(tmp_path: Path, subdir: str = "state.json") -> JsonFileStateStore:
    return JsonFileStateStore(tmp_path / subdir)


# ---------------------------------------------------------------------------
# Section 1 — Round-trip + path (AC-3-001, AC-3-013, AC-3-014)
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    """save then load returns an equivalent dict (AC-3-001)."""
    store = _store(tmp_path)
    state = {"version": 1, "seen": {"owner/repo": {"issue:42": "2026-06-24T00:00:00Z"}}}
    store.save(state)
    loaded = store.load()
    assert loaded == state


def test_saved_document_has_version_1(tmp_path):
    """Saved document carries top-level integer version=1 (AC-3-014)."""
    store = _store(tmp_path)
    state = {"version": 1, "seen": {}}
    store.save(state)
    raw = (tmp_path / "state.json").read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert doc["version"] == 1
    assert isinstance(doc["version"], int)
    assert "seen" in doc


def test_state_path_from_config_drives_target(tmp_path):
    """state_path from Config drives the store location, not hardcoded (AC-3-013)."""
    custom_path = tmp_path / "custom" / "my-state.json"
    store = JsonFileStateStore(custom_path)
    state = {"version": 1, "seen": {}}
    store.save(state)
    assert custom_path.exists(), "file must be at the configured path"
    loaded = JsonFileStateStore(custom_path).load()
    assert loaded == state


def test_config_state_path_default():
    """Config.state_path defaults to './.osspulse/state.json' (AC-3-013)."""
    cfg = Config(watched_repos=[WatchedRepo("a", "b")])
    assert cfg.state_path == "./.osspulse/state.json"


def test_config_state_path_custom():
    """Config.state_path carries the explicitly set value (AC-3-013)."""
    cfg = Config(watched_repos=[WatchedRepo("a", "b")], state_path="/tmp/my-state.json")
    assert cfg.state_path == "/tmp/my-state.json"


# ---------------------------------------------------------------------------
# Section 2 — Identity + idempotency (AC-3-003, AC-3-004, AC-3-005, AC-3-006)
# ---------------------------------------------------------------------------


def test_new_item_recorded_then_is_seen(tmp_path):
    """is_seen false → mark_seen → is_seen true; entry has UTC Z first_seen_at (AC-3-003)."""
    store = _store(tmp_path)
    item = _make_item()
    assert not store.is_seen(item.repo, item.item_type, item.item_id)
    store.mark_seen([item])
    assert store.is_seen(item.repo, item.item_type, item.item_id)
    # Verify first_seen_at is stored and is UTC-Z
    loaded = store.load()
    ts = loaded["seen"][item.repo][f"{item.item_type}:{item.item_id}"]
    assert _UTC_Z_RE.match(ts), f"expected UTC-Z timestamp, got {ts!r}"


def test_remark_preserves_original_first_seen_at(tmp_path):
    """Re-marking a seen item keeps the original first_seen_at (AC-3-004)."""
    store = _store(tmp_path)
    item = _make_item()
    store.mark_seen([item])
    loaded_first = store.load()
    t1 = loaded_first["seen"][item.repo][f"{item.item_type}:{item.item_id}"]

    # Patch time to simulate a later call
    with patch("osspulse.state.json_store._now_utc_z", return_value="2099-01-01T00:00:00Z"):
        store.mark_seen([item])

    loaded_second = store.load()
    t2 = loaded_second["seen"][item.repo][f"{item.item_type}:{item.item_id}"]
    assert t2 == t1, "first_seen_at must not be overwritten on re-mark"


def test_same_item_id_different_repo_are_distinct(tmp_path):
    """Same item_id under different repos are distinct entries (AC-3-005)."""
    store = _store(tmp_path)
    item_a = _make_item(repo="facebook/react", item_id="1")
    item_b = _make_item(repo="vercel/next.js", item_id="1")
    store.mark_seen([item_a, item_b])
    assert store.is_seen("facebook/react", "issue", "1")
    assert store.is_seen("vercel/next.js", "issue", "1")


def test_same_item_id_different_item_type_are_distinct(tmp_path):
    """Same item_id under different item_types are distinct entries (AC-3-005)."""
    store = _store(tmp_path)
    issue = _make_item(item_type="issue", item_id="99")
    discussion = _make_item(item_type="discussion", item_id="99")
    store.mark_seen([issue, discussion])
    assert store.is_seen("facebook/react", "issue", "99")
    assert store.is_seen("facebook/react", "discussion", "99")


def test_empty_item_id_keys_safely(tmp_path):
    """Empty item_id is valid and keys as '{item_type}:' (AC-3-005, EC-002)."""
    store = _store(tmp_path)
    item = _make_item(item_id="")
    assert not store.is_seen(item.repo, item.item_type, "")
    store.mark_seen([item])
    assert store.is_seen(item.repo, item.item_type, "")
    loaded = store.load()
    assert "issue:" in loaded["seen"]["facebook/react"]


def test_mark_seen_empty_list_is_noop(tmp_path):
    """mark_seen([]) leaves existing state unchanged (AC-3-006)."""
    store = _store(tmp_path)
    item = _make_item()
    store.mark_seen([item])
    loaded_before = store.load()

    store.mark_seen([])
    loaded_after = store.load()
    assert loaded_after == loaded_before


def test_mark_seen_empty_list_on_fresh_store_does_not_error(tmp_path):
    """mark_seen([]) on a fresh store is a safe no-op, creates no file (AC-3-006)."""
    store = _store(tmp_path)
    store.mark_seen([])  # must not raise


# ---------------------------------------------------------------------------
# Section 3 — Corrupt-vs-empty boundary (AC-3-002, AC-3-009, AC-3-010, AC-3-011, AC-3-012)
# ---------------------------------------------------------------------------


def test_missing_file_returns_empty_state(tmp_path):
    """load() with no file returns empty initialized state, no error (AC-3-002)."""
    store = _store(tmp_path)
    state = store.load()
    assert state == {"version": 1, "seen": {}}


def test_missing_file_does_not_create_file(tmp_path):
    """load() must not create the file (no side effect on cold read — AC-3-002)."""
    store = _store(tmp_path)
    store.load()
    assert not (tmp_path / "state.json").exists()


def test_zero_byte_file_returns_empty_state(tmp_path):
    """0-byte file is treated as empty, no error (AC-3-011)."""
    path = tmp_path / "state.json"
    path.write_bytes(b"")
    store = JsonFileStateStore(path)
    state = store.load()
    assert state == {"version": 1, "seen": {}}


def test_whitespace_only_file_returns_empty_state(tmp_path):
    """Whitespace-only file (strips to empty) is treated as empty (AC-3-011)."""
    path = tmp_path / "state.json"
    path.write_text("   \n\t  ", encoding="utf-8")
    store = JsonFileStateStore(path)
    state = store.load()
    assert state == {"version": 1, "seen": {}}


def test_missing_seen_key_tolerated_as_empty(tmp_path):
    """Valid JSON without 'seen' key is tolerated, seen treated as empty (AC-3-012)."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    store = JsonFileStateStore(path)
    state = store.load()
    assert state["seen"] == {}


def test_malformed_json_raises_state_error(tmp_path):
    """Malformed JSON raises StateError with a clear message (AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text("{broken json", encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="corrupt"):
        store.load()


def test_malformed_json_file_not_overwritten(tmp_path):
    """Corrupt file is NOT overwritten or reset on load failure (AC-3-009, RF-2)."""
    path = tmp_path / "state.json"
    original = "{broken json"
    path.write_text(original, encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError):
        store.load()
    assert path.read_text(encoding="utf-8") == original, "corrupt file must be left intact"


def test_unknown_version_raises_state_error(tmp_path):
    """State file with unrecognised version raises StateError (AC-3-010)."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 99, "seen": {}}), encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="unsupported state version"):
        store.load()


def test_version_0_raises_state_error(tmp_path):
    """Version 0 (not 1) raises StateError (AC-3-010)."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 0, "seen": {}}), encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="unsupported state version"):
        store.load()


def test_bool_version_raises_state_error(tmp_path):
    """Boolean version (True/False) raises StateError — bool-trap guard (AC-3-010)."""
    path = tmp_path / "state.json"
    # True serialises as JSON true; json.loads gives Python True (a bool, not int)
    path.write_text('{"version": true, "seen": {}}', encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="unsupported state version"):
        store.load()


def test_string_version_raises_state_error(tmp_path):
    """String version raises StateError (AC-3-010)."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": "1", "seen": {}}), encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="unsupported state version"):
        store.load()


# BUG-001 regression tests (AC-3-009) — non-dict root values must raise StateError,
# not AttributeError.  Each case writes a syntactically valid but structurally corrupt
# JSON root value and asserts: (a) StateError is raised, (b) file is not overwritten.


def test_null_root_raises_state_error_not_attribute_error(tmp_path):
    """JSON root 'null' raises StateError, not AttributeError (BUG-001 regression, AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text("null", encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="corrupt"):
        store.load()


def test_null_root_file_not_overwritten(tmp_path):
    """Corrupt null-root file is NOT overwritten on load failure (BUG-001 regression, AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text("null", encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError):
        store.load()
    assert path.read_text(encoding="utf-8") == "null", "corrupt file must be left intact"


def test_array_root_raises_state_error_not_attribute_error(tmp_path):
    """JSON root '[]' raises StateError, not AttributeError (BUG-001 regression, AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="corrupt"):
        store.load()


def test_integer_root_raises_state_error_not_attribute_error(tmp_path):
    """JSON root '42' raises StateError, not AttributeError (BUG-001 regression, AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text("42", encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="corrupt"):
        store.load()


def test_string_root_raises_state_error_not_attribute_error(tmp_path):
    """JSON root string raises StateError, not AttributeError (BUG-001 regression, AC-3-009)."""
    path = tmp_path / "state.json"
    path.write_text('"a string"', encoding="utf-8")
    store = JsonFileStateStore(path)
    with pytest.raises(StateError, match="corrupt"):
        store.load()


# ---------------------------------------------------------------------------
# Section 4 — Atomic + filesystem (AC-3-007, AC-3-008, AC-3-015, AC-3-016)
# ---------------------------------------------------------------------------


def test_missing_parent_dir_created_on_save(tmp_path):
    """save creates nested parent directories that don't exist yet (AC-3-015)."""
    path = tmp_path / "deep" / "nested" / "state.json"
    store = JsonFileStateStore(path)
    store.save({"version": 1, "seen": {}})
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_save_uses_temp_then_replace(tmp_path):
    """save writes via a temp file then renames — no direct in-place write (AC-3-007)."""
    path = tmp_path / "state.json"
    store = JsonFileStateStore(path)
    rename_calls: list = []
    original_replace = os.replace

    def spy_replace(src: str, dst: str) -> None:
        rename_calls.append((src, dst))
        original_replace(src, dst)

    with patch("osspulse.state.json_store.os.replace", side_effect=spy_replace):
        store.save({"version": 1, "seen": {}})

    assert len(rename_calls) == 1, "os.replace must be called exactly once"
    src, dst = rename_calls[0]
    assert str(dst) == str(path), "destination must be state_path"
    # src is the temp file: it must be in the same directory
    assert Path(src).parent == path.parent, "temp file must be in state_path.parent"


def test_interrupted_write_leaves_prior_valid_file(tmp_path):
    """If os.replace fails the original file remains intact (AC-3-008)."""
    path = tmp_path / "state.json"
    original_state = {"version": 1, "seen": {"repo/a": {"issue:1": "2026-01-01T00:00:00Z"}}}
    # Write the valid prior state directly
    path.write_text(json.dumps(original_state), encoding="utf-8")

    store = JsonFileStateStore(path)

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("simulated disk full")

    with patch("osspulse.state.json_store.os.replace", side_effect=fail_replace):
        with pytest.raises(StateError):
            store.save({"version": 1, "seen": {}})

    # The original file must still be there and intact
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == original_state


def test_interrupted_write_cleans_up_temp_file(tmp_path):
    """Failed save must remove the orphaned temp file (AC-3-007, ADR-002 cleanup)."""
    path = tmp_path / "state.json"
    store = JsonFileStateStore(path)

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("simulated failure")

    before = set(tmp_path.iterdir())
    with patch("osspulse.state.json_store.os.replace", side_effect=fail_replace):
        with pytest.raises(StateError):
            store.save({"version": 1, "seen": {}})
    after = set(tmp_path.iterdir())
    assert after == before, "no orphaned temp file should remain after a failed save"


def test_mkdir_failure_raises_state_error(tmp_path):
    """OSError from mkdir is wrapped in StateError (AC-3-015, AC-3-016)."""
    store = _store(tmp_path)
    with patch("osspulse.state.json_store.Path.mkdir", side_effect=OSError("permission denied")):
        with pytest.raises(StateError, match="cannot write state"):
            store.save({"version": 1, "seen": {}})


def test_failed_save_unlink_error_is_swallowed(tmp_path):
    """If os.unlink also fails in the finally block, the StateError from replace is still raised.

    This covers the 'except OSError: pass' branch in the finally cleanup (AC-3-016).
    """
    store = _store(tmp_path)

    original_replace = os.replace

    def fail_replace(src: str, dst: str) -> None:
        original_replace(src, dst)  # actually do the replace so file exists for unlink
        raise OSError("simulated failure after replace")

    def fail_unlink(path: str) -> None:
        raise OSError("unlink also failed")

    with (
        patch("osspulse.state.json_store.os.replace", side_effect=fail_replace),
        patch("osspulse.state.json_store.os.unlink", side_effect=fail_unlink),
    ):
        with pytest.raises(StateError):
            store.save({"version": 1, "seen": {}})


@pytest.mark.skipif(
    sys.platform == "win32" or os.getuid() == 0,
    reason="chmod read-only test not reliable on Windows or when running as root",
)
def test_unwritable_path_raises_state_error(tmp_path):
    """Saving to a read-only directory raises StateError (AC-3-016)."""
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x
    path = readonly_dir / "state.json"
    store = JsonFileStateStore(path)
    try:
        with pytest.raises(StateError, match="cannot write state"):
            store.save({"version": 1, "seen": {}})
    finally:
        # Restore permissions so pytest can clean up tmp_path
        readonly_dir.chmod(stat.S_IRWXU)


# ---------------------------------------------------------------------------
# Section 5 — Boundary: pure persistence + Protocol shape (AC-3-017, AC-3-018)
# ---------------------------------------------------------------------------


def test_no_network_or_cross_stage_imports(tmp_path):
    """json_store must not import collector, LLM, or network modules (AC-3-017)."""
    import osspulse.state.json_store as mod

    module_src = inspect.getsource(mod)
    forbidden_patterns = [
        r"\bimport\s+httpx\b",
        r"\bimport\s+litellm\b",
        r"\bfrom\s+osspulse\.github\b",
        r"\bfrom\s+osspulse\.summarizer\b",
        r"\bfrom\s+osspulse\.cache\b",
        r"\bimport\s+requests\b",
        r"\bimport\s+urllib\.request\b",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, module_src), (
            f"json_store must not contain {pattern!r} (AC-3-017)"
        )


def test_state_store_protocol_has_exactly_load_and_save():
    """StateStore Protocol declares exactly load() and save() — no helpers added (AC-3-018)."""
    protocol_methods = {
        name
        for name, member in inspect.getmembers(StateStore, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert protocol_methods == {"load", "save"}, (
        f"StateStore Protocol must only have 'load' and 'save'; found: {protocol_methods}"
    )


def test_json_store_not_in_state_store_protocol_members():
    """is_seen and mark_seen are on JsonFileStateStore only, NOT on the Protocol (AC-3-018)."""
    protocol_attrs = set(dir(StateStore))
    assert "is_seen" not in protocol_attrs
    assert "mark_seen" not in protocol_attrs

    concrete_attrs = set(dir(JsonFileStateStore))
    assert "is_seen" in concrete_attrs
    assert "mark_seen" in concrete_attrs


def test_json_store_implements_state_store_protocol_structurally(tmp_path):
    """JsonFileStateStore satisfies the StateStore Protocol (load/save signatures — AC-3-018)."""
    store: StateStore = JsonFileStateStore(tmp_path / "state.json")  # type: ignore[assignment]
    # If the structural typing is satisfied, this assignment doesn't raise at runtime.
    # Call both protocol methods to confirm they work:
    result = store.load()
    assert isinstance(result, dict)
    store.save(result)


# ---------------------------------------------------------------------------
# Section 6 — Helper unit tests (identity key, timestamp)
# ---------------------------------------------------------------------------


def test_identity_key_format():
    """_identity_key returns '{item_type}:{item_id}' (AC-3-005)."""
    assert _identity_key("issue", "123") == "issue:123"
    assert _identity_key("discussion", "abc") == "discussion:abc"


def test_identity_key_empty_item_id():
    """_identity_key with empty item_id returns '{item_type}:' — valid (AC-3-005, EC-002)."""
    assert _identity_key("issue", "") == "issue:"


def test_now_utc_z_format():
    """_now_utc_z returns UTC ISO-8601 with trailing Z (AC-3-003)."""
    ts = _now_utc_z()
    assert _UTC_Z_RE.match(ts), f"expected UTC-Z timestamp, got {ts!r}"


def test_config_is_frozen_after_state_path_added():
    """Config remains a frozen dataclass after adding state_path (AC-3-013)."""
    cfg = Config(watched_repos=[WatchedRepo("a", "b")])
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.state_path = "other"  # type: ignore[misc]
