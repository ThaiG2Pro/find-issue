"""Collector tunables — config-driven, no hardcoded literals in the fetch loop.

Every value the Collector reads at runtime lives here as a frozen dataclass field with a
locked default (BR-2-013/014). Defaults apply when omitted; explicit values override without
any code change (AC-2-024..027). The GitHub token is NOT stored here — it is set on the httpx
client at construction so it never appears in a config repr (ADR-004, AC-2-009).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetryPolicy:
    """Single retry-policy object driving ``_request_with_retry`` (ADR-002, AC-2-026).

    Tunable in one place — the fetch loop never inlines a retry count or backoff literal.
    """

    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    jitter_seconds: float = 0.5
    backoff_ceiling_seconds: float = 60.0


@dataclass(frozen=True)
class CollectorConfig:
    """Collector tunables injected via ``GitHubCollector.__init__`` (ADR-001).

    ``base_url`` is overridable for GitHub Enterprise but is only ever taken from config,
    never built from the ``repo`` argument or any response data (AC-2-025, BR-2-008).
    """

    max_items_per_repo: int = 100
    page_size: int = 100
    base_url: str = "https://api.github.com"
    retry: RetryPolicy = field(default_factory=RetryPolicy)
