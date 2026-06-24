"""GitHub Collector adapter (S2) — implements ``osspulse.ports.GitHubClient``.

Pure I/O: fetches newly-opened issues for one repo via the GitHub REST API and maps them to
``RawItem``s. It never touches the State Store (S3) nor the LLM (S4) — it depends only on
``osspulse.models`` + httpx (AC-2-015, BR-2-012).

Security invariants (do not break):
- The GitHub token is set on the httpx client headers at construction and is never stored
  elsewhere, logged, or interpolated into an error/return value (ADR-004, AC-2-009).
- TLS verification is always on; only GET is issued (AC-2-013).
- ``base_url`` comes only from config; ``repo`` fills the path only, never host/scheme
  (AC-2-025). ``repo`` is validated against the shared ``REPO_PATTERN`` before any request
  (AC-2-014).
"""

import logging
import random
import time
from datetime import UTC, datetime, timedelta
from enum import Enum, auto

import httpx

from osspulse.config import REPO_PATTERN
from osspulse.github.config import CollectorConfig
from osspulse.github.errors import (
    AuthError,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
)
from osspulse.models import RawItem

logger = logging.getLogger(__name__)

_API_VERSION = "2022-11-28"
_ACCEPT = "application/vnd.github+json"


class _Action(Enum):
    """Outcome of classifying one HTTP response (ADR-003)."""

    OK = auto()
    RETRY = auto()
    SKIP_REPO = auto()
    FAIL_FAST = auto()


class GitHubCollector:
    """httpx-based adapter that collects newly-opened issues for a single repo."""

    def __init__(
        self,
        token: str,
        config: CollectorConfig = CollectorConfig(),
        *,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ) -> None:
        """Build the collector.

        The token is applied to the httpx client's ``Authorization`` header at construction
        and is not retained on ``self`` (ADR-004). Tests inject ``client`` (with a
        ``MockTransport``) and ``sleep`` so retries never actually wait (ADR-005).
        """
        self._config = config
        self._sleep = sleep
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                base_url=config.base_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": _ACCEPT,
                    "X-GitHub-Api-Version": _API_VERSION,
                },
                verify=True,  # TLS never disabled (AC-2-013)
            )

    # -- helpers ---------------------------------------------------------------

    def _validate_repo(self, repo: str) -> None:
        """Reject anything that is not ``owner/name`` before any request (AC-2-014).

        Defense-in-depth against an SSRF-shaped path (T-T2): the shared ``REPO_PATTERN``
        permits ``.`` so a value like ``../x`` would otherwise pass and then be normalized by
        httpx into a different path. Reject any ``.`` / ``..`` path segment explicitly so the
        repo can only ever fill the intended ``owner/name`` slot (AC-2-025)."""
        if not REPO_PATTERN.match(repo):
            raise InvalidRepoError(f"invalid repo '{repo}': expected 'owner/name'")
        owner, name = repo.split("/", 1)
        if owner in (".", "..") or name in (".", ".."):
            raise InvalidRepoError(f"invalid repo '{repo}': path traversal not allowed")

    def _classify(self, response: httpx.Response) -> _Action:
        """Map an HTTP status to a behavior (ADR-003).

        The 403 branch keys ONLY on ``X-RateLimit-Remaining: 0`` → RETRY (secondary rate
        limit); every other 403 is a permanent auth failure → FAIL_FAST (AC-2-008 vs AC-2-020).
        """
        status = response.status_code
        if status == 200:
            return _Action.OK
        if status in (404, 410):
            return _Action.SKIP_REPO
        if status == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            return _Action.RETRY
        if status == 429 or 500 <= status < 600:
            return _Action.RETRY
        if status in (401, 403):
            return _Action.FAIL_FAST
        return _Action.FAIL_FAST

    def _backoff_seconds(self, response: httpx.Response | None, attempt: int) -> float:
        """Wait time for one retry: ``Retry-After`` if present, else exponential backoff with
        jitter — both capped by ``backoff_ceiling_seconds`` (ADR-002, AC-2-026)."""
        retry = self._config.retry
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    return min(float(retry_after), retry.backoff_ceiling_seconds)
                except ValueError:
                    pass  # non-numeric Retry-After → fall through to computed backoff
        computed = retry.backoff_base_seconds * (
            retry.backoff_multiplier**attempt
        ) + random.uniform(0, retry.jitter_seconds)
        return min(computed, retry.backoff_ceiling_seconds)

    def _request_with_retry(self, url: str, repo: str) -> httpx.Response:
        """The ONLY httpx caller. Bounded retry loop (no infinite loop, AC-2-022).

        Retries on the RETRY class (429 / 5xx / secondary rate limit) and on
        ``httpx.TransportError``; raises ``RateLimitError``/``NetworkError`` once the budget
        is exhausted. ``AuthError`` is raised immediately for FAIL_FAST. Error messages carry
        status + repo + a static reason only — never the token, request, or headers (ADR-004).
        """
        retry = self._config.retry
        for attempt in range(retry.max_retries + 1):
            response: httpx.Response | None = None
            transport_failed = False
            try:
                response = self._client.get(url)
            except httpx.TransportError:
                transport_failed = True

            if not transport_failed:
                assert response is not None
                action = self._classify(response)
                if action in (_Action.OK, _Action.SKIP_REPO):
                    return response
                if action is _Action.FAIL_FAST:
                    raise AuthError(
                        f"GitHub auth failed for '{repo}' (status {response.status_code})"
                    )
                # action is RETRY
                if attempt == retry.max_retries:
                    raise RateLimitError(
                        f"GitHub rate limit / server error for '{repo}' "
                        f"(status {response.status_code}); retries exhausted"
                    )
            else:
                if attempt == retry.max_retries:
                    raise NetworkError(
                        f"network error contacting GitHub for '{repo}'; retries exhausted"
                    )

            self._sleep(self._backoff_seconds(response, attempt))

        # Unreachable: the loop always returns or raises within the budget.
        raise NetworkError(f"unexpected retry exhaustion for '{repo}'")  # pragma: no cover

    @staticmethod
    def _next_link(link_header: str | None) -> str | None:
        """Parse the ``rel="next"`` absolute URL from a ``Link`` header (AC-2-007, BR-2-004).

        Missing or malformed → ``None`` (single-page / stop pagination)."""
        if not link_header:
            return None
        for part in link_header.split(","):
            segments = part.split(";")
            if len(segments) < 2:
                continue
            url_seg = segments[0].strip()
            if not (url_seg.startswith("<") and url_seg.endswith(">")):
                continue
            url = url_seg[1:-1]
            for param in segments[1:]:
                if param.strip() == 'rel="next"':
                    return url
        return None

    def _map_item(self, raw: dict, repo: str) -> RawItem | None:
        """Map a GitHub issue dict to ``RawItem``; guard every field (AC-2-010/012/016/017).

        Returns ``None`` (skip) when a mandatory field — ``number`` or ``created_at`` — is
        missing, rather than crashing (dirty-data tolerance, T-T1). ``created_at`` is passed
        through unchanged (never reformatted, BR-2-010)."""
        number = raw.get("number")
        created_at = raw.get("created_at")
        if number is None or created_at is None:
            return None
        return RawItem(
            repo=repo,
            item_type="issue",
            item_id=str(number),
            title=raw.get("title") or "",
            body=raw.get("body") or "",
            url=raw.get("html_url") or "",
            created_at=created_at,
        )

    # -- public API ------------------------------------------------------------

    def fetch_items(self, repo: str, lookback_days: int) -> list[RawItem]:
        """Fetch newly-opened issues for ``repo`` created within the last ``lookback_days``.

        Pure I/O. Paginates created-desc, stops early per-item on the cutoff (not page-level,
        AC-2-005), drops PRs (AC-2-018), caps at ``max_items_per_repo`` with an info
        truncation log (AC-2-006), and returns ``[]`` for a skipped repo (404/410, AC-2-011).
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        self._validate_repo(repo)
        cfg = self._config

        url: str | None = (
            f"{cfg.base_url}/repos/{repo}/issues"
            f"?state=all&sort=created&direction=desc&per_page={cfg.page_size}"
        )
        items: list[RawItem] = []

        while url and len(items) < cfg.max_items_per_repo:
            response = self._request_with_retry(url, repo)
            if self._classify(response) is _Action.SKIP_REPO:
                logger.warning("skipping repo '%s' (status %d)", repo, response.status_code)
                return []

            for raw in response.json():
                if "pull_request" in raw:
                    continue  # PRs are not collected in V1 (AC-2-018)
                created = raw.get("created_at")
                if created is None:
                    continue  # dirty guard — cannot apply cutoff without created_at
                if not isinstance(created, str):
                    continue  # guard against non-string type (AC-2-010)
                if _parse_created(created) < cutoff:
                    return items  # created-desc → everything after is older (AC-2-005)
                item = self._map_item(raw, repo)
                if item is not None:
                    items.append(item)
                if len(items) >= cfg.max_items_per_repo:
                    logger.info("truncated at %d for %s", cfg.max_items_per_repo, repo)
                    return items

            url = self._next_link(response.headers.get("Link"))

        return items


def _parse_created(value: str) -> datetime:
    """Parse a GitHub ``created_at`` ISO timestamp (``...Z``) to a tz-aware UTC datetime.

    Used only for the cutoff comparison — the stored ``RawItem.created_at`` keeps the raw
    string (BR-2-010)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
