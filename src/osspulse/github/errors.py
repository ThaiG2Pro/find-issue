"""Collector error hierarchy — token-safe by construction (ADR-004, AC-2-009).

Every message is composed from a status code + repo identifier + a *static* reason string
only. The GitHub token, the outbound request, and response headers are NEVER interpolated
into an error — that is the #1 risk for this component (T-I1 High, AC-2-009).
"""


class CollectorError(Exception):
    """Base for all Collector failures. Messages = status + repo + static reason only."""


class InvalidRepoError(CollectorError):
    """Repo arg failed the ``owner/name`` pattern; raised before any HTTP call (AC-2-014)."""


class AuthError(CollectorError):
    """401 or a non-rate-limit 403 — fail fast, affects all repos (AC-2-008)."""


class RateLimitError(CollectorError):
    """429 / ``403 + X-RateLimit-Remaining: 0`` / 5xx, surfaced only after retries are
    exhausted (AC-2-019/020/021/022)."""


class NetworkError(CollectorError):
    """Transport-level error that persisted past the retry budget (AC-2-023)."""
