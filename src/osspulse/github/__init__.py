"""GitHub Collector package — S2 adapter + its config types."""

from osspulse.github.client import GitHubCollector
from osspulse.github.config import CollectorConfig, RetryPolicy
from osspulse.github.errors import (
    AuthError,
    CollectorError,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
)

__all__ = [
    "GitHubCollector",
    "CollectorConfig",
    "RetryPolicy",
    "CollectorError",
    "InvalidRepoError",
    "AuthError",
    "RateLimitError",
    "NetworkError",
]
