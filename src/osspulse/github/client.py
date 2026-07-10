"""GitHub Collector adapter (S2) — implements ``osspulse.ports.GitHubClient``.

Pure I/O: fetches newly-opened issues, releases, and discussions for one repo via the GitHub
API (REST for issues/releases, GraphQL POST for discussions) and maps them to ``RawItem``s.
It never touches the State Store (S3) nor the LLM (S4) — it depends only on
``osspulse.models`` + httpx (AC-2-015, BR-2-012).

Security invariants (do not break):
- The GitHub token is set on the httpx client headers at construction and is never stored
  elsewhere, logged, or interpolated into an error/return value (ADR-004, AC-2-009).
- TLS verification is always on; REST callers use GET, the GraphQL path uses one fixed POST
  to ``{base_url}/graphql`` with a non-mutating query (ADR-002, AC-V2-006-016).
- ``base_url`` comes only from config; ``repo`` fills the path/variables only, never
  host/scheme (AC-2-025). ``repo`` is validated against the shared ``REPO_PATTERN`` before
  any request (AC-2-014).
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
    CollectorError,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
)
from osspulse.models import RawItem
from osspulse.ports import ConditionalCache, _NullConditionalCache

logger = logging.getLogger(__name__)

_API_VERSION = "2022-11-28"
_ACCEPT = "application/vnd.github+json"


class _Action(Enum):
    """Outcome of classifying one HTTP response (ADR-003)."""

    OK = auto()
    RETRY = auto()
    SKIP_REPO = auto()
    FAIL_FAST = auto()


class _GraphQLOutcome(Enum):
    """Sentinel outcomes for GraphQL 200-payload classification (ADR-003, AC-V2-006-003/014).

    SKIP_REPO — repo not found or Discussions disabled (null connection shape).
    Returned as a sentinel; the caller WARNs + returns [].
    The "map" outcome is NOT a sentinel — ``_classify_graphql`` returns the connection
    dict directly so the cursor loop receives nodes + pageInfo without a second lookup.
    """

    SKIP_REPO = auto()


# ---------------------------------------------------------------------------
# GraphQL query constant (ADR-004, AC-V2-006-016)
# Fixed, non-mutating; only owner/name/first/after are variables — never built
# from untrusted input, never a mutation (BR-V2-006-006).
# ---------------------------------------------------------------------------

_DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: $first, after: $after,
                orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { number title body url createdAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""".strip()


class GitHubCollector:
    """httpx-based adapter that collects newly-opened issues for a single repo."""

    def __init__(
        self,
        token: str,
        config: CollectorConfig = CollectorConfig(),
        *,
        client: httpx.Client | None = None,
        sleep=time.sleep,
        conditional_cache: ConditionalCache | None = None,
    ) -> None:
        """Build the collector.

        The token is applied to the httpx client's ``Authorization`` header at construction
        and is not retained on ``self`` (ADR-004). Tests inject ``client`` (with a
        ``MockTransport``) and ``sleep`` so retries never actually wait (ADR-005).

        ``conditional_cache`` injects the ETag conditional-request cache (AC-V2-007-009).
        Defaults to a ``_NullConditionalCache`` so a collector built without one behaves
        exactly as today — a cache miss produces the same unconditional fetch as V1.
        The collector depends on the ``ConditionalCache`` PORT only; it never imports
        ``JsonFileETagStore`` or the State Store (BR-V2-007-007).
        """
        self._config = config
        self._sleep = sleep
        # AC-V2-007-009: default null cache → no-op, preserves today's behaviour exactly
        self._conditional_cache: ConditionalCache = (
            conditional_cache if conditional_cache is not None else _NullConditionalCache()
        )
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

        ``304 Not Modified`` → ``OK`` (AC-V2-007-016, ADR-003). The fetch method MUST branch
        on ``response.status_code == 304`` (not on ``_Action``) because both ``200`` and ``304``
        map to ``OK``; attempting to iterate a body-less ``304`` would be a bug.
        """
        status = response.status_code
        if status == 200:
            return _Action.OK
        if status == 304:
            # ADR-003: map to OK so _request_with_retry returns; caller branches on raw status
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

    def _request_with_retry(
        self,
        url: str,
        repo: str,
        *,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> httpx.Response:
        """The ONLY httpx caller. Bounded retry loop (no infinite loop, AC-2-022).

        ``json_body is None`` → ``self._client.get(url)`` (every REST caller, unchanged —
        GET-only invariant preserved for issues/releases). ``json_body is not None`` →
        ``self._client.post(url, json=json_body)`` (GraphQL path only — ADR-002).

        ``extra_headers`` — when present, merged into the GET request headers (AC-V2-007-013).
        Used to send ``If-None-Match`` on the first page of a REST endpoint. Only valid for
        GET requests (``json_body is None``); ignored on POST (GraphQL path always uses
        ``json_body``). The conditional header rides the SAME single retry/``_classify``/
        backoff path — no duplicated logic (BR-V2-007-011, ADR-003).

        The retry loop, ``_classify``, ``_backoff_seconds``, and error messages are
        shared verbatim for both verbs (BR-V2-006-010).

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
                if json_body is None:
                    response = self._client.get(url, headers=extra_headers or {})
                else:
                    response = self._client.post(url, json=json_body)
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

    def _map_release(self, raw: dict, repo: str) -> RawItem | None:
        """Map a GitHub release dict to ``RawItem``; guard every field (AC-V2-003-006..011).

        Returns ``None`` (skip) when BOTH ``tag_name`` and ``id`` are missing — cannot key
        the release (dirty-data tolerance). ``published_at`` is stored in ``created_at``
        unchanged (BR-V2-003-002 / AC-V2-003-010) — never reformatted.
        """
        tag_name = raw.get("tag_name")
        if not tag_name:
            # Only skip entirely when both tag_name and id are absent (AC-V2-003-011)
            if raw.get("id") is None:
                return None
            # Fall back to str(id) as item_id — ensures the release can still be keyed
            tag_name = str(raw["id"])
        name = raw.get("name")
        return RawItem(
            repo=repo,
            item_type="release",
            item_id=tag_name,  # AC-V2-003-006: tag_name as identity
            title=name if name else tag_name,  # AC-V2-003-007: fallback to tag_name
            body=raw.get("body") or "",  # AC-V2-003-008: null → ""
            url=raw.get("html_url") or "",  # AC-V2-003-009: null → ""
            created_at=raw.get("published_at") or "",  # AC-V2-003-010: raw ISO string
        )

    def _map_discussion(self, node: dict, repo: str) -> RawItem | None:
        """Map a GraphQL discussion node to ``RawItem``; guard every field (AC-V2-006-005..010).

        Returns ``None`` (skip) when ``number`` is missing — cannot key the discussion
        (dirty-data tolerance, AC-V2-006-010). ``item_id = str(number)`` renders as ``#42``.
        ``body`` is the markdown field (not ``bodyText``) — ADR-004. ``created_at`` is the
        raw ``createdAt`` ISO string, never reformatted.
        """
        number = node.get("number")
        if number is None:
            return None  # AC-V2-006-010: skip node without a number
        return RawItem(
            repo=repo,
            item_type="discussion",
            item_id=str(number),  # AC-V2-006-005
            title=node.get("title") or "",  # AC-V2-006-006: null → ""
            body=node.get("body") or "",  # AC-V2-006-007: markdown body, null → ""
            url=node.get("url") or "",  # AC-V2-006-008: null → ""
            created_at=node.get("createdAt") or "",  # AC-V2-006-009: raw ISO, never reformatted
        )

    def _classify_graphql(self, payload: dict, repo: str) -> _GraphQLOutcome | dict:
        """Classify a GraphQL 200 payload — shape-first ordered (ADR-003, RISK-003).

        The check ORDER is load-bearing (the active concern from _handoff.md):
        1. Null connection SHAPE → SKIP_REPO sentinel (disabled or not-found repo).
           Checked FIRST because a disabled repo carries BOTH a null connection AND an
           errors entry — the null-shape guard must fire before the errors-raise.
        2. Non-empty top-level ``errors`` (and null-shape did NOT fire) → raise.
           ``RATE_LIMITED`` error type → ``RateLimitError``; anything else → ``CollectorError``.
        3. Otherwise → return the ``discussions`` connection dict (nodes + pageInfo).

        Does NOT hardcode an ``errors[].type`` string to detect disabled Discussions —
        detection keys on the null connection SHAPE (BR-V2-006-007, handoff §2 warning).
        """
        data = payload.get("data") or {}
        repo_node = data.get("repository")

        # Step 1 — shape-first: null repository OR null discussions → skip repo (AC-V2-006-003)
        # This check MUST precede the errors-raise below (ADR-003 active concern).
        if repo_node is None or repo_node.get("discussions") is None:
            logger.warning(
                "skipping repo '%s': Discussions disabled or repo not found (null connection)",
                repo,
            )
            return _GraphQLOutcome.SKIP_REPO

        # Step 2 — non-empty top-level errors that are NOT a null-connection shape (AC-V2-006-014)
        errors = payload.get("errors")
        if errors:
            # Detect RATE_LIMITED to map → RateLimitError (pipeline partial-deliver arm)
            # Key on error type string ONLY for rate-limit routing — NOT for disabled detection.
            has_rate_limited = any(
                (e.get("type") or "").upper() == "RATE_LIMITED"
                for e in errors
                if isinstance(e, dict)
            )
            if has_rate_limited:
                raise RateLimitError(f"GraphQL RATE_LIMITED for '{repo}'; retries exhausted")
            raise CollectorError(f"GraphQL errors for '{repo}': {len(errors)} error(s) returned")

        # Step 3 — map: return the discussions connection (nodes + pageInfo)
        return repo_node["discussions"]  # type: ignore[return-value]

    # -- public API ------------------------------------------------------------

    def fetch_discussions(self, repo: str, lookback_days: int) -> list[RawItem]:
        """Fetch discussions created within the last ``lookback_days`` for ``repo``.

        Pure I/O. Issues a fixed non-mutating GraphQL POST to ``{base_url}/graphql``
        ordered ``CREATED_AT DESC``; cursor-paginates via ``pageInfo.hasNextPage``/
        ``endCursor``; early-stops per-item when ``createdAt < cutoff`` (ADR-001 — same
        field for ordering and inclusion, no skew); caps at ``max_items_per_repo`` with an
        info truncation log (AC-V2-006-013).

        GraphQL 200 payload classified (ADR-003): disabled/not-found → WARN + [];
        non-disabled top-level errors → raise (``RateLimitError`` for ``RATE_LIMITED``,
        else ``CollectorError``); else map nodes to ``RawItem``.

        Reuses the same authed httpx client, retry policy, and ``CollectorError`` hierarchy
        as ``fetch_items``/``fetch_releases``. Token never in the query body or any log/error.
        ``GitHubClient`` Protocol unchanged (AC-V2-006-018).
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        self._validate_repo(repo)
        cfg = self._config

        owner, name = repo.split("/", 1)
        url = f"{cfg.base_url}/graphql"
        items: list[RawItem] = []
        after: str | None = None

        while len(items) < cfg.max_items_per_repo:
            body = {
                "query": _DISCUSSIONS_QUERY,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "first": cfg.page_size,
                    "after": after,  # None on the first page
                },
            }
            # _request_with_retry handles transport-level 429/5xx/auth unchanged (ADR-002)
            response = self._request_with_retry(url, repo, json_body=body)

            payload = response.json()
            result = self._classify_graphql(payload, repo)

            if result is _GraphQLOutcome.SKIP_REPO:
                return []  # already logged in _classify_graphql (AC-V2-006-003)

            # result is the discussions connection dict (nodes + pageInfo)
            conn: dict = result  # type: ignore[assignment]

            for node in conn.get("nodes") or []:
                # ADR-001: per-item early-stop — inclusion and ordering both key on createdAt
                created_raw = node.get("createdAt")
                if isinstance(created_raw, str) and _parse_created(created_raw) < cutoff:
                    return items  # created-desc → everything after is older (AC-V2-006-012)

                item = self._map_discussion(node, repo)
                if item is not None:
                    items.append(item)
                if len(items) >= cfg.max_items_per_repo:
                    logger.info(
                        "discussions truncated at %d for %s", cfg.max_items_per_repo, repo
                    )  # AC-V2-006-013
                    return items

            page_info = conn.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")

        return items

    def fetch_releases(self, repo: str, lookback_days: int) -> list[RawItem]:
        """Fetch newly-published releases for ``repo`` within the last ``lookback_days``.

        Pure I/O. Mirrors ``fetch_items`` control-flow (ADR-001).

        Pagination: created-desc via ``Link`` rel=next; bounded by ``max_items_per_repo``
        and the ADR-001 dual-key early-stop:
          - **STOP** when a release's ``created_at`` < cutoff (endpoint's sort key —
            the "everything after is older" guarantee only holds against this field).
          - **SKIP (continue)** when ``published_at`` is None (draft) or < cutoff
            (created-recently but published-before-window) — do NOT stop.
          - **INCLUDE** when ``published_at`` >= cutoff (in-window published release).
        Prereleases are included unconditionally (AC-V2-003-004).
        Returns ``[]`` for a skipped repo (404/410, AC-V2-003-017).

        Conditional request (AC-V2-007-010..015, ADR-003):
        - On the FIRST page only: if ``conditional_cache.get("{repo}:releases")`` returns a
          validator, send ``If-None-Match: <validator>``. Sound because ``/releases`` is
          newest-first — any new in-window release appears on page 1 and changes its ETag.
        - ``304`` → return ``[]`` immediately (empty delta, no further pages).
        - ``200`` + ETag present → ``set("{repo}:releases", etag)`` in-memory.
        - Pages 2..N → unconditional.

        Security: reuses the same authed httpx client, GET-only, TLS on, base_url from
        config only (BR-V2-003-005 / AC-V2-003-015). Token never logged/returned.
        Same retry policy as fetch_items (AC-V2-003-016). No state/LLM access
        (AC-V2-003-018). GitHubClient Protocol unchanged (ADR-002).
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        self._validate_repo(repo)
        cfg = self._config

        # ⚠️ LOAD-BEARING: /releases is returned newest-first (created-desc).
        # The conditional on page 1 is ONLY sound against this ordering (ADR-003, RISK-002).
        url: str | None = f"{cfg.base_url}/repos/{repo}/releases?per_page={cfg.page_size}"
        items: list[RawItem] = []
        endpoint_key = f"{repo}:releases"
        first_page = True  # AC-V2-007-013: conditional header on FIRST page only

        while url and len(items) < cfg.max_items_per_repo:
            # Build conditional header for the first page (AC-V2-007-010)
            extra_headers: dict | None = None
            if first_page:
                cached_etag = self._conditional_cache.get(endpoint_key)
                if cached_etag is not None:
                    extra_headers = {"If-None-Match": cached_etag}

            response = self._request_with_retry(url, repo, extra_headers=extra_headers)

            # Handle first-page 304 — empty delta, no further pages (AC-V2-007-011, ADR-003)
            if first_page and response.status_code == 304:
                return []

            # First-page 200: record the fresh ETag in-memory (AC-V2-007-012)
            if first_page and response.status_code == 200:
                etag = response.headers.get("ETag")
                if etag:  # AC-V2-007-014: present-guard — no set() when header absent
                    self._conditional_cache.set(endpoint_key, etag)

            first_page = False  # pages 2..N are unconditional

            if self._classify(response) is _Action.SKIP_REPO:
                logger.warning(
                    "skipping repo '%s' releases (status %d)", repo, response.status_code
                )
                return []

            for raw in response.json():
                # ADR-001: early-stop uses created_at (the endpoint's sort key)
                created = raw.get("created_at")
                if isinstance(created, str) and _parse_created(created) < cutoff:
                    return items  # created-desc → everything after is older (AC-V2-003-013)

                # Drafts: skip without stopping (published_at is None → not yet published)
                published = raw.get("published_at")
                if published is None:
                    continue  # AC-V2-003-003: draft — do NOT return, only continue

                # Inclusion filter: published within the lookback window
                if not isinstance(published, str) or _parse_created(published) < cutoff:
                    continue  # AC-V2-003-002: published before window → skip item

                item = self._map_release(raw, repo)
                if item is not None:
                    items.append(item)
                if len(items) >= cfg.max_items_per_repo:
                    logger.info(
                        "releases truncated at %d for %s", cfg.max_items_per_repo, repo
                    )  # AC-V2-003-014
                    return items

            url = self._next_link(response.headers.get("Link"))

        return items

    def fetch_items(self, repo: str, lookback_days: int) -> list[RawItem]:
        """Fetch newly-opened issues for ``repo`` created within the last ``lookback_days``.

        Pure I/O. Paginates created-desc, stops early per-item on the cutoff (not page-level,
        AC-2-005), drops PRs (AC-2-018), caps at ``max_items_per_repo`` with an info
        truncation log (AC-2-006), and returns ``[]`` for a skipped repo (404/410, AC-2-011).

        Conditional request (AC-V2-007-010..015, ADR-003):
        - On the FIRST page only: if ``conditional_cache.get("{repo}:issues")`` returns a
          validator, send ``If-None-Match: <validator>``. This is sound because the endpoint
          is sorted newest-first (``sort=created&direction=desc``) — any new in-window item
          would change the first-page ETag, so a ``304`` provably means "nothing new".
        - ``304`` → return ``[]`` immediately (empty delta, no further pages).
        - ``200`` + ETag present → ``set("{repo}:issues", etag)`` in-memory, paginate as today.
        - ``200`` + no ETag → record nothing; continue pagination unchanged.
        - Pages 2..N → unconditional (no ``If-None-Match`` header).
        - Never persist here — ``set()`` is in-memory only; pipeline calls ``commit()`` later.
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        self._validate_repo(repo)
        cfg = self._config

        # ⚠️ LOAD-BEARING: this endpoint is fetched sort=created&direction=desc (newest-first).
        # The conditional request on page 1 is ONLY sound against newest-first ordering —
        # a new in-window item appears on page 1 and changes its ETag; a 304 proves nothing new.
        # Do NOT reorder this query away from direction=desc (ADR-003, RISK-002).
        url: str | None = (
            f"{cfg.base_url}/repos/{repo}/issues"
            f"?state=all&sort=created&direction=desc&per_page={cfg.page_size}"
        )
        items: list[RawItem] = []
        endpoint_key = f"{repo}:issues"
        first_page = True  # AC-V2-007-013: conditional header on FIRST page only

        while url and len(items) < cfg.max_items_per_repo:
            # Build conditional header for the first page (AC-V2-007-010)
            extra_headers: dict | None = None
            if first_page:
                cached_etag = self._conditional_cache.get(endpoint_key)
                if cached_etag is not None:
                    extra_headers = {"If-None-Match": cached_etag}

            response = self._request_with_retry(url, repo, extra_headers=extra_headers)

            # Handle first-page 304 — empty delta, no further pages (AC-V2-007-011, ADR-003)
            # Branch on raw status_code: both 200 and 304 map to _Action.OK (ADR-003 warning).
            if first_page and response.status_code == 304:
                return []  # nothing new for this endpoint; stored ETag unchanged

            # First-page 200: record the fresh ETag in-memory (AC-V2-007-012)
            if first_page and response.status_code == 200:
                etag = response.headers.get("ETag")
                if etag:  # AC-V2-007-014: present-guard — no set() when header absent
                    self._conditional_cache.set(endpoint_key, etag)

            first_page = False  # pages 2..N are unconditional (AC-V2-007-013)

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
