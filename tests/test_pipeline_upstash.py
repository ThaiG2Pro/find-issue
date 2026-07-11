"""Tests for pipeline._build_store — env-driven backend selection (ADR-001).

AC coverage: AC-V3-003-004, AC-V3-003-005.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osspulse.pipeline import _build_store
from osspulse.state.json_store import JsonFileStateStore

# ---------------------------------------------------------------------------
# Minimal Config stub — only the fields _build_store uses
# ---------------------------------------------------------------------------


class _FakeConfig:
    state_path: str = ".osspulse/state.json"


# ---------------------------------------------------------------------------
# Backend selection — AC-V3-003-004 and AC-V3-003-005
# ---------------------------------------------------------------------------


class TestBuildStoreSelection:
    def test_returns_json_store_when_no_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both env vars absent → JsonFileStateStore (AC-V3-003-005)."""
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

        store = _build_store(_FakeConfig())

        assert isinstance(store, JsonFileStateStore)

    def test_returns_json_store_when_only_url_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only URL set, token absent → JsonFileStateStore (AC-V3-003-005)."""
        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://db.upstash.io")
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

        store = _build_store(_FakeConfig())

        assert isinstance(store, JsonFileStateStore)

    def test_returns_json_store_when_only_token_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only token set, URL absent → JsonFileStateStore (AC-V3-003-005)."""
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
        monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "tok")

        store = _build_store(_FakeConfig())

        assert isinstance(store, JsonFileStateStore)

    def test_returns_json_store_when_url_is_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty-string URL counts as absent → JsonFileStateStore (AC-V3-003-005)."""
        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "")
        monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "tok")

        store = _build_store(_FakeConfig())

        assert isinstance(store, JsonFileStateStore)

    def test_returns_json_store_when_token_is_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty-string token counts as absent → JsonFileStateStore (AC-V3-003-005)."""
        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://db.upstash.io")
        monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "")

        store = _build_store(_FakeConfig())

        assert isinstance(store, JsonFileStateStore)

    def test_returns_upstash_store_when_both_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both env vars non-empty → UpstashStateStore (AC-V3-003-004)."""
        from osspulse.state.upstash_store import UpstashStateStore

        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://db.upstash.io")
        monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "tok")

        with patch("osspulse.state.upstash_store.Redis", return_value=MagicMock()):
            store = _build_store(_FakeConfig())

        assert isinstance(store, UpstashStateStore)

    def test_upstash_store_receives_url_and_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """UpstashStateStore is constructed with the env-var values (AC-V3-003-004)."""
        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://my-db.upstash.io")
        monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "secret-tok")

        with patch("osspulse.state.upstash_store.Redis") as mock_redis_cls:
            mock_redis_cls.return_value = MagicMock()
            _build_store(_FakeConfig())
            mock_redis_cls.assert_called_once_with(
                url="https://my-db.upstash.io", token="secret-tok"
            )

    def test_json_store_uses_config_state_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JsonFileStateStore is constructed with config.state_path (AC-V3-003-005)."""
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

        config = _FakeConfig()
        config.state_path = "/custom/state.json"
        store = _build_store(config)

        assert isinstance(store, JsonFileStateStore)
        assert store._path == Path("/custom/state.json")


# ---------------------------------------------------------------------------
# SeenTracker Protocol compliance — both backends expose is_seen + mark_seen
# ---------------------------------------------------------------------------


class TestSeenTrackerCompliance:
    def test_json_store_has_is_seen_and_mark_seen(self) -> None:
        """JsonFileStateStore satisfies SeenTracker Protocol (AC-V3-003-008)."""
        store = JsonFileStateStore(".osspulse/state.json")
        assert callable(getattr(store, "is_seen", None))
        assert callable(getattr(store, "mark_seen", None))

    def test_upstash_store_has_is_seen_and_mark_seen(self) -> None:
        """UpstashStateStore satisfies SeenTracker Protocol (AC-V3-003-008)."""
        from osspulse.state.upstash_store import UpstashStateStore

        with patch("osspulse.state.upstash_store.Redis", return_value=MagicMock()):
            store = UpstashStateStore(url="https://fake.upstash.io", token="tok")

        assert callable(getattr(store, "is_seen", None))
        assert callable(getattr(store, "mark_seen", None))

    def test_state_store_protocol_unchanged(self) -> None:
        """StateStore Protocol still only declares load/save — not is_seen/mark_seen.

        (AC-V3-003-008)
        """
        from osspulse.ports import StateStore

        # Protocol members are stored in __protocol_attrs__ in Python 3.13
        # or as annotations. Check the methods are load and save.
        assert hasattr(StateStore, "load")
        assert hasattr(StateStore, "save")
        # is_seen / mark_seen must NOT be on StateStore
        assert not hasattr(StateStore, "is_seen"), (
            "StateStore Protocol must NOT have is_seen — use SeenTracker (AC-V3-003-008)"
        )
        assert not hasattr(StateStore, "mark_seen"), (
            "StateStore Protocol must NOT have mark_seen — use SeenTracker (AC-V3-003-008)"
        )

    def test_seen_tracker_protocol_has_is_seen_and_mark_seen(self) -> None:
        """SeenTracker Protocol declares is_seen + mark_seen (ADR-003)."""
        from osspulse.ports import SeenTracker

        assert hasattr(SeenTracker, "is_seen")
        assert hasattr(SeenTracker, "mark_seen")
