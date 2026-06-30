"""LiteLLM summarizer adapter — implements ``osspulse.ports.LLMClient`` (AC-4-001..022).

Cache-aside, graceful degradation, best-effort cache, and batch skip-log-continue all
live here.  Only imports: osspulse.models, osspulse.ports (structural), osspulse.summarizer.*,
litellm, and stdlib.  No GitHub or state-store imports (AC-4-021).

Security invariants (do not break):
- The LLM API key is held in ``self.__api_key`` and passed directly to
  ``litellm.completion(api_key=...)``.  It is NEVER logged, repr'd, or interpolated
  into an error message (ADR-008, AC-4-012/022, RF-4).
- Only ``title`` and ``body`` of each item are sent to the LLM provider (RF-1).
"""

import logging
from collections.abc import Callable
from typing import Any

import litellm
import litellm.exceptions
import openai

from osspulse.models import RawItem, SummarizedItem
from osspulse.ports import SummaryCache
from osspulse.summarizer.config import SummarizerConfig
from osspulse.summarizer.errors import SummarizationFailed
from osspulse.summarizer.keys import cache_key, content_hash
from osspulse.summarizer.normalize import normalize_summary, prepare_input

logger = logging.getLogger(__name__)


class _SkipItem(Exception):
    """Internal sentinel: fully-empty item — skip without LLM call (AC-4-018)."""


def _identity(item: RawItem) -> str:
    """Return a log-safe identity string (repo/type/id only — no body/key)."""
    return f"{item.repo}/{item.item_type}/{item.item_id}"


class LiteLLMSummarizer:
    """LiteLLM-backed ``LLMClient`` adapter with cache-aside (ADR-001/002/003/004/005).

    Implements ``osspulse.ports.LLMClient`` structurally (no subclassing required).
    The ``completion`` callable is injected so tests pass a mock without hitting the
    network (stack.md, A-C8).  The API key is never stored in ``SummarizerConfig``
    (RF-4, ADR-007/008).
    """

    def __init__(
        self,
        *,
        provider: str,
        api_key: str | None,
        cache: SummaryCache,
        config: SummarizerConfig,
        completion: Callable[..., Any] = litellm.completion,
    ) -> None:
        self._provider = provider
        self.__api_key = api_key  # private — never logged or repr'd (ADR-008)
        self._cache = cache
        self._config = config
        self._completion = completion

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, title: str, body: str) -> list[dict[str, str]]:
        """Build the two-message prompt.  Sends ONLY title+body (RF-1, ADR-008)."""
        system_content = "Summarize in at most 2 sentences. Plain text only, no markdown."
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Title: {title}\n\nBody: {body}"},
        ]

    def _cache_get(self, key: str) -> str | None:
        """Best-effort cache read: Redis error → treated as miss (ADR-004, AC-4-013)."""
        try:
            return self._cache.get(key)
        except Exception as exc:  # noqa: BLE001 — intentional broad catch for I/O degradation
            logger.warning("cache get failed for key %r: %s", key, type(exc).__name__)
            return None

    def _cache_set(self, key: str, value: str) -> None:
        """Best-effort cache write: Redis error → no-op (ADR-004, AC-4-014)."""
        try:
            self._cache.set(key, value)
        except Exception as exc:  # noqa: BLE001 — intentional broad catch for I/O degradation
            logger.warning("cache set failed for key %r: %s", key, type(exc).__name__)

    # ------------------------------------------------------------------
    # LLMClient Protocol method (AC-4-003 — signature must stay unchanged)
    # ------------------------------------------------------------------

    def summarize(self, item: RawItem) -> str:
        """Return a 1–2 sentence plain-text summary for ``item`` (AC-4-001, Flow 1).

        Cache-aside: hit → return cached; miss → call LLM once → store → return.
        Raises ``_SkipItem`` for fully-empty items (AC-4-018); the batch loop catches it.
        Raises ``SummarizationFailed`` if the LLM returns empty output (EC-012).
        Raises ``litellm.exceptions.APIError`` (subclasses) on LLM errors; the batch
        loop catches those too (AC-4-009/010).
        """
        cfg = self._config
        title, body = prepare_input(item.title, item.body, cfg.input_char_cap)

        # AC-4-018: fully-empty → skip without LLM call
        if not title and not body:
            raise _SkipItem(_identity(item))

        h = content_hash(title, body)
        key = cache_key(item, h)

        # AC-4-004: cache hit → return immediately, no LLM call
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        # AC-4-005: cache miss → exactly one LLM call
        response = self._completion(
            model=self._config.model,
            messages=self._build_messages(title, body),
            api_key=self.__api_key,
            timeout=cfg.request_timeout_seconds,
        )
        raw_text: str = response.choices[0].message.content or ""

        # AC-4-015/016, EC-012: normalize; raises SummarizationFailed if empty
        summary = normalize_summary(raw_text, cfg.max_sentences, cfg.max_summary_chars)

        # AC-4-014: best-effort store; failure is a no-op
        self._cache_set(key, summary)
        return summary

    # ------------------------------------------------------------------
    # Adapter-only batch helper (NOT on the Protocol — ADR-005, AC-4-011)
    # ------------------------------------------------------------------

    def summarize_items(self, items: list[RawItem]) -> list[SummarizedItem]:
        """Summarize a batch; return only the survivors (AC-4-011, Flow 2).

        Per-item failures degrade gracefully (AC-4-009/010/018); the batch never aborts.
        Log records carry item identity only — NEVER the API key or prompt (AC-4-012).
        """
        out: list[SummarizedItem] = []
        for item in items:
            try:
                out.append(SummarizedItem(raw=item, summary=self.summarize(item)))
            except _SkipItem:
                # AC-4-018: fully-empty item — silent skip (no noise in logs)
                logger.debug("skip empty item %s", _identity(item))
            except SummarizationFailed as exc:
                # EC-012: LLM returned empty output
                logger.warning("skip %s: %s", _identity(item), exc)
            except openai.APIError as exc:
                # AC-4-009/010: timeout / 4xx / 5xx / 429 — identity + error class only.
                # litellm exceptions (Timeout, RateLimitError, etc.) inherit from
                # openai.APIError (their actual common base), not litellm.exceptions.APIError.
                logger.warning("skip %s: LLM error %s", _identity(item), type(exc).__name__)
        return out
