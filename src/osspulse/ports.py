from typing import Protocol

from osspulse.models import RawItem, SummarizedItem


class GitHubClient(Protocol):
    def fetch_items(self, repo: str, lookback_days: int) -> list[RawItem]: ...


class LLMClient(Protocol):
    def summarize(self, item: RawItem) -> str: ...


class StateStore(Protocol):
    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...


class SeenTracker(Protocol):
    """Port for the is_seen/mark_seen helpers the pipeline actually calls (ADR-003, AC-V3-003-008).

    This is the REAL contract the pipeline depends on — wider than ``StateStore`` (load/save),
    which the pipeline never calls directly.  Both ``JsonFileStateStore`` and
    ``UpstashStateStore`` satisfy this Protocol structurally (no subclassing required).

    ``StateStore`` is NOT changed (scope constraint 5 / AC-V3-003-008).  This Protocol is
    ADDED alongside it to let ``_partition_new``/``_collect_all`` accept either backend.
    """

    def is_seen(self, repo: str, item_type: str, item_id: str) -> bool:
        """Return True if the item is already recorded in the state store."""
        ...

    def mark_seen(self, items: list[RawItem]) -> None:
        """Record *items* as seen; empty list is a safe no-op."""
        ...


class SummaryCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


class Delivery(Protocol):
    def deliver(self, content: str) -> None: ...  # AC-6-001, D-1


class DigestRenderer(Protocol):
    def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str: ...


class ConditionalCache(Protocol):
    """Port for HTTP ETag conditional-request caching (AC-V2-007-001).

    Keys are ``"{repo}:{endpoint}"`` (e.g. ``"owner/name:issues"``).
    Values are opaque validator strings (strong ``"abc"`` or weak ``W/"abc"``).

    ``get``/``set`` operate on an in-memory dict; the durable write only
    happens when the pipeline explicitly calls ``commit()`` (ADR-002).
    The pipeline MUST call ``commit()`` exactly once, AFTER ``mark_seen`` (ADR-004).
    """

    def get(self, key: str) -> str | None:
        """Return the cached validator for *key*, or ``None`` on a miss (AC-V2-007-001)."""
        ...

    def set(self, key: str, validator: str) -> None:
        """Update *key* → *validator* in the in-memory cache (AC-V2-007-005)."""
        ...

    def commit(self) -> None:
        """Flush the in-memory cache to durable storage, best-effort (AC-V2-007-003)."""
        ...


class _NullConditionalCache:
    """No-op ``ConditionalCache`` used when caching is disabled or unavailable (ADR-002).

    ``get`` → ``None`` (always a cache miss), ``set``/``commit`` → no-op.
    Satisfies the ``ConditionalCache`` Protocol structurally so callers need
    no ``if cache is not None`` guards (AC-V2-007-007, BR-V2-007-007).

    Defined here (in ``ports.py``) so the collector and other callers can import from
    the port layer only — never from a concrete adapter (BR-V2-007-007, AC-2-015).
    """

    def get(self, key: str) -> str | None:  # noqa: ARG002
        return None

    def set(self, key: str, validator: str) -> None:  # noqa: ARG002,A003
        pass

    def commit(self) -> None:
        pass
