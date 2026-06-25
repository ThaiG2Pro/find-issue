"""Tests for RedisSummaryCache adapter (AC-4-004, AC-4-005).

Rules:
- All test names carry their AC-ID (R3).
- No real Redis — inject a fake in-memory dict-backed client (stack.md, A-C8).
"""

import pytest

from osspulse.cache.redis_cache import RedisSummaryCache

# ---------------------------------------------------------------------------
# Fake in-memory Redis client (dict-backed; raises on demand)
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self, raise_on_get: bool = False, raise_on_set: bool = False) -> None:
        self._store: dict[str, bytes] = {}
        self._raise_on_get = raise_on_get
        self._raise_on_set = raise_on_set

    def get(self, key: str) -> bytes | None:
        if self._raise_on_get:
            raise ConnectionError("Redis unavailable")
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        if self._raise_on_set:
            raise ConnectionError("Redis unavailable")
        self._store[key] = value.encode("utf-8") if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_hit_returns_decoded_string_AC_4_004():
    """Cache hit returns the stored summary as a str (AC-4-004)."""
    fake = _FakeRedis()
    fake._store["k1"] = b"a summary"
    cache = RedisSummaryCache(fake)
    assert cache.get("k1") == "a summary"


def test_get_miss_returns_none_AC_4_004():
    """Cache miss (key absent) returns None (AC-4-004)."""
    cache = RedisSummaryCache(_FakeRedis())
    assert cache.get("missing") is None


def test_set_stores_value_AC_4_005():
    """set() stores the value so a subsequent get() returns it (AC-4-005)."""
    fake = _FakeRedis()
    cache = RedisSummaryCache(fake)
    cache.set("k2", "stored summary")
    assert cache.get("k2") == "stored summary"


def test_get_raises_on_transport_error_propagates():
    """Transport error from get() propagates (best-effort handled upstream, ADR-004)."""
    cache = RedisSummaryCache(_FakeRedis(raise_on_get=True))
    with pytest.raises(ConnectionError):
        cache.get("k")


def test_set_raises_on_transport_error_propagates():
    """Transport error from set() propagates (best-effort handled upstream, ADR-004)."""
    cache = RedisSummaryCache(_FakeRedis(raise_on_set=True))
    with pytest.raises(ConnectionError):
        cache.set("k", "v")
