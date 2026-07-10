"""Unit tests for GitHubCollector.fetch_discussions (AC-V2-006-001..017).

All tests use httpx.MockTransport — no real API calls.
sleep is injected so retry/backoff tests never actually wait.
Every test references the AC-ID(s) it exercises (R3).
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from osspulse.github import (
    AuthError,
    CollectorConfig,
    GitHubCollector,
    RateLimitError,
    RetryPolicy,
)
from osspulse.github.errors import CollectorError

TOKEN = "ghp_SUPER_SECRET_TOKEN_value"  # noqa: S105 — test-only sentinel for leak assertions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso(days_ago: float) -> str:
    """ISO-8601 Z timestamp ``days_ago`` days before now (UTC)."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def graphql_response(
    discussions: list[dict] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
    *,
    repository_null: bool = False,
    discussions_null: bool = False,
    errors: list[dict] | None = None,
) -> dict:
    """Build a minimal GitHub GraphQL response payload."""
    if repository_null:
        data: dict = {"repository": None}
    elif discussions_null:
        data = {"repository": {"discussions": None}}
    else:
        data = {
            "repository": {
                "discussions": {
                    "nodes": discussions or [],
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                }
            }
        }
    payload: dict = {"data": data}
    if errors is not None:
        payload["errors"] = errors
    return payload


def discussion_node(
    number: int,
    days_ago: float = 1.0,
    *,
    title: str | None = None,
    body: str | None = None,
    url: str | None = None,
) -> dict:
    """Minimal GraphQL discussion node."""
    return {
        "number": number,
        "title": title if title is not None else f"Discussion {number}",
        "body": body if body is not None else f"Body {number}",
        "url": url if url is not None else f"https://github.com/o/r/discussions/{number}",
        "createdAt": iso(days_ago),
    }


def make_collector(
    handler,
    config: CollectorConfig | None = None,
) -> tuple[GitHubCollector, list[float]]:
    """Build a collector wired to a MockTransport handler."""
    slept: list[float] = []

    def _capture_sleep(seconds: float) -> None:
        slept.append(seconds)

    cfg = config or CollectorConfig()
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url=cfg.base_url,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    collector = GitHubCollector(TOKEN, cfg, client=client, sleep=_capture_sleep)
    return collector, slept


def single_graphql(payload: dict):
    """Handler returning a single GraphQL response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


# ---------------------------------------------------------------------------
# AC-V2-006-001: discussions within the window are returned as RawItems
# ---------------------------------------------------------------------------


def test_discussions_in_window_returned():
    """Discussions within lookback window returned as RawItems with item_type=discussion
    (AC-V2-006-001, AC-V2-006-002)."""
    payload = graphql_response(
        [
            discussion_node(1, days_ago=1),
            discussion_node(2, days_ago=5),
        ]
    )
    collector, _ = make_collector(single_graphql(payload))
    items = collector.fetch_discussions("o/r", lookback_days=7)
    assert len(items) == 2
    assert all(i.item_type == "discussion" for i in items)
    assert [i.item_id for i in items] == ["1", "2"]


# ---------------------------------------------------------------------------
# AC-V2-006-002: older discussions excluded by early-stop
# ---------------------------------------------------------------------------


def test_older_discussion_excluded_early_stop():
    """Discussion older than cutoff is excluded; early-stop fires (AC-V2-006-002, AC-V2-006-012)."""
    payload = graphql_response(
        [
            discussion_node(1, days_ago=2),
            discussion_node(2, days_ago=30),  # beyond cutoff → early-stop
        ]
    )
    collector, _ = make_collector(single_graphql(payload))
    items = collector.fetch_discussions("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


# ---------------------------------------------------------------------------
# AC-V2-006-003: disabled Discussions repo — data.repository.discussions == null
# ---------------------------------------------------------------------------


def test_discussions_disabled_null_discussions_skips_repo(caplog):
    """data.repository.discussions == null (+ errors) → WARN + [] (AC-V2-006-003, ADR-003)."""
    payload = graphql_response(
        discussions_null=True,
        errors=[{"type": "NOT_FOUND", "message": "Discussions not enabled for this repo"}],
    )
    collector, _ = make_collector(single_graphql(payload))

    with caplog.at_level(logging.WARNING, logger="osspulse.github.client"):
        items = collector.fetch_discussions("o/r", lookback_days=7)

    assert items == []
    assert any("null connection" in r.message or "disabled" in r.message for r in caplog.records)


def test_discussions_disabled_null_repository_skips_repo(caplog):
    """data.repository == null → WARN + [], run continues (AC-V2-006-003, ADR-003 step 1)."""
    payload = graphql_response(repository_null=True)
    collector, _ = make_collector(single_graphql(payload))

    with caplog.at_level(logging.WARNING, logger="osspulse.github.client"):
        items = collector.fetch_discussions("o/r", lookback_days=7)

    assert items == []
    assert any(
        "null connection" in r.message or "disabled" in r.message or "not found" in r.message
        for r in caplog.records
    )


def test_disabled_null_shape_detected_BEFORE_errors_raise():
    """ADR-003 order: null-shape SKIP_REPO fires before the generic errors-raise.

    A disabled repo payload carries BOTH a null connection AND an errors entry.
    If the order were reversed, this would raise instead of skip — a run-crashing bug.
    (AC-V2-006-003, ADR-003 active concern)
    """
    # Payload that has BOTH null discussions AND a non-RATE_LIMITED error
    payload = graphql_response(
        discussions_null=True,
        errors=[{"type": "SOME_OTHER_ERROR", "message": "Something went wrong"}],
    )
    collector, _ = make_collector(single_graphql(payload))
    # Must NOT raise — null-shape check must precede the errors-raise
    items = collector.fetch_discussions("o/r", lookback_days=7)
    assert items == []


# ---------------------------------------------------------------------------
# AC-V2-006-004: enabled but empty repo → [] with no error
# ---------------------------------------------------------------------------


def test_enabled_empty_repo_returns_empty_list():
    """Enabled repo with no discussions in window → empty list, no error (AC-V2-006-004)."""
    payload = graphql_response([])  # empty nodes
    collector, _ = make_collector(single_graphql(payload))
    assert collector.fetch_discussions("o/r", lookback_days=7) == []


# ---------------------------------------------------------------------------
# AC-V2-006-011: cursor pagination — multi-page fetch
# ---------------------------------------------------------------------------


def test_cursor_pagination_follows_pages():
    """hasNextPage=True causes a second request with the endCursor (AC-V2-006-011)."""
    requests_made: list[dict] = []
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests_made.append(body)
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            payload = graphql_response(
                [discussion_node(1, days_ago=1)],
                has_next_page=True,
                end_cursor="cursor-abc",
            )
        else:
            payload = graphql_response(
                [discussion_node(2, days_ago=2)],
                has_next_page=False,
            )
        return httpx.Response(200, json=payload)

    collector, _ = make_collector(handler)
    items = collector.fetch_discussions("o/r", lookback_days=7)

    assert len(items) == 2
    assert call_count[0] == 2
    # First request: after=None; second request: after="cursor-abc"
    assert requests_made[0]["variables"]["after"] is None
    assert requests_made[1]["variables"]["after"] == "cursor-abc"


# ---------------------------------------------------------------------------
# AC-V2-006-012: early-stop mid-pagination (ADR-001)
# ---------------------------------------------------------------------------


def test_early_stop_mid_pagination_requests_no_further_pages():
    """Early-stop on createdAt < cutoff mid-pagination — no further pages requested
    (AC-V2-006-012, ADR-001)."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            # Page 1: in-window + cursor to page 2
            payload = graphql_response(
                [discussion_node(1, days_ago=1)],
                has_next_page=True,
                end_cursor="cursor-1",
            )
        elif idx == 1:
            # Page 2: out-of-window → triggers early-stop
            payload = graphql_response(
                [discussion_node(2, days_ago=30)],
                has_next_page=True,  # would have more pages, but early-stop fires
                end_cursor="cursor-2",
            )
        else:
            # Page 3: should never be reached
            payload = graphql_response([discussion_node(3, days_ago=1)])
        return httpx.Response(200, json=payload)

    collector, _ = make_collector(handler)
    items = collector.fetch_discussions("o/r", lookback_days=7)

    assert [i.item_id for i in items] == ["1"]
    assert call_count[0] == 2  # page 3 never requested


# ---------------------------------------------------------------------------
# AC-V2-006-013: config tunables drive first/cap (not literals)
# ---------------------------------------------------------------------------


def test_config_tunables_drive_first_and_cap():
    """page_size → first: variable; max_items_per_repo → cap (AC-V2-006-013, ADR-001)."""
    requests_seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests_seen.append(body)
        nodes = [discussion_node(i, days_ago=1) for i in range(1, 6)]
        return httpx.Response(200, json=graphql_response(nodes))

    cfg = CollectorConfig(max_items_per_repo=2, page_size=25)
    collector, _ = make_collector(handler, config=cfg)
    items = collector.fetch_discussions("o/r", lookback_days=7)

    assert len(items) == 2  # capped at max_items_per_repo
    assert requests_seen[0]["variables"]["first"] == 25


def test_truncation_info_log_at_cap(caplog):
    """Info log emitted when max_items_per_repo is reached (AC-V2-006-013)."""
    cfg = CollectorConfig(max_items_per_repo=2, page_size=100)
    nodes = [discussion_node(i, days_ago=1) for i in range(1, 6)]
    payload = graphql_response(nodes)
    collector, _ = make_collector(single_graphql(payload), config=cfg)

    with caplog.at_level(logging.INFO, logger="osspulse.github.client"):
        items = collector.fetch_discussions("o/r", lookback_days=7)

    assert len(items) == 2
    assert any("truncated" in r.message and "2" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC-V2-006-014: non-disabled top-level errors → raise (not silent empty)
# ---------------------------------------------------------------------------


def test_graphql_non_disabled_errors_raises_collector_error():
    """200 with non-disabled/non-not-found top-level errors → raises CollectorError
    (AC-V2-006-014, ADR-003 step 2)."""
    payload = graphql_response(
        discussions=[],
        errors=[{"type": "FORBIDDEN", "message": "Forbidden"}],
    )
    # Note: discussions is NOT null — this is a real error, not disabled shape
    collector, _ = make_collector(single_graphql(payload))
    with pytest.raises(CollectorError):
        collector.fetch_discussions("o/r", lookback_days=7)


def test_graphql_rate_limited_error_raises_rate_limit_error():
    """200 with RATE_LIMITED error type → RateLimitError (AC-V2-006-014, AC-V2-006-015)."""
    payload = graphql_response(
        discussions=[],
        errors=[{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}],
    )
    collector, _ = make_collector(single_graphql(payload))
    with pytest.raises(RateLimitError):
        collector.fetch_discussions("o/r", lookback_days=7)


def test_no_errors_key_not_raises():
    """Payload without an errors key is not an error (AC-V2-006-014)."""
    payload = graphql_response([discussion_node(1, days_ago=1)])
    collector, _ = make_collector(single_graphql(payload))
    items = collector.fetch_discussions("o/r", lookback_days=7)
    assert len(items) == 1


def test_empty_errors_array_not_raises():
    """Payload with errors=[] (empty) is treated as success (AC-V2-006-014)."""
    # Build payload manually with empty errors array
    payload = graphql_response([discussion_node(1, days_ago=1)])
    payload["errors"] = []  # empty list — falsy, should not raise
    collector, _ = make_collector(single_graphql(payload))
    items = collector.fetch_discussions("o/r", lookback_days=7)
    assert len(items) == 1


# ---------------------------------------------------------------------------
# AC-V2-006-015: transport 429/5xx retried; 401 → AuthError fail-fast
# ---------------------------------------------------------------------------


def test_transport_429_retried_then_succeeds():
    """429 on the GraphQL POST retried, then succeeds (AC-V2-006-015)."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] <= 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=graphql_response([discussion_node(1, days_ago=1)]))

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=3, backoff_base_seconds=0, jitter_seconds=0)
    )
    collector, slept = make_collector(handler, config=cfg)
    items = collector.fetch_discussions("o/r", lookback_days=7)

    assert len(items) == 1
    assert call_count[0] == 3
    assert len(slept) == 2


def test_transport_429_exhausted_raises_rate_limit_error():
    """Terminal RateLimitError raised when retry budget exhausted (AC-V2-006-015)."""
    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=2, backoff_base_seconds=0, jitter_seconds=0)
    )
    collector, _ = make_collector(
        lambda r: httpx.Response(429, headers={"Retry-After": "0"}), config=cfg
    )
    with pytest.raises(RateLimitError):
        collector.fetch_discussions("o/r", lookback_days=7)


def test_transport_401_raises_auth_error():
    """401 on the GraphQL POST → AuthError fail-fast (AC-V2-006-015)."""
    collector, _ = make_collector(lambda r: httpx.Response(401))
    with pytest.raises(AuthError):
        collector.fetch_discussions("o/r", lookback_days=7)


def test_transport_403_non_rate_limit_raises_auth_error():
    """403 without X-RateLimit-Remaining: 0 → AuthError (AC-V2-006-015)."""
    collector, _ = make_collector(lambda r: httpx.Response(403))
    with pytest.raises(AuthError):
        collector.fetch_discussions("o/r", lookback_days=7)


# ---------------------------------------------------------------------------
# AC-V2-006-016: GraphQL POST — only POST, never mutation, only variables
# ADR-002 regression: REST callers still GET
# ---------------------------------------------------------------------------


def test_fetch_discussions_issues_exactly_one_post_per_page():
    """fetch_discussions issues a POST (not GET) to /graphql with a query key
    (never a mutation), and only owner/name/cursor/first as variables (AC-V2-006-016)."""
    requests_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_captured.append(request)
        return httpx.Response(200, json=graphql_response([discussion_node(1, days_ago=1)]))

    collector, _ = make_collector(handler)
    collector.fetch_discussions("o/r", lookback_days=7)

    assert len(requests_captured) == 1
    req = requests_captured[0]
    # Must be POST
    assert req.method == "POST"
    # URL must include /graphql
    assert "/graphql" in str(req.url)
    # Body must contain a query field with the word "query" (not "mutation")
    body = json.loads(req.content)
    assert "query" in body
    assert "mutation" not in body["query"].lower()
    # Variables must only have owner, name, first, after
    variables = body["variables"]
    assert set(variables.keys()) == {"owner", "name", "first", "after"}
    assert variables["owner"] == "o"
    assert variables["name"] == "r"


def test_fetch_items_still_issues_get_adr002_regression():
    """REST fetch_items still issues GET — json_body=None default preserved (ADR-002)."""
    requests_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_captured.append(request)
        return httpx.Response(200, json=[])

    collector, _ = make_collector(handler)
    collector.fetch_items("o/r", lookback_days=7)

    assert len(requests_captured) >= 1
    assert requests_captured[0].method == "GET"
    # No request body for GET
    assert not requests_captured[0].content or requests_captured[0].content == b""


def test_fetch_releases_still_issues_get_adr002_regression():
    """REST fetch_releases still issues GET — json_body=None default preserved (ADR-002)."""
    requests_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_captured.append(request)
        return httpx.Response(200, json=[])

    collector, _ = make_collector(handler)
    collector.fetch_releases("o/r", lookback_days=7)

    assert len(requests_captured) >= 1
    assert requests_captured[0].method == "GET"
    assert not requests_captured[0].content or requests_captured[0].content == b""


# ---------------------------------------------------------------------------
# AC-V2-006-017: token never in logs or errors
# ---------------------------------------------------------------------------


def test_token_never_in_log_lines_on_graphql_path(caplog):
    """GITHUB_TOKEN value never appears in any log line on the GraphQL path (AC-V2-006-017)."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=graphql_response([]))

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=1, backoff_base_seconds=0, jitter_seconds=0)
    )
    with caplog.at_level(logging.DEBUG, logger="osspulse.github.client"):
        collector, _ = make_collector(handler, config=cfg)
        collector.fetch_discussions("o/r", lookback_days=7)

    for record in caplog.records:
        assert TOKEN not in record.getMessage(), f"Token leaked in log: {record.getMessage()}"


def test_token_never_in_auth_error_message():
    """AuthError message never contains the token value (AC-V2-006-017)."""
    collector, _ = make_collector(lambda r: httpx.Response(401))
    with pytest.raises(AuthError) as exc_info:
        collector.fetch_discussions("o/r", lookback_days=7)
    assert TOKEN not in str(exc_info.value)


def test_token_never_in_rate_limit_error_message():
    """RateLimitError message never contains the token value (AC-V2-006-017)."""
    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=0, backoff_base_seconds=0, jitter_seconds=0)
    )
    collector, _ = make_collector(
        lambda r: httpx.Response(429, headers={"Retry-After": "0"}), config=cfg
    )
    with pytest.raises(RateLimitError) as exc_info:
        collector.fetch_discussions("o/r", lookback_days=7)
    assert TOKEN not in str(exc_info.value)


def test_token_not_in_graphql_request_body():
    """Token must not appear in the GraphQL POST body (AC-V2-006-017, RISK-001)."""
    requests_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_captured.append(request)
        return httpx.Response(200, json=graphql_response([]))

    collector, _ = make_collector(handler)
    collector.fetch_discussions("o/r", lookback_days=7)

    assert len(requests_captured) == 1
    body_str = requests_captured[0].content.decode()
    assert TOKEN not in body_str


# ---------------------------------------------------------------------------
# AC-V2-006-017: URL comes from config base_url, never from repo
# ---------------------------------------------------------------------------


def test_graphql_url_derived_from_config_base_url():
    """GraphQL endpoint URL derives only from config.base_url (AC-V2-006-017, RISK-002)."""
    requests_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_captured.append(request)
        return httpx.Response(200, json=graphql_response([]))

    collector, _ = make_collector(handler)
    collector.fetch_discussions("o/r", lookback_days=7)

    assert len(requests_captured) == 1
    url = str(requests_captured[0].url)
    # URL must be /graphql path, not anything derived from repo owner/name
    assert url.endswith("/graphql")
    # Owner/name appear only in variables, not in URL
    assert "o/r" not in url
    assert "owner" not in url
