"""Redis summary-cache adapter — implements ``osspulse.ports.SummaryCache`` (AC-4-004/005).

Faithful port: ``get``/``set`` may raise on transport error — best-effort swallowing
lives in the LiteLLMSummarizer adapter, not here (ADR-004).

Only imports: osspulse.ports (structural), redis, and stdlib.
No GitHub, LLM, or state-store imports allowed here (AC-4-021).
"""

import redis as redis_lib

from osspulse.models import RawItem  # noqa: F401 — not used here; here for boundary doc only


class RedisSummaryCache:
    """Concrete ``SummaryCache`` adapter backed by a ``redis.Redis`` client (ADR-004).

    Implements the ``osspulse.ports.SummaryCache`` Protocol structurally.
    The client is injected at construction so tests can pass a fake/in-memory client
    without hitting a real Redis server (stack.md, A-C8).
    """

    def __init__(self, client: redis_lib.Redis) -> None:  # type: ignore[type-arg]
        self._client = client

    def get(self, key: str) -> str | None:
        """Return the cached summary string, or ``None`` if missing (AC-4-004).

        Decodes bytes → str.  Raises on transport/connection error — the caller
        (``LiteLLMSummarizer._cache_get``) is responsible for best-effort handling (ADR-004).
        """
        value = self._client.get(key)
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def set(self, key: str, value: str) -> None:
        """Store the summary string under ``key`` with no TTL (A-A6, AC-4-005).

        Raises on transport/connection error — the caller handles as a no-op (ADR-004).
        """
        self._client.set(key, value)
