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
import time
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


# ---------------------------------------------------------------------------
# Token-aware sliding window (ADR-001/002, AC-V3-001-001..004)
# ---------------------------------------------------------------------------


class TokenWindow:
    """In-memory 60-second sliding window of per-call token counts (ADR-001).

    Tracks ``(timestamp, tokens)`` pairs.  ``sleep_if_needed()`` prunes expired
    entries, then loops sleeping until the budget has enough headroom (ADR-002).
    Uses injected ``clock`` and ``sleep`` callables for deterministic testing (ADR-003).
    """

    def __init__(
        self,
        tokens_per_minute: int,
        window_seconds: float,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._budget = tokens_per_minute
        self._window = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._entries: list[tuple[float, int]] = []  # (monotonic_ts, tokens)

    def record(self, tokens: int) -> None:
        """Record ``tokens`` consumed by the most recent completion (AC-V3-001-003)."""
        self._entries.append((self._clock(), tokens))

    def _prune(self) -> None:
        """Drop entries older than ``window_seconds`` from the current clock time."""
        cutoff = self._clock() - self._window
        self._entries = [(ts, tok) for ts, tok in self._entries if ts > cutoff]

    def sleep_if_needed(self) -> None:
        """Sleep until the window has enough headroom for the next call (ADR-002).

        Prunes first, then while recorded tokens ≥ budget, sleeps until the oldest
        entry would expire and re-checks.  Best-effort: a single item whose own tokens
        exceed the budget is never hard-blocked — this guards accumulated usage only.
        """
        self._prune()
        while self._entries and sum(tok for _, tok in self._entries) >= self._budget:
            oldest_ts = self._entries[0][0]
            wait = (oldest_ts + self._window) - self._clock()
            self._sleep(max(wait, 1e-3))  # sleep at least 1ms to avoid tight spin
            self._prune()


# ---------------------------------------------------------------------------
# LiteLLM adapter
# ---------------------------------------------------------------------------


class LiteLLMSummarizer:
    """LiteLLM-backed ``LLMClient`` adapter with cache-aside (ADR-001/002/003/004/005).

    Implements ``osspulse.ports.LLMClient`` structurally (no subclassing required).
    The ``completion`` callable is injected so tests pass a mock without hitting the
    network (stack.md, A-C8).  The API key is never stored in ``SummarizerConfig``
    (RF-4, ADR-007/008).
    ``sleep`` and ``clock`` are injected for deterministic throttle + retry tests (ADR-003).
    """

    def __init__(
        self,
        *,
        provider: str,
        api_key: str | None,
        cache: SummaryCache,
        config: SummarizerConfig,
        completion: Callable[..., Any] = litellm.completion,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self.__api_key = api_key  # private — never logged or repr'd (ADR-008)
        self._cache = cache
        self._config = config
        self._completion = completion
        self._sleep = sleep
        self._clock = clock
        # One TokenWindow per adapter instance = run/batch-scoped (AC-V3-001-002)
        self._window = TokenWindow(
            tokens_per_minute=config.tokens_per_minute,
            window_seconds=config.throttle_window_seconds,
            clock=clock,
            sleep=sleep,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, title: str, body: str) -> list[dict[str, str]]:
        """Build the two-message prompt.  Sends ONLY title+body (RF-1, ADR-008).

        Appends the exact Vietnamese instruction to the system message (ADR-004,
        AC-V3-001-005).  Static instruction — not item data — so RF-1 is unchanged.
        """
        system_content = (
            "Summarize in at most 2 sentences. Plain text only, no markdown."
            " Trả lời bằng tiếng Việt."
        )
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

    def _call_with_retry(self, item: RawItem, messages: list[dict[str, str]]) -> Any:
        """Call ``_completion`` and retry on 429 ``RateLimitError`` (ADR-005).

        Catches only ``litellm.exceptions.RateLimitError``.  All other exceptions
        propagate immediately (unchanged AC-4-009/010 behavior).

        Wait per attempt = ``max(Retry-After, backoff_base * 2**attempt)``.
        ``Retry-After`` is extracted defensively — any absence/parse failure falls back
        to pure exp-backoff (ADR-005, AC-V3-001-007).

        After ``max_retries`` exhaustion the ``RateLimitError`` is re-raised so the
        batch loop's existing ``except openai.APIError`` catches it (AC-V3-001-008,
        MODIFIED AC-4-010).  Log lines carry identity only — never key or prompt
        (AC-4-012).
        """
        cfg = self._config
        attempt = 0
        while True:
            try:
                return self._completion(
                    model=cfg.model,
                    messages=messages,
                    api_key=self.__api_key,
                    timeout=cfg.request_timeout_seconds,
                )
            except litellm.exceptions.RateLimitError as exc:
                if attempt >= cfg.max_retries:
                    # All retries exhausted — re-raise into skip-log-continue (AC-V3-001-008)
                    logger.warning(
                        "skip %s: RateLimitError after %d retries",
                        _identity(item),
                        cfg.max_retries,
                    )
                    raise

                # Defensive Retry-After extraction (ADR-005)
                retry_after: float | None = None
                try:
                    response = getattr(exc, "response", None)
                    headers = getattr(response, "headers", None)
                    if headers is not None:
                        raw = headers.get("Retry-After") or headers.get("retry-after")
                        if raw is not None:
                            parsed = float(raw)
                            retry_after = max(parsed, 0.0)
                except Exception:  # noqa: BLE001 — extraction must never crash
                    retry_after = None

                backoff = cfg.retry_backoff_base_seconds * (2**attempt)
                wait = max(retry_after, backoff) if retry_after is not None else backoff

                logger.warning(
                    "retry %d/%d for %s: RateLimitError, waiting %.1fs",
                    attempt + 1,
                    cfg.max_retries,
                    _identity(item),
                    wait,
                )
                self._sleep(wait)
                attempt += 1

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

        Throttle + token recording happen ONLY on the real-completion path — after the
        cache-hit return and the _SkipItem guard — so cache hits/skips never count
        toward the window (AC-V3-001-004).
        """
        cfg = self._config
        title, body = prepare_input(item.title, item.body, cfg.input_char_cap)

        # AC-4-018: fully-empty → skip without LLM call (no window touch — AC-V3-001-004)
        if not title and not body:
            raise _SkipItem(_identity(item))

        h = content_hash(title, body)
        key = cache_key(item, h)

        # AC-4-004: cache hit → return immediately, no LLM call (no window touch — AC-V3-001-004)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        # AC-V3-001-001: throttle check — sleep if window budget is exhausted
        self._window.sleep_if_needed()

        # AC-4-005 / AC-V3-001-006..008: cache miss → call with retry-then-skip on 429
        messages = self._build_messages(title, body)
        response = self._call_with_retry(item, messages)
        raw_text: str = response.choices[0].message.content or ""

        # AC-V3-001-003: record tokens — None/missing usage ⇒ 0, never crash
        usage = getattr(response, "usage", None)
        total_tokens: int = (getattr(usage, "total_tokens", None) or 0) if usage is not None else 0
        self._window.record(total_tokens)

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
                # AC-4-009/010: timeout / 4xx / 5xx / 429 (after retries exhausted) —
                # identity + error class only.
                # litellm exceptions (Timeout, RateLimitError, etc.) inherit from
                # openai.APIError (their actual common base), not litellm.exceptions.APIError.
                logger.warning("skip %s: LLM error %s", _identity(item), type(exc).__name__)
        return out
