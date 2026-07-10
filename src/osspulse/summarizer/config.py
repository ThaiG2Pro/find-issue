"""Summarizer tunables — all literals in one frozen dataclass (ADR-007, AC-4-019).

No secret/api_key field here (RF-4). The API key is held privately on the adapter
and passed directly to litellm.completion — it never appears in a config repr.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SummarizerConfig:
    """Tunables injected into ``LiteLLMSummarizer.__init__`` (ADR-001/007).

    ``model`` is the LiteLLM model string (e.g. ``"openai/gpt-4o-mini"``).
    ``request_timeout_seconds`` is passed to ``litellm.completion(timeout=...)``
    to bound a hung LLM call (RF-2).
    ``input_char_cap`` is the max characters of title+body sent to the LLM (AC-4-019/RF-3).
    ``max_sentences`` is the ≤N sentence cap enforced by ``normalize_summary`` (AC-4-015).
    ``max_summary_chars`` is a secondary clamp on the final summary string.
    """

    model: str
    request_timeout_seconds: float = 30.0
    input_char_cap: int = 8000
    max_sentences: int = 2
    max_summary_chars: int = 600
    # Throttle tunables (AC-V3-001-001, ADR-001)
    tokens_per_minute: int = 6000
    throttle_window_seconds: float = 60.0
    # Retry tunables (AC-V3-001-006, ADR-005)
    max_retries: int = 3
    retry_backoff_base_seconds: float = 1.0
