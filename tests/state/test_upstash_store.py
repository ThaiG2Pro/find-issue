"""Tests for UpstashStateStore — Upstash Redis HTTP REST state adapter.

Upstash client is MOCKED throughout — no live network in tests (integration test policy).
AC coverage: AC-V3-003-001, AC-V3-003-002, AC-V3-003-003, AC-V3-003-006, AC-V3-003-007.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from osspulse.models import RawItem
from osspulse.state.errors import StateError
from osspulse.state.upstash_store import UpstashStateStore, _identity_key, _repo_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO = "vercel/next.js"
_KEY = _repo_key(_REPO)  # "osspulse:state:vercel/next.js"


def _make_item(item_type: str = "issue", item_id: str = "42", repo: str = _REPO) -> RawItem:
    return RawItem(
        repo=repo,
        item_type=item_type,
        item_id=item_id,
        title="Test item",
        body="body",
        url="https://github.com/vercel/next.js/issues/42",
        created_at="2026-07-11T00:00:00Z",
    )


def _make_store(mock_redis: MagicMock | None = None) -> tuple[UpstashStateStore, MagicMock]:
    """Return (store, mock_redis_instance) with the Redis client patched."""
    if mock_redis is None:
        mock_redis = MagicMock()
    with patch("osspulse.state.upstash_store.Redis", return_value=mock_redis):
        store = UpstashStateStore(url="https://fake.upstash.io", token="fake-token")
    return store, mock_redis


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_constructs_redis_client_with_url_and_token(self) -> None:
        """Redis client receives url= and token= at construction (AC-V3-003-006)."""
        with patch("osspulse.state.upstash_store.Redis") as mock_cls:
            mock_cls.return_value = MagicMock()
            UpstashStateStore(url="https://db.upstash.io", token="tok")
            mock_cls.assert_called_once_with(url="https://db.upstash.io", token="tok")


# ---------------------------------------------------------------------------
# is_seen — AC-V3-003-002
# ---------------------------------------------------------------------------


class TestIsSeen:
    def test_returns_false_when_hget_returns_none(self) -> None:
        """Item not present → HGET returns None → is_seen returns False (AC-V3-003-002)."""
        store, mock_redis = _make_store()
        mock_redis.hget.return_value = None

        result = store.is_seen(_REPO, "issue", "42")

        assert result is False
        mock_redis.hget.assert_called_once_with(_KEY, "issue:42")

    def test_returns_true_when_hget_returns_value(self) -> None:
        """Item present → HGET returns timestamp → is_seen returns True (AC-V3-003-002)."""
        store, mock_redis = _make_store()
        mock_redis.hget.return_value = "2026-07-11T00:00:00Z"

        result = store.is_seen(_REPO, "issue", "42")

        assert result is True

    def test_key_format_uses_repo_in_key(self) -> None:
        """Key is ``osspulse:state:{repo}`` (AC-V3-003-002)."""
        store, mock_redis = _make_store()
        mock_redis.hget.return_value = None

        store.is_seen("facebook/react", "issue", "1")

        mock_redis.hget.assert_called_once_with("osspulse:state:facebook/react", "issue:1")

    def test_field_format_is_item_type_colon_item_id(self) -> None:
        """Field is ``{item_type}:{item_id}`` (AC-V3-003-002)."""
        store, mock_redis = _make_store()
        mock_redis.hget.return_value = None

        store.is_seen(_REPO, "release", "v1.0")

        mock_redis.hget.assert_called_once_with(_KEY, "release:v1.0")

    def test_empty_item_id_is_valid(self) -> None:
        """Empty item_id yields field ``issue:`` — not rejected (EC-002, AC-V3-003-002)."""
        store, mock_redis = _make_store()
        mock_redis.hget.return_value = None

        store.is_seen(_REPO, "issue", "")

        mock_redis.hget.assert_called_once_with(_KEY, "issue:")

    def test_raises_state_error_on_upstash_failure(self) -> None:
        """HGET failure → StateError raised (fail loud — AC-V3-003-007)."""
        store, mock_redis = _make_store()
        mock_redis.hget.side_effect = RuntimeError("connection refused")

        with pytest.raises(StateError) as exc_info:
            store.is_seen(_REPO, "issue", "42")

        assert "is_seen failed" in str(exc_info.value)

    def test_state_error_message_does_not_contain_token(self) -> None:
        """StateError message never embeds the token (R-3, AC-V3-003-006)."""
        store, mock_redis = _make_store()
        mock_redis.hget.side_effect = RuntimeError("fake-token in error")

        with pytest.raises(StateError) as exc_info:
            store.is_seen(_REPO, "issue", "42")

        # The StateError message must compose from type name, not str(exc).
        assert "fake-token" not in str(exc_info.value)

    def test_state_error_message_does_not_contain_url(self) -> None:
        """StateError message never embeds the REST URL (R-3, AC-V3-003-006)."""
        store, mock_redis = _make_store()
        mock_redis.hget.side_effect = RuntimeError("https://fake.upstash.io in error")

        with pytest.raises(StateError) as exc_info:
            store.is_seen(_REPO, "issue", "42")

        assert "https://fake.upstash.io" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# mark_seen — AC-V3-003-001, AC-V3-003-003
# ---------------------------------------------------------------------------


class TestMarkSeen:
    def test_empty_list_is_noop_no_client_call(self) -> None:
        """Empty items list → no client call (AC-V3-003-001)."""
        store, mock_redis = _make_store()

        store.mark_seen([])

        mock_redis.hsetnx.assert_not_called()

    def test_single_item_calls_hsetnx(self) -> None:
        """Single item → one HSETNX call with correct key/field (AC-V3-003-002/003)."""
        store, mock_redis = _make_store()
        item = _make_item()

        store.mark_seen([item])

        mock_redis.hsetnx.assert_called_once()
        call_args = mock_redis.hsetnx.call_args
        assert call_args[0][0] == _KEY  # key
        assert call_args[0][1] == "issue:42"  # field

    def test_mark_seen_value_is_iso_z_timestamp(self) -> None:
        """Value stored is a UTC ISO-8601 ``…Z`` timestamp (AC-V3-003-003)."""
        store, mock_redis = _make_store()
        item = _make_item()

        store.mark_seen([item])

        value = mock_redis.hsetnx.call_args[0][2]
        assert value.endswith("Z")
        assert "T" in value

    def test_multiple_items_calls_hsetnx_per_item(self) -> None:
        """Multiple items → one HSETNX per item (AC-V3-003-001/003)."""
        store, mock_redis = _make_store()
        items = [
            _make_item("issue", "1"),
            _make_item("issue", "2"),
            _make_item("release", "v1.0"),
        ]

        store.mark_seen(items)

        assert mock_redis.hsetnx.call_count == 3

    def test_write_once_semantics_via_hsetnx(self) -> None:
        """HSETNX is used (not HSET) — server-side set-if-absent = write-once (AC-V3-003-003)."""
        store, mock_redis = _make_store()

        store.mark_seen([_make_item()])

        # Must call hsetnx, not hset
        mock_redis.hsetnx.assert_called_once()
        mock_redis.hset.assert_not_called()

    def test_raises_state_error_on_upstash_failure(self) -> None:
        """HSETNX failure → StateError raised (fail loud — AC-V3-003-007)."""
        store, mock_redis = _make_store()
        mock_redis.hsetnx.side_effect = ConnectionError("network timeout")

        with pytest.raises(StateError) as exc_info:
            store.mark_seen([_make_item()])

        assert "mark_seen failed" in str(exc_info.value)

    def test_state_error_message_no_token_in_mark_seen(self) -> None:
        """StateError from mark_seen does not embed the token (R-3, AC-V3-003-006)."""
        store, mock_redis = _make_store()
        mock_redis.hsetnx.side_effect = RuntimeError("fake-token leaked")

        with pytest.raises(StateError) as exc_info:
            store.mark_seen([_make_item()])

        assert "fake-token" not in str(exc_info.value)

    def test_items_across_different_repos_use_correct_keys(self) -> None:
        """Items from different repos use their respective hash keys (AC-V3-003-002)."""
        store, mock_redis = _make_store()
        items = [
            _make_item(repo="facebook/react"),
            _make_item(repo="vercel/next.js"),
        ]

        store.mark_seen(items)

        keys_used = {call[0][0] for call in mock_redis.hsetnx.call_args_list}
        assert "osspulse:state:facebook/react" in keys_used
        assert "osspulse:state:vercel/next.js" in keys_used

    def test_empty_item_id_marks_as_type_colon(self) -> None:
        """Empty item_id marks field ``issue:`` safely (EC-002, AC-V3-003-002)."""
        store, mock_redis = _make_store()
        item = _make_item(item_id="")

        store.mark_seen([item])

        field = mock_redis.hsetnx.call_args[0][1]
        assert field == "issue:"


# ---------------------------------------------------------------------------
# load / save — Protocol conformance
# ---------------------------------------------------------------------------


class TestLoadSave:
    def test_load_returns_versioned_seen_dict(self) -> None:
        """load() returns ``{"version": 1, "seen": {...}}`` (StateStore Protocol)."""
        store, mock_redis = _make_store()
        # scan returns (cursor=0, keys=[])
        mock_redis.scan.return_value = (0, [])

        result = store.load()

        assert result["version"] == 1
        assert "seen" in result
        assert result["seen"] == {}

    def test_load_populates_seen_from_hgetall(self) -> None:
        """load() fetches each repo hash via HGETALL (StateStore Protocol)."""
        store, mock_redis = _make_store()
        mock_redis.scan.return_value = (0, ["osspulse:state:vercel/next.js"])
        mock_redis.hgetall.return_value = {"issue:42": "2026-07-11T00:00:00Z"}

        result = store.load()

        assert result["seen"]["vercel/next.js"] == {"issue:42": "2026-07-11T00:00:00Z"}

    def test_load_raises_state_error_on_failure(self) -> None:
        """load() failure → StateError (fail loud — AC-V3-003-007)."""
        store, mock_redis = _make_store()
        mock_redis.scan.side_effect = OSError("upstash down")

        with pytest.raises(StateError) as exc_info:
            store.load()

        assert "load failed" in str(exc_info.value)

    def test_save_calls_hset_per_repo(self) -> None:
        """save() writes each repo hash via HSET (StateStore Protocol)."""
        store, mock_redis = _make_store()
        state = {
            "version": 1,
            "seen": {
                "vercel/next.js": {"issue:42": "2026-07-11T00:00:00Z"},
            },
        }

        store.save(state)

        mock_redis.hset.assert_called_once_with(
            "osspulse:state:vercel/next.js",
            values={"issue:42": "2026-07-11T00:00:00Z"},
        )

    def test_save_raises_state_error_on_failure(self) -> None:
        """save() failure → StateError (fail loud — AC-V3-003-007)."""
        store, mock_redis = _make_store()
        mock_redis.hset.side_effect = RuntimeError("write failed")
        state = {"version": 1, "seen": {"vercel/next.js": {"issue:1": "2026-01-01T00:00:00Z"}}}

        with pytest.raises(StateError) as exc_info:
            store.save(state)

        assert "save failed" in str(exc_info.value)

    def test_save_empty_seen_no_hset_calls(self) -> None:
        """save() with empty seen dict makes no HSET calls."""
        store, mock_redis = _make_store()
        store.save({"version": 1, "seen": {}})
        mock_redis.hset.assert_not_called()


# ---------------------------------------------------------------------------
# Round-trip: is_seen + mark_seen (both helpers together — R-1 check)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_is_seen_false_before_mark_then_true_after(self) -> None:
        """is_seen=False before mark, then HSETNX records; simulate HGET returning value (R-1)."""
        store, mock_redis = _make_store()
        item = _make_item()
        field = _identity_key(item.item_type, item.item_id)

        # Before mark: HGET returns None
        mock_redis.hget.return_value = None
        assert store.is_seen(item.repo, item.item_type, item.item_id) is False

        # Mark the item
        store.mark_seen([item])
        mock_redis.hsetnx.assert_called_once_with(_KEY, field, mock_redis.hsetnx.call_args[0][2])

        # After mark: simulate HGET returning the stored value
        mock_redis.hget.return_value = "2026-07-11T00:00:00Z"
        assert store.is_seen(item.repo, item.item_type, item.item_id) is True

    def test_both_backends_satisfy_seen_tracker_protocol(self) -> None:
        """Both UpstashStateStore and JsonFileStateStore have is_seen + mark_seen (R-1)."""
        from osspulse.state.json_store import JsonFileStateStore

        store, _ = _make_store()

        # Both expose is_seen / mark_seen — no AttributeError
        assert callable(store.is_seen)
        assert callable(store.mark_seen)
        assert callable(JsonFileStateStore.__dict__["is_seen"])
        assert callable(JsonFileStateStore.__dict__["mark_seen"])

    def test_state_error_is_chained_from_original_exc(self) -> None:
        """StateError has __cause__ set to the original exception (ADR-004 chain)."""
        store, mock_redis = _make_store()
        original = RuntimeError("network error")
        mock_redis.hget.side_effect = original

        with pytest.raises(StateError) as exc_info:
            store.is_seen(_REPO, "issue", "1")

        assert exc_info.value.__cause__ is original
