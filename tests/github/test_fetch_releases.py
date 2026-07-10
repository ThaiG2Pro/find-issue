"""Unit tests for GitHubCollector.fetch_releases (AC-V2-003-001..017).

All tests use httpx.MockTransport — no real API calls.
sleep is injected so retry/backoff tests never actually wait.
Every test references the AC-ID(s) it exercises (R3).
"""

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
from osspulse.models import RawItem

TOKEN = "ghp_SUPER_SECRET_TOKEN_value"  # noqa: S105 — test-only sentinel for leak assertions


# ---------------------------------------------------------------------------
# Helpers (mirror test_github_client.py conventions)
# ---------------------------------------------------------------------------


def iso(days_ago: float) -> str:
    """ISO-8601 Z timestamp `days_ago` days before now (UTC)."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def release(
    tag: str,
    published_days_ago: float = 1.0,
    created_days_ago: float | None = None,
    *,
    draft: bool = False,
    prerelease: bool = False,
    name: str | None = None,
    **overrides,
) -> dict:
    """Minimal GitHub release payload."""
    if created_days_ago is None:
        created_days_ago = published_days_ago
    base: dict = {
        "tag_name": tag,
        "name": name if name is not None else tag,
        "body": f"notes for {tag}",
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
        "published_at": None if draft else iso(published_days_ago),
        "created_at": iso(created_days_ago),
        "prerelease": prerelease,
    }
    base.update(overrides)
    return base


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


def single_page(items: list[dict]):
    """Handler returning items as a single page (no Link header)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=items)

    return handler


def paginated(pages: list[list[dict]], base_url: str = "https://api.github.com"):
    """Handler serving successive pages, with Link rel=next between them."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count[0]
        call_count[0] += 1
        data = pages[idx] if idx < len(pages) else []
        headers = {}
        if idx < len(pages) - 1:
            next_url = f"{base_url}/repos/o/r/releases?per_page=100&page={idx + 2}"
            headers["Link"] = f'<{next_url}>; rel="next"'
        return httpx.Response(200, json=data, headers=headers)

    return handler


# ---------------------------------------------------------------------------
# AC-V2-003-001: releases within the window are returned
# ---------------------------------------------------------------------------


def test_releases_in_window_returned():
    """Releases published within lookback window are returned as RawItems (AC-V2-003-001)."""
    collector, _ = make_collector(
        single_page(
            [
                release("v1.0.0", published_days_ago=1),
                release("v0.9.0", published_days_ago=5),
            ]
        )
    )
    items = collector.fetch_releases("o/r", lookback_days=7)
    assert len(items) == 2
    assert all(isinstance(i, RawItem) and i.item_type == "release" for i in items)
    assert [i.item_id for i in items] == ["v1.0.0", "v0.9.0"]


# ---------------------------------------------------------------------------
# AC-V2-003-002: releases older than cutoff are excluded
# ---------------------------------------------------------------------------


def test_releases_older_than_cutoff_excluded():
    """Only the in-window release is returned when one is outside the cutoff (AC-V2-003-002)."""
    collector, _ = make_collector(
        single_page(
            [
                release("v1.0.0", published_days_ago=2),
                release("v0.9.0", published_days_ago=40),
            ]
        )
    )
    items = collector.fetch_releases("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["v1.0.0"]


# ---------------------------------------------------------------------------
# AC-V2-003-003: drafts are skipped but do NOT trigger early-stop
# ---------------------------------------------------------------------------


def test_draft_release_skipped_does_not_stop():
    """Draft (published_at=null) is skipped; releases after it are still returned
    (AC-V2-003-003)."""
    collector, _ = make_collector(
        single_page(
            [
                release("v2.0.0", draft=True, created_days_ago=1),  # draft — skip but continue
                release("v1.0.0", published_days_ago=2),  # published in-window — include
            ]
        )
    )
    items = collector.fetch_releases("o/r", lookback_days=7)
    assert [i.item_id for i in items] == ["v1.0.0"]


# ---------------------------------------------------------------------------
# AC-V2-003-004: prereleases are included
# ---------------------------------------------------------------------------


def test_prerelease_is_included():
    """A prerelease=true release is included (AC-V2-003-004)."""
    collector, _ = make_collector(
        single_page([release("v2.0.0-beta", published_days_ago=1, prerelease=True)])
    )
    items = collector.fetch_releases("o/r", lookback_days=7)
    assert len(items) == 1
    assert items[0].item_id == "v2.0.0-beta"


# ---------------------------------------------------------------------------
# AC-V2-003-005: repo with no releases returns []
# ---------------------------------------------------------------------------


def test_empty_repo_returns_empty_list():
    """Repo with no releases returns an empty list without error (AC-V2-003-005)."""
    collector, _ = make_collector(single_page([]))
    assert collector.fetch_releases("o/r", lookback_days=7) == []


# ---------------------------------------------------------------------------
# AC-V2-003-012: config tunables drive per_page and cap (not literals)
# ---------------------------------------------------------------------------


def test_config_tunables_drive_per_page_and_cap():
    """per_page and max_items_per_repo come from config, not literals (AC-V2-003-012)."""
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        data = [release(f"v{i}.0.0", published_days_ago=1) for i in range(3)]
        return httpx.Response(200, json=data)

    cfg = CollectorConfig(max_items_per_repo=2, page_size=25)
    collector, _ = make_collector(handler, config=cfg)
    items = collector.fetch_releases("o/r", lookback_days=7)

    assert len(items) == 2  # capped at max_items_per_repo
    assert "per_page=25" in requests_seen[0]


# ---------------------------------------------------------------------------
# AC-V2-003-013: early-stop on created_at mid-pagination (ADR-001)
# ---------------------------------------------------------------------------


def test_early_stop_on_created_at_mid_pagination():
    """Stops when created_at < cutoff, requests no further pages (AC-V2-003-013)."""
    page1 = [release("v2.0.0", published_days_ago=1, created_days_ago=1)]
    page2 = [release("v1.0.0", published_days_ago=30, created_days_ago=30)]  # created old → stop
    page3 = [release("v0.9.0", published_days_ago=1, created_days_ago=1)]  # never reached

    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count[0]
        call_count[0] += 1
        pages = [page1, page2, page3]
        data = pages[idx] if idx < len(pages) else []
        headers = {}
        if idx < len(pages) - 1:
            next_url = f"https://api.github.com/repos/o/r/releases?per_page=100&page={idx + 2}"
            headers["Link"] = f'<{next_url}>; rel="next"'
        return httpx.Response(200, json=data, headers=headers)

    collector, _ = make_collector(handler)
    items = collector.fetch_releases("o/r", lookback_days=7)

    assert [i.item_id for i in items] == ["v2.0.0"]
    assert call_count[0] == 2  # page3 never requested


# ---------------------------------------------------------------------------
# AC-V2-003-014: truncation log at max_items cap
# ---------------------------------------------------------------------------


def test_truncation_log_at_max_items_cap(caplog):
    """Info log emitted when max_items_per_repo is reached (AC-V2-003-014)."""
    cfg = CollectorConfig(max_items_per_repo=2, page_size=100)
    data = [release(f"v{i}.0.0", published_days_ago=1) for i in range(5)]
    collector, _ = make_collector(single_page(data), config=cfg)

    with caplog.at_level(logging.INFO, logger="osspulse.github.client"):
        items = collector.fetch_releases("o/r", lookback_days=7)

    assert len(items) == 2
    assert any("truncated" in record.message and "2" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# AC-V2-003-015: token never appears in any log or error message
# ---------------------------------------------------------------------------


def test_token_never_in_log_or_error(caplog):
    """GITHUB_TOKEN value never appears in any log line or error message (AC-V2-003-015)."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[])

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=1, backoff_base_seconds=0, jitter_seconds=0)
    )
    with caplog.at_level(logging.DEBUG, logger="osspulse.github.client"):
        collector, _ = make_collector(handler, config=cfg)
        collector.fetch_releases("o/r", lookback_days=7)

    for record in caplog.records:
        assert TOKEN not in record.getMessage(), f"Token leaked in log: {record.getMessage()}"


def test_token_never_in_auth_error_message():
    """AuthError message never contains the token value (AC-V2-003-015)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    collector, _ = make_collector(handler)
    with pytest.raises(AuthError) as exc_info:
        collector.fetch_releases("o/r", lookback_days=7)

    assert TOKEN not in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC-V2-003-016: rate-limit is retried with backoff
# ---------------------------------------------------------------------------


def test_rate_limit_429_retried_then_succeeds():
    """429 is retried using the retry policy before eventually succeeding (AC-V2-003-016)."""
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if call_count[0] <= 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[release("v1.0.0", published_days_ago=1)])

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=3, backoff_base_seconds=0, jitter_seconds=0)
    )
    collector, slept = make_collector(handler, config=cfg)
    items = collector.fetch_releases("o/r", lookback_days=7)

    assert len(items) == 1
    assert call_count[0] == 3
    assert len(slept) == 2  # retried twice before success


def test_rate_limit_exhausted_raises_rate_limit_error():
    """Terminal RateLimitError raised when retry budget exhausted (AC-V2-003-016)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"})

    cfg = CollectorConfig(
        retry=RetryPolicy(max_retries=2, backoff_base_seconds=0, jitter_seconds=0)
    )
    collector, _ = make_collector(handler, config=cfg)

    with pytest.raises(RateLimitError):
        collector.fetch_releases("o/r", lookback_days=7)


# ---------------------------------------------------------------------------
# AC-V2-003-017: 404/410 → empty list; 401 → AuthError (fail fast)
# ---------------------------------------------------------------------------


def test_404_returns_empty_list():
    """404 on /releases → warn and return [] (AC-V2-003-017)."""
    collector, _ = make_collector(lambda r: httpx.Response(404))
    assert collector.fetch_releases("o/r", lookback_days=7) == []


def test_410_returns_empty_list():
    """410 on /releases → warn and return [] (AC-V2-003-017)."""
    collector, _ = make_collector(lambda r: httpx.Response(410))
    assert collector.fetch_releases("o/r", lookback_days=7) == []


def test_401_raises_auth_error():
    """401 on /releases → AuthError (fail fast, AC-V2-003-017)."""
    collector, _ = make_collector(lambda r: httpx.Response(401))
    with pytest.raises(AuthError):
        collector.fetch_releases("o/r", lookback_days=7)


# ---------------------------------------------------------------------------
# AC-V2-003-013 / ADR-001 RISK-002 regression tripwire (task 3.3)
#
# A release whose created_at is BEFORE the cutoff but published_at is WITHIN
# the window is missed by created-desc early-stop.
# This test DOCUMENTS the accepted behavior — if it breaks, someone reversed
# the stop key to published_at (the rejected Option-B data-loss bug).
# ---------------------------------------------------------------------------


def test_risk002_regression_old_created_recent_published_is_missed():
    """RISK-002 tripwire: release created before window but published within it is missed
    by created-desc early-stop, because early-stop keys on created_at (ADR-001 Option A).

    This is the ACCEPTED behavior — the miss is rare, bounded, and documented.
    If this test fails, the early-stop key was reversed to published_at (Option-B bug).
    (AC-V2-003-013 / ADR-001)
    """
    # Page 1: a recent, in-window release
    # Page 2: a release created 30 days ago but published 3 days ago (within window)
    #         — will be missed because created_at triggers early-stop first
    page1 = [release("v2.0.0", published_days_ago=1, created_days_ago=1)]
    page2 = [
        # created_at is 30 days old → early-stop fires; published_at=3d is irrelevant
        release("v1.9.9", published_days_ago=3, created_days_ago=30),
    ]
    page3 = [release("v1.0.0", published_days_ago=1, created_days_ago=1)]  # never reached

    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count[0]
        call_count[0] += 1
        pages = [page1, page2, page3]
        data = pages[idx] if idx < len(pages) else []
        headers = {}
        if idx < len(pages) - 1:
            next_url = f"https://api.github.com/repos/o/r/releases?per_page=100&page={idx + 2}"
            headers["Link"] = f'<{next_url}>; rel="next"'
        return httpx.Response(200, json=data, headers=headers)

    collector, _ = make_collector(handler)
    items = collector.fetch_releases("o/r", lookback_days=7)

    # v1.9.9 (old-created / recent-published) is NOT returned — accepted RISK-002 miss
    assert [i.item_id for i in items] == ["v2.0.0"]
    # page3 never fetched — the early-stop on created_at fired at page2
    assert call_count[0] == 2
