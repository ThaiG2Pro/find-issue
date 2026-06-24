"""Tests for the GitHub Collector adapter (S2).

All tests mock GitHub via ``httpx.MockTransport`` — no real API, no new dependency (ADR-005).
``sleep`` is injected so retry/backoff tests never actually wait. Every test references the
AC-ID(s) it exercises (R3).
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from osspulse.github import (
    AuthError,
    CollectorConfig,
    GitHubCollector,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
    RetryPolicy,
)
from osspulse.models import RawItem

TOKEN = "ghp_SUPER_SECRET_TOKEN_value"  # noqa: S105 — test-only sentinel for leak assertions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso(days_ago: float) -> str:
    """An ISO-8601 ``...Z`` timestamp ``days_ago`` days before now (UTC)."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(number: int, days_ago: float = 0, **overrides) -> dict:
    """A minimal GitHub issue payload, overridable per test."""
    base = {
        "number": number,
        "title": f"issue {number}",
        "body": f"body {number}",
        "html_url": f"https://github.com/o/r/issues/{number}",
        "created_at": iso(days_ago),
    }
    base.update(overrides)
    return base


def make_collector(
    handler,
    config: CollectorConfig | None = None,
    sleep=None,
) -> tuple[GitHubCollector, list[float]]:
    """Build a collector wired to a ``MockTransport`` handler.

    Returns the collector and a list capturing every ``sleep`` duration (so retry tests can
    assert no real wait happened and how long the backoff would have been).
    """
    slept: list[float] = []

    def _capture_sleep(seconds: float) -> None:
        slept.append(seconds)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url=(config or CollectorConfig()).base_url,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    collector = GitHubCollector(
        TOKEN,
        config or CollectorConfig(),
        client=client,
        sleep=sleep or _capture_sleep,
    )
    return collector, slept


def single_page(items: list[dict]):
    """A handler that always returns ``items`` as one page (no rel=next)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=items)

    return handler


# ---------------------------------------------------------------------------
# 7.1 Window & mapping
# ---------------------------------------------------------------------------


def test_in_window_issues_returned():
    """Issues created within lookback are returned (AC-2-001, AC-2-002, AC-2-004)."""
    collector, _ = make_collector(single_page([issue(1, 1), issue(2, 2)]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1", "2"]
    assert all(isinstance(i, RawItem) and i.item_type == "issue" for i in items)


def test_old_issues_excluded():
    """Issues older than the cutoff are excluded (AC-2-003, AC-2-005)."""
    collector, _ = make_collector(single_page([issue(1, 1), issue(2, 30)]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


def test_empty_result_returns_empty_list():
    """A repo with no in-window issues returns [] (AC-2-001)."""
    collector, _ = make_collector(single_page([]))
    assert collector.fetch_items("o/r", lookback_days=7) == []


def test_opened_then_closed_issue_kept():
    """state=all keeps an issue opened-in-window even if later closed (AC-2-002)."""
    collector, _ = make_collector(single_page([issue(5, 1, state="closed")]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["5"]


def test_item_id_is_str_number_and_created_at_unchanged():
    """item_id = str(number); created_at passed through verbatim (AC-2-016, AC-2-017)."""
    raw_created = iso(1)
    collector, _ = make_collector(single_page([issue(42, created_at=raw_created)]))
    [item] = collector.fetch_items("o/r", lookback_days=7)
    assert item.item_id == "42"
    assert item.created_at == raw_created


# ---------------------------------------------------------------------------
# 7.2 Pagination
# ---------------------------------------------------------------------------


def _two_page_handler(page1: list[dict], page2: list[dict]):
    """Page 1 carries a rel=next Link to page 2; page 2 has no next."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        next_url = f"{request.url}&page=2" if "?" in str(request.url) else f"{request.url}?page=2"
        return httpx.Response(200, json=page1, headers={"Link": f'<{next_url}>; rel="next"'})

    return handler


def test_cutoff_early_stop_at_page_two_boundary():
    """Per-item cutoff stops mid-page-2 (AC-2-005, not page-level)."""
    page1 = [issue(1, 1), issue(2, 2)]
    page2 = [issue(3, 3), issue(4, 30), issue(5, 31)]  # #4 is past cutoff
    collector, _ = make_collector(_two_page_handler(page1, page2))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1", "2", "3"]


def test_cap_reached_truncates_with_info_log(caplog):
    """max_items_per_repo cap → exactly N items + info truncation log (AC-2-006)."""
    cfg = CollectorConfig(max_items_per_repo=2)
    collector, _ = make_collector(single_page([issue(1, 1), issue(2, 1), issue(3, 1)]), cfg)
    with caplog.at_level(logging.INFO):
        items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1", "2"]
    assert any("truncated at 2" in r.message for r in caplog.records)


def test_missing_link_header_means_single_page():
    """Missing/malformed Link → single page, no further request (AC-2-007)."""
    collector, _ = make_collector(single_page([issue(1, 1)]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


@pytest.mark.parametrize(
    "link_header",
    [
        None,
        "",
        "garbage-without-semicolon",
        '<https://api.github.com/x>; rel="last"',  # no rel=next
        'no-brackets; rel="next"',  # url segment not wrapped in <>
    ],
)
def test_next_link_returns_none_for_malformed_headers(link_header):
    """_next_link handles every malformed shape → None (AC-2-007, BR-2-004)."""
    assert GitHubCollector._next_link(link_header) is None


def test_pull_requests_dropped():
    """Items carrying a pull_request field are dropped (AC-2-018)."""
    collector, _ = make_collector(
        single_page([issue(1, 1), issue(2, 1, pull_request={"url": "x"})])
    )
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


def test_per_page_and_max_items_honor_injected_config():
    """page_size + max_items_per_repo come from config, not hardcoded (AC-2-024)."""
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[issue(1, 1), issue(2, 1)])

    cfg = CollectorConfig(page_size=37, max_items_per_repo=1)
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url=cfg.base_url)
    collector = GitHubCollector(TOKEN, cfg, client=client, sleep=lambda s: None)
    items = collector.fetch_items("o/r", lookback_days=7)
    assert len(items) == 1  # max_items_per_repo=1 honored
    assert "per_page=37" in seen_urls[0]  # page_size honored


# ---------------------------------------------------------------------------
# 7.3 Security — token leak (T-I1, AC-2-009)
# ---------------------------------------------------------------------------


def test_token_absent_from_success_path(caplog):
    """On success: token never in logs nor any returned RawItem (AC-2-009)."""
    collector, _ = make_collector(single_page([issue(1, 1)]))
    with caplog.at_level(logging.DEBUG):
        items = collector.fetch_items("o/r", lookback_days=7)
    assert TOKEN not in caplog.text
    for item in items:
        assert TOKEN not in repr(item)


def test_token_absent_from_auth_error(caplog):
    """On 401: token absent from the raised exception text and logs (AC-2-009)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    collector, _ = make_collector(handler)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AuthError) as exc_info:
            collector.fetch_items("o/r", lookback_days=7)
    assert TOKEN not in str(exc_info.value)
    assert TOKEN not in caplog.text


def test_config_repr_has_no_token():
    """CollectorConfig never stores the token (AC-2-009)."""
    assert TOKEN not in repr(CollectorConfig())


def test_other_4xx_fails_fast():
    """A non-auth, non-retryable 4xx (e.g. 422) → fail fast (AC-2-008, ADR-003)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Unprocessable"})

    collector, _ = make_collector(handler)
    with pytest.raises(AuthError):
        collector.fetch_items("o/r", lookback_days=7)


def test_non_numeric_retry_after_falls_back_to_computed_backoff():
    """A garbage Retry-After header does not crash; computed backoff is used (AC-2-019)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "soon"}, json={})
        return httpx.Response(200, json=[issue(1, 1)])

    cfg = CollectorConfig(retry=RetryPolicy(backoff_base_seconds=2.0, jitter_seconds=0.0))
    collector, slept = make_collector(handler, cfg)
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]
    assert slept == [2.0]  # base * mult**0 + 0 jitter, not the bad header


# ---------------------------------------------------------------------------
# 7.4 Dirty data (T-T1, AC-2-010, AC-2-012)
# ---------------------------------------------------------------------------


def test_null_body_becomes_empty_string():
    """null body → "" (AC-2-010)."""
    collector, _ = make_collector(single_page([issue(1, 1, body=None)]))
    [item] = collector.fetch_items("o/r", lookback_days=7)
    assert item.body == ""


def test_missing_user_and_html_url_use_safe_defaults():
    """Missing html_url → "" and the item is still returned (AC-2-012)."""
    raw = issue(1, 1)
    del raw["html_url"]
    raw.pop("title", None)
    collector, _ = make_collector(single_page([raw]))
    [item] = collector.fetch_items("o/r", lookback_days=7)
    assert item.url == ""
    assert item.title == ""
    assert item.item_id == "1"


def test_missing_mandatory_field_skips_item_without_crash():
    """Missing number → item skipped, no crash (AC-2-010, AC-2-012)."""
    good = issue(1, 1)
    bad = issue(2, 1)
    del bad["number"]
    collector, _ = make_collector(single_page([bad, good]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


def test_missing_created_at_skipped_in_fetch_loop():
    """An item with no created_at is skipped before the cutoff compare, no crash (AC-2-010)."""
    bad = issue(2, 1)
    del bad["created_at"]
    collector, _ = make_collector(single_page([bad, issue(1, 1)]))
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]


# ---------------------------------------------------------------------------
# 7.5 Auth & per-repo isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_not_found_warns_and_returns_empty(status, caplog):
    """404/410 → warn + [] so the watchlist loop continues (AC-2-011)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "Not Found"})

    collector, _ = make_collector(handler)
    with caplog.at_level(logging.WARNING):
        assert collector.fetch_items("o/r", lookback_days=7) == []
    assert any("skipping repo" in r.message for r in caplog.records)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_fail_fast(status):
    """401 / non-rate-limit 403 → AuthError fail-fast, token absent (AC-2-008, AC-2-009)."""

    def handler(request: httpx.Request) -> httpx.Response:
        # 403 without X-RateLimit-Remaining:0 → permanent auth failure
        return httpx.Response(status, json={"message": "Forbidden"})

    collector, _ = make_collector(handler)
    with pytest.raises(AuthError) as exc_info:
        collector.fetch_items("o/r", lookback_days=7)
    assert TOKEN not in str(exc_info.value)  # token absent for both 401 and 403 (AC-2-009)


def test_secondary_rate_limit_is_retried_not_auth_error():
    """403 + X-RateLimit-Remaining:0 → backoff/retry, not AuthError (AC-2-020)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={})
        return httpx.Response(200, json=[issue(1, 1)])

    collector, slept = make_collector(handler)
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]
    assert calls["n"] == 2
    assert len(slept) == 1  # backed off once, did not fail fast


# ---------------------------------------------------------------------------
# 7.6 Retry / backoff (config-driven)
# ---------------------------------------------------------------------------


def test_retry_after_header_honored_on_429():
    """429 with Retry-After uses that wait (capped by ceiling) (AC-2-019)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "5"}, json={})
        return httpx.Response(200, json=[issue(1, 1)])

    collector, slept = make_collector(handler)
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]
    assert slept == [5.0]


def test_5xx_retried_then_succeeds():
    """A transient 5xx is retried, then the request succeeds (AC-2-021)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[issue(1, 1)])

    collector, slept = make_collector(handler)
    items = collector.fetch_items("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["1"]
    assert calls["n"] == 3
    assert len(slept) == 2


def test_exhausted_retries_raise_bounded():
    """Persistent 5xx → RateLimitError after a bounded number of attempts (AC-2-022)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    collector, slept = make_collector(handler)  # default max_retries=3
    with pytest.raises(RateLimitError):
        collector.fetch_items("o/r", lookback_days=7)
    assert len(slept) == 3  # 1 initial + 3 retries = 4 attempts, 3 sleeps — no infinite loop


def test_transport_error_retried_then_network_error():
    """A persistent transport error → NetworkError after retries (AC-2-023)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    collector, slept = make_collector(handler)
    with pytest.raises(NetworkError):
        collector.fetch_items("o/r", lookback_days=7)
    assert len(slept) == 3


def test_injected_retry_policy_changes_attempt_count():
    """A custom RetryPolicy changes the attempt budget without code edits (AC-2-026, AC-2-027)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=5, backoff_base_seconds=0.0, jitter_seconds=0.0)
    )
    collector, slept = make_collector(handler, cfg)
    with pytest.raises(RateLimitError):
        collector.fetch_items("o/r", lookback_days=7)
    assert len(slept) == 5  # 5 retries honored from config


def test_injected_sleep_means_no_real_wait():
    """Backoff uses the injected sleep — tests never actually wait (AC-2-026)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[issue(1, 1)])

    real_waits: list[float] = []
    collector, _ = make_collector(handler, sleep=real_waits.append)
    collector.fetch_items("o/r", lookback_days=7)
    assert real_waits  # sleep was called instead of time.sleep


# ---------------------------------------------------------------------------
# 7.7 SSRF / TLS / scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_repo", ["../x", "a/b/c", "", "noslash", "o/r?x=1"])
def test_malformed_repo_rejected_before_any_request(bad_repo):
    """Malformed repo → InvalidRepoError before any HTTP call (AC-2-014)."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json=[])

    collector, _ = make_collector(handler)
    with pytest.raises(InvalidRepoError):
        collector.fetch_items(bad_repo, lookback_days=7)
    assert called["n"] == 0  # no request was issued


def test_only_get_issued_and_base_url_from_config():
    """Only GET is issued; host/scheme from base_url, repo fills path (AC-2-013, AC-2-025)."""
    methods: list[str] = []
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        hosts.append(request.url.host)
        return httpx.Response(200, json=[issue(1, 1)])

    cfg = CollectorConfig(base_url="https://ghe.example.com")
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url=cfg.base_url)
    collector = GitHubCollector(TOKEN, cfg, client=client, sleep=lambda s: None)
    collector.fetch_items("o/r", lookback_days=7)
    assert methods == ["GET"]
    assert hosts == ["ghe.example.com"]


def test_default_client_enables_tls_verification():
    """GitHubCollector passes verify=True to httpx.Client (AC-2-013)."""
    from unittest.mock import patch

    captured: dict = {}
    real_init = httpx.Client.__init__

    def capturing_init(self, *args, **kwargs):
        captured["verify"] = kwargs.get("verify")
        real_init(self, *args, **kwargs)

    with patch.object(httpx.Client, "__init__", capturing_init):
        collector = GitHubCollector(TOKEN)
        collector._client.close()

    assert captured["verify"] is True


# ---------------------------------------------------------------------------
# Purity — pure I/O boundary (AC-2-015)
# ---------------------------------------------------------------------------


def test_collector_is_pure_io_no_state_or_llm():
    """The Collector implements GitHubClient and imports no State/LLM/cache (AC-2-015)."""
    import inspect

    from osspulse import ports
    from osspulse.github import client as client_module

    # Implements the port contract.
    assert hasattr(GitHubCollector, "fetch_items")
    assert hasattr(ports.GitHubClient, "fetch_items")

    # The module pulls in nothing from the state/summarizer/cache/delivery layers.
    source = inspect.getsource(client_module)
    forbidden = ("osspulse.state", "osspulse.summarizer", "osspulse.cache", "litellm", "redis")
    for name in forbidden:
        assert name not in source
