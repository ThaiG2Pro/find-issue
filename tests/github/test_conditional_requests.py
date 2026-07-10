"""Unit tests for GitHubCollector ETag conditional-request support.

All tests use ``httpx.MockTransport`` and a fake ``ConditionalCache`` (no real network).
Tests cover: null-cache regression, If-None-Match sending (strong + weak),
304→empty-delta, 200→set ETag, no-ETag-header path, retry on 429/5xx, auth fail-fast,
discussions untouched, token-discipline, page-2 unconditional.

Each test references the AC-ID it covers.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import httpx
import pytest

from osspulse.github.client import GitHubCollector
from osspulse.github.config import CollectorConfig
from osspulse.github.errors import AuthError, RateLimitError

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

TOKEN = "ghp_token"
TOKEN_SENTINEL = "ghp_token"  # used to assert it never appears in output
REPO = "owner/repo"
_FUTURE_CREATED = "2099-01-01T00:00:00Z"  # always within any lookback window
_OLD_CREATED = "2000-01-01T00:00:00Z"  # always outside any lookback window


def _issue(num: int, created: str = _FUTURE_CREATED) -> dict:
    return {
        "number": num,
        "title": f"Issue {num}",
        "body": "body",
        "html_url": f"https://github.com/{REPO}/issues/{num}",
        "created_at": created,
    }


def _release(tag: str, created: str = _FUTURE_CREATED, published: str = _FUTURE_CREATED) -> dict:
    return {
        "tag_name": tag,
        "name": f"Release {tag}",
        "body": "release notes",
        "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
        "created_at": created,
        "published_at": published,
    }


def _discussion_query_response(num: int) -> dict:
    return {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": [
                        {
                            "number": num,
                            "title": f"Discussion {num}",
                            "body": "text",
                            "url": f"https://github.com/{REPO}/discussions/{num}",
                            "createdAt": _FUTURE_CREATED,
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }


def _collector(transport: httpx.MockTransport, cache=None) -> GitHubCollector:
    """Build a collector with mock transport, no sleep (fast tests)."""
    client = httpx.Client(
        transport=transport,
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    cfg = CollectorConfig(page_size=10, max_items_per_repo=100)
    return GitHubCollector(TOKEN, cfg, client=client, sleep=lambda _: None, conditional_cache=cache)


class _Requests:
    """Records captured httpx.Request objects from a MockTransport."""

    def __init__(self) -> None:
        self._requests: list[httpx.Request] = []

    def append(self, req: httpx.Request) -> None:
        self._requests.append(req)

    def __iter__(self) -> Iterator[httpx.Request]:
        return iter(self._requests)

    def __len__(self) -> int:
        return len(self._requests)

    @property
    def headers_list(self) -> list[dict[str, str]]:
        return [dict(r.headers) for r in self._requests]


# ---------------------------------------------------------------------------
# AC-V2-007-009: null-cache collector behaves exactly as today (regression)
# ---------------------------------------------------------------------------


def test_null_cache_collector_unconditional_fetch_issues(tmp_path):
    """Collector with null cache issues unconditional requests, returns items (AC-V2-007-009)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(
            200,
            json=[_issue(1)],
            headers={"ETag": '"etag1"'},
        )

    c = _collector(httpx.MockTransport(handler))
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1
    assert items[0].item_id == "1"
    # No If-None-Match header was sent
    assert "if-none-match" not in captured.headers_list[0]


def test_no_cache_arg_uses_null_cache(tmp_path):
    """A collector built without conditional_cache arg uses _NullConditionalCache
    (AC-V2-007-009)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=[_issue(1)], headers={"ETag": '"etag1"'})

    # Build collector WITHOUT passing conditional_cache
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    c = GitHubCollector(TOKEN, client=client, sleep=lambda _: None)
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1
    assert "if-none-match" not in captured.headers_list[0]


# ---------------------------------------------------------------------------
# AC-V2-007-010/015: If-None-Match sent on first page (strong + weak ETags)
# ---------------------------------------------------------------------------


def test_first_page_sends_if_none_match_strong_etag_issues(tmp_path):
    """With a cached strong ETag, first GET carries If-None-Match verbatim (AC-V2-007-010/015)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=[_issue(1)], headers={"ETag": '"etag-new"'})

    cache = MagicMock()
    cache.get.return_value = '"etag-old"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_items(REPO, 7)

    assert len(captured) >= 1
    assert captured.headers_list[0].get("if-none-match") == '"etag-old"'


def test_first_page_sends_if_none_match_weak_etag_issues(tmp_path):
    """With a cached weak ETag, If-None-Match echoed verbatim (AC-V2-007-015)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=[_issue(1)], headers={"ETag": 'W/"etag-new"'})

    cache = MagicMock()
    cache.get.return_value = 'W/"etag-old"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_items(REPO, 7)

    assert captured.headers_list[0].get("if-none-match") == 'W/"etag-old"'


def test_first_page_sends_if_none_match_releases(tmp_path):
    """With a cached ETag, fetch_releases sends If-None-Match on first page (AC-V2-007-010)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=[_release("v1.0.0")], headers={"ETag": '"etag-new"'})

    cache = MagicMock()
    cache.get.return_value = '"etag-releases"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_releases(REPO, 7)

    assert captured.headers_list[0].get("if-none-match") == '"etag-releases"'


# ---------------------------------------------------------------------------
# AC-V2-007-011: first-page 304 → empty list, no page-2 request, ETag unchanged
# ---------------------------------------------------------------------------


def test_first_page_304_returns_empty_no_page2_issues(tmp_path):
    """First-page 304 → empty list for issues; no further page requests (AC-V2-007-011)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(304, content=b"")

    cache = MagicMock()
    cache.get.return_value = '"etag-cached"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_items(REPO, 7)

    assert items == []
    assert len(captured) == 1  # only one request — no page-2 request
    cache.set.assert_not_called()  # stored ETag unchanged


def test_first_page_304_returns_empty_no_page2_releases(tmp_path):
    """First-page 304 → empty list for releases; no further page requests (AC-V2-007-011)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(304, content=b"")

    cache = MagicMock()
    cache.get.return_value = '"etag-releases"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_releases(REPO, 7)

    assert items == []
    assert len(captured) == 1
    cache.set.assert_not_called()


# ---------------------------------------------------------------------------
# AC-V2-007-012: first-page 200 → set() with fresh ETag + pagination continues
# ---------------------------------------------------------------------------


def test_first_page_200_records_etag_and_paginates_issues(tmp_path):
    """200 + ETag → set() called with fresh ETag; pagination continues (AC-V2-007-012)."""
    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] == 1:
            # First page — has ETag + Link to next page
            return httpx.Response(
                200,
                json=[_issue(1)],
                headers={
                    "ETag": '"fresh-etag"',
                    "Link": '<https://api.github.com/next>; rel="next"',
                },
            )
        # Second page — no Link (last page)
        return httpx.Response(200, json=[_issue(2)], headers={})

    cache = MagicMock()
    cache.get.return_value = '"old-etag"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_items(REPO, 7)

    # set() called with fresh ETag from first-page 200
    cache.set.assert_called_once_with(f"{REPO}:issues", '"fresh-etag"')
    # Pagination continued — second page also fetched
    assert call_count[0] == 2
    assert len(items) == 2


def test_first_page_200_records_etag_releases(tmp_path):
    """200 + ETag → set() called for releases (AC-V2-007-012)."""
    cache = MagicMock()
    cache.get.return_value = '"old-releases-etag"'
    cache.set = MagicMock()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_release("v1.0.0")], headers={"ETag": '"fresh-releases"'})

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_releases(REPO, 7)

    cache.set.assert_called_once_with(f"{REPO}:releases", '"fresh-releases"')


# ---------------------------------------------------------------------------
# AC-V2-007-013: page 2+ unconditional — no If-None-Match on subsequent pages
# ---------------------------------------------------------------------------


def test_page2_carries_no_if_none_match_issues(tmp_path):
    """Pages 2..N carry no If-None-Match header (AC-V2-007-013)."""
    captured = _Requests()
    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(
                200,
                json=[_issue(1)],
                headers={
                    "ETag": '"etag1"',
                    "Link": '<https://api.github.com/next>; rel="next"',
                },
            )
        return httpx.Response(200, json=[_issue(2)], headers={})

    cache = MagicMock()
    cache.get.return_value = '"old-etag"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_items(REPO, 7)

    assert len(captured) == 2
    # First page: has If-None-Match
    assert "if-none-match" in captured.headers_list[0]
    # Second page: NO If-None-Match
    assert "if-none-match" not in captured.headers_list[1]


# ---------------------------------------------------------------------------
# AC-V2-007-014: 200 with no ETag header → no set(), no crash
# ---------------------------------------------------------------------------


def test_200_no_etag_header_no_set_no_crash_issues(tmp_path):
    """200 with no ETag header → set() NOT called, items returned, no crash (AC-V2-007-014)."""
    cache = MagicMock()
    cache.get.return_value = '"old-etag"'
    cache.set = MagicMock()

    def handler(req: httpx.Request) -> httpx.Response:
        # No ETag in response headers
        return httpx.Response(200, json=[_issue(1)], headers={})

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1
    cache.set.assert_not_called()  # no ETag → no set


def test_200_no_etag_no_crash_null_cache(tmp_path):
    """200 with no ETag, null cache → items returned normally, no crash (AC-V2-007-014)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_issue(1)], headers={})

    c = _collector(httpx.MockTransport(handler))
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1


# ---------------------------------------------------------------------------
# AC-V2-007-016: 429/5xx on conditional request → retry; 401 → fail-fast
# ---------------------------------------------------------------------------


def test_429_on_conditional_request_retries_issues(tmp_path):
    """429 on conditional request → retry (same _request_with_retry path) (AC-V2-007-016)."""
    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[_issue(1)], headers={"ETag": '"etag"'})

    cache = MagicMock()
    cache.get.return_value = '"etag-old"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1
    assert call_count[0] == 2  # retried once after 429


def test_401_on_conditional_request_fails_fast_issues(tmp_path):
    """401 on conditional request → AuthError fail-fast (AC-V2-007-016)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    cache = MagicMock()
    cache.get.return_value = '"etag-old"'

    c = _collector(httpx.MockTransport(handler), cache=cache)
    with pytest.raises(AuthError):
        c.fetch_items(REPO, 7)


def test_5xx_on_conditional_request_retries_then_raises(tmp_path):
    """500 on conditional request → retry up to max, then RateLimitError (AC-V2-007-016)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    cache = MagicMock()
    cache.get.return_value = '"etag-old"'

    # 0 max retries → fails immediately after first attempt
    from osspulse.github.config import RetryPolicy

    cfg_no_retry = CollectorConfig(
        page_size=10,
        max_items_per_repo=100,
        retry=RetryPolicy(max_retries=0, backoff_base_seconds=0, jitter_seconds=0),
    )
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    c = GitHubCollector(
        TOKEN, cfg_no_retry, client=client, sleep=lambda _: None, conditional_cache=cache
    )
    with pytest.raises(RateLimitError):
        c.fetch_items(REPO, 7)


# ---------------------------------------------------------------------------
# AC-V2-007-017: fetch_discussions sends no conditional header
# ---------------------------------------------------------------------------


def test_fetch_discussions_sends_no_conditional_header(tmp_path):
    """fetch_discussions never sends If-None-Match — GraphQL has no ETag (AC-V2-007-017)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=_discussion_query_response(1))

    cache = MagicMock()
    cache.get.return_value = '"cached-etag"'
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_discussions(REPO, 7)

    assert len(captured) >= 1
    # No If-None-Match on the GraphQL POST
    assert "if-none-match" not in captured.headers_list[0]
    # cache.get never called for discussions — discussions key is never queried
    # (cache.get may be called for other reasons in future, but not by fetch_discussions)
    for call_args in cache.get.call_args_list:
        key = call_args[0][0]
        assert "discussion" not in key, f"cache.get called with discussion key: {key}"


def test_fetch_discussions_cache_set_never_called(tmp_path):
    """fetch_discussions never calls cache.set (AC-V2-007-017)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_discussion_query_response(1))

    cache = MagicMock()
    cache.get.return_value = None

    c = _collector(httpx.MockTransport(handler), cache=cache)
    c.fetch_discussions(REPO, 7)

    cache.set.assert_not_called()


# ---------------------------------------------------------------------------
# AC-V2-007-018: token never in any log/error on the conditional path
# ---------------------------------------------------------------------------


def test_token_not_in_conditional_path_error_message(tmp_path, caplog):
    """Token sentinel never appears in any log/error on the conditional path
    (AC-V2-007-018)."""
    import logging

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    cache = MagicMock()
    cache.get.return_value = '"cached-etag"'

    c = _collector(httpx.MockTransport(handler), cache=cache)

    with caplog.at_level(logging.DEBUG, logger="osspulse.github.client"):
        with pytest.raises(AuthError) as exc_info:
            c.fetch_items(REPO, 7)

    # Token must not appear in the exception message
    assert TOKEN_SENTINEL not in str(exc_info.value)
    # Token must not appear in any log record
    for record in caplog.records:
        assert TOKEN_SENTINEL not in record.getMessage()


# ---------------------------------------------------------------------------
# Regression: no If-None-Match when cache.get returns None
# ---------------------------------------------------------------------------


def test_no_cached_etag_no_if_none_match_header(tmp_path):
    """When cache.get returns None (miss), no If-None-Match header is sent (AC-V2-007-009)."""
    captured = _Requests()

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=[_issue(1)], headers={"ETag": '"fresh"'})

    cache = MagicMock()
    cache.get.return_value = None  # cache miss
    cache.set = MagicMock()

    c = _collector(httpx.MockTransport(handler), cache=cache)
    items = c.fetch_items(REPO, 7)

    assert len(items) == 1
    assert "if-none-match" not in captured.headers_list[0]
    # set() still called because 200 + ETag present
    cache.set.assert_called_once()
