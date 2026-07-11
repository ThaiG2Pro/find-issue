"""Upstash Redis state store adapter — persists seen-items over HTTP REST (AC-V3-003-001..008).

Implements the ``osspulse.ports.StateStore`` Protocol (``load``/``save``) PLUS the
``is_seen``/``mark_seen`` helpers the pipeline actually calls (ADR-002, R-1).

Key layout (per-repo hash):
    key   = ``osspulse:state:{repo}``          e.g. ``osspulse:state:vercel/next.js``
    field = ``{item_type}:{item_id}``          e.g. ``issue:42``
    value = ``first_seen_at`` UTC ISO-8601 Z   e.g. ``2026-07-11T13:00:00Z``

Only imports: osspulse.models, osspulse.state.errors, and stdlib + upstash_redis.
No GitHub, LLM, cache, or other cross-module imports (mirrors json_store import discipline).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from upstash_redis import Redis

from osspulse.state.errors import StateError

if TYPE_CHECKING:
    from osspulse.models import RawItem

# Redis key prefix for all state hashes (AC-V3-003-002).
_KEY_PREFIX = "osspulse:state:"

# Version field embedded in the load()-returned dict for Protocol conformance.
_STATE_VERSION = 1


def _identity_key(item_type: str, item_id: str) -> str:
    """Compound hash field ``{item_type}:{item_id}`` (mirrors json_store, AC-V3-003-002).

    Empty ``item_id`` yields e.g. ``"issue:"`` — valid, not rejected (EC-002).
    """
    return f"{item_type}:{item_id}"


def _now_utc_z() -> str:
    """Current UTC time as ISO-8601 with trailing ``Z`` (mirrors json_store format)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_key(repo: str) -> str:
    """Full Redis hash key for *repo* (AC-V3-003-002)."""
    return f"{_KEY_PREFIX}{repo}"


class UpstashStateStore:
    """Concrete ``StateStore`` adapter backed by Upstash Redis over HTTP REST (ADR-002).

    Implements the ``osspulse.ports.StateStore`` Protocol structurally (``load``/``save``)
    and the ``is_seen``/``mark_seen`` helpers the pipeline calls on the concrete adapter.

    Fail-loud semantics (ADR-004, AC-V3-003-007):
    - Any runtime Upstash error raises ``StateError`` (chained).
    - Messages are composed from ``type(exc).__name__`` / status only — NEVER ``str(exc)``
      (which may embed the tokened REST URL) and NEVER the url/token values (R-3, AC-006).
    - Fallback to ``JsonFileStateStore`` is a construction-time-on-env-absence choice only,
      never a runtime catch inside this adapter.
    """

    def __init__(self, url: str, token: str) -> None:
        """Construct the Upstash client.

        ``url`` and ``token`` come from env vars (never logged or embedded in errors).
        """
        self._client = Redis(url=url, token=token)

    # ------------------------------------------------------------------
    # StateStore Protocol methods (AC-V3-003-008 / scope constraint 5)
    # load/save are implemented for Protocol conformance but are NOT on
    # the pipeline's hot path — _partition_new / _collect_all never call them.
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Return a snapshot of all state keys as the ``{"version":1,"seen":{...}}`` dict.

        Scans for ``osspulse:state:*`` keys and fetches each repo hash.
        Any Upstash error → ``StateError`` (fail loud, ADR-004).
        """
        try:
            # Collect all repo keys in the osspulse namespace.
            # upstash-redis sync scan returns (cursor, keys).
            cursor = 0
            repo_keys: list[str] = []
            while True:
                cursor, batch = self._client.scan(cursor, match=f"{_KEY_PREFIX}*", count=100)
                repo_keys.extend(batch)
                if cursor == 0:
                    break

            seen: dict[str, dict[str, str]] = {}
            for full_key in repo_keys:
                repo = full_key.removeprefix(_KEY_PREFIX)
                fields: dict[str, str] = self._client.hgetall(full_key) or {}
                if fields:
                    seen[repo] = fields
            return {"version": _STATE_VERSION, "seen": seen}
        except StateError:
            raise  # already wrapped — don't double-wrap
        except Exception as exc:  # noqa: BLE001 — fail loud for any Upstash error (ADR-004)
            raise StateError(f"Upstash state load failed: {type(exc).__name__}") from exc

    def save(self, state: dict) -> None:
        """Write the ``state["seen"]`` dict back into Upstash hashes (best-effort Protocol).

        For each ``{repo: {field: first_seen_at}}`` entry, writes using ``HSET`` (overwrite).
        ``load``/``save`` are NOT on the pipeline hot path; ``mark_seen`` (HSETNX) is the
        write-path used by the pipeline (ADR-002).
        Any Upstash error → ``StateError`` (fail loud, ADR-004).
        """
        seen: dict[str, dict[str, str]] = state.get("seen", {})
        try:
            for repo, fields in seen.items():
                if fields:
                    key = _repo_key(repo)
                    self._client.hset(key, values=fields)
        except StateError:
            raise
        except Exception as exc:  # noqa: BLE001 — fail loud for any Upstash error (ADR-004)
            raise StateError(f"Upstash state save failed: {type(exc).__name__}") from exc

    # ------------------------------------------------------------------
    # Adapter-only helpers — the real contract the pipeline depends on
    # (ADR-002, R-1; NOT part of StateStore Protocol; NOT added to StateStore)
    # ------------------------------------------------------------------

    def is_seen(self, repo: str, item_type: str, item_id: str) -> bool:
        """Return True if the item is already recorded in Upstash (AC-V3-003-002).

        Issues a single ``HGET osspulse:state:{repo} {item_type}:{item_id}``.
        Any Upstash error → ``StateError`` (fail loud, ADR-004, AC-V3-003-007).
        """
        key = _repo_key(repo)
        field = _identity_key(item_type, item_id)
        try:
            result = self._client.hget(key, field)
            return result is not None
        except StateError:
            raise
        except Exception as exc:  # noqa: BLE001 — fail loud for any Upstash error (ADR-004)
            raise StateError(f"Upstash is_seen failed: {type(exc).__name__}") from exc

    def mark_seen(self, items: list[RawItem]) -> None:
        """Record not-yet-seen items using HSETNX (set-if-absent — write-once, AC-V3-003-003).

        - Empty list is a safe no-op; no client call is made (AC-V3-003-001).
        - ``first_seen_at`` is preserved on re-mark: HSETNX is a no-op if the field exists,
          so the original timestamp survives without a read-modify-write race (AC-V3-003-003).
        - Empty ``item_id`` is valid: fields safely as ``"{item_type}:"`` (EC-002).
        - Any Upstash error → ``StateError`` (fail loud, ADR-004, AC-V3-003-007).
        """
        if not items:
            # AC-V3-003-001: empty list is a true no-op — identical to json_store.
            return

        now = _now_utc_z()
        try:
            for item in items:
                key = _repo_key(item.repo)
                field = _identity_key(item.item_type, item.item_id)
                # HSETNX: set field only if absent → write-once first_seen_at (AC-V3-003-003).
                self._client.hsetnx(key, field, now)
        except StateError:
            raise
        except Exception as exc:  # noqa: BLE001 — fail loud for any Upstash error (ADR-004)
            raise StateError(f"Upstash mark_seen failed: {type(exc).__name__}") from exc
