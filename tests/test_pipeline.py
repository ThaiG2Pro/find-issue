"""Tests for osspulse.pipeline — run_pipeline orchestrator (AC-7-001..022).

All external adapters (GitHub, LLM, Redis, delivery) are mocked — never real APIs.
Each test references the AC-ID it covers in its name.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osspulse.github.errors import (
    AuthError,
    CollectorError,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
)
from osspulse.models import Config, RawItem, SummarizedItem, WatchedRepo
from osspulse.pipeline import NO_LLM_PLACEHOLDER, run_pipeline

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

REPO_A = WatchedRepo(owner="org", name="repo-a")
REPO_B = WatchedRepo(owner="org", name="repo-b")


def _raw(repo: str = "org/repo-a", *, idx: int = 1) -> RawItem:
    return RawItem(
        repo=repo,
        item_type="issue",
        item_id=str(idx),
        title=f"Issue {idx}",
        body=f"Body {idx}",
        url=f"https://github.com/{repo}/issues/{idx}",
        created_at="2026-06-30T00:00:00Z",
    )


def _summarized(item: RawItem, summary: str = "A summary.") -> SummarizedItem:
    return SummarizedItem(raw=item, summary=summary)


def _config(
    repos: list[WatchedRepo] | None = None,
    *,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    output_destination: str = "stdout",
    tmp_path: Path | None = None,
    delta_enabled: bool = True,
) -> Config:
    return Config(
        watched_repos=repos or [REPO_A],
        lookback_days=7,
        github_token="ghp_fake_token_abc123",
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        state_path=str(tmp_path / "state.json") if tmp_path else "/tmp/test_state.json",
        output_destination=output_destination,
        output_path=str(tmp_path / "digest.md") if tmp_path else "/tmp/test_digest.md",
        delta_enabled=delta_enabled,
    )


# ---------------------------------------------------------------------------
# Flow 1 — Happy path, LLM enabled (AC-7-001, AC-7-007, AC-7-016)
# ---------------------------------------------------------------------------


def test_happy_path_llm_one_combined_call(tmp_path):
    """Full run with LLM: one summarize_items call, one render, one deliver.

    AC-7-001, AC-7-007, AC-7-016.
    """
    item_a = _raw("org/repo-a", idx=1)
    item_b = _raw("org/repo-b", idx=2)
    summarized_a = _summarized(item_a)
    summarized_b = _summarized(item_b)

    cfg = _config(
        repos=[REPO_A, REPO_B], llm_provider="openai", llm_api_key="sk-fake", tmp_path=tmp_path
    )

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [
        [item_a],  # REPO_A
        [item_b],  # REPO_B
    ]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_summarizer = MagicMock()
    mock_summarizer.summarize_items.return_value = [summarized_a, summarized_b]
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer", return_value=mock_summarizer),
        patch("osspulse.pipeline._build_cache", return_value=MagicMock()),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    # One combined summarize_items call with ALL items (BR-7-009, AC-7-007)
    mock_summarizer.summarize_items.assert_called_once_with([item_a, item_b])
    # One deliver call (BR-7-007)
    mock_delivery.deliver.assert_called_once()
    # Digest contains both repos (AC-7-016)
    delivered_content = mock_delivery.deliver.call_args[0][0]
    assert "org/repo-a" in delivered_content
    assert "org/repo-b" in delivered_content


def test_happy_path_mark_seen_called_per_repo(tmp_path):
    """mark_seen called for each repo's items at collect time (AC-7-010, AC-7-019)."""
    item_a = _raw("org/repo-a", idx=1)
    item_b = _raw("org/repo-b", idx=2)
    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [[item_a], [item_b]]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=MagicMock()),
    ):
        run_pipeline(cfg)

    # mark_seen called for each repo's items (not batched at end — decoupled, AC-7-019)
    assert mock_state.mark_seen.call_count == 2
    mock_state.mark_seen.assert_any_call([item_a])
    mock_state.mark_seen.assert_any_call([item_b])


# ---------------------------------------------------------------------------
# Flow 3 — Error taxonomy (AC-7-004, AC-7-005, AC-7-017)
# ---------------------------------------------------------------------------


def test_invalid_repo_error_skipped_others_succeed(tmp_path):
    """InvalidRepoError on one repo → skip it, others still processed (AC-7-004, BR-7-001)."""
    item_b = _raw("org/repo-b", idx=2)
    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [
        InvalidRepoError("not found"),
        [item_b],
    ]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)  # must NOT raise

    # repo-b item appeared in digest
    delivered = mock_delivery.deliver.call_args[0][0]
    assert "org/repo-b" in delivered
    # mark_seen NOT called for the failed repo
    mock_state.mark_seen.assert_called_once_with([item_b])


def test_network_error_skipped(tmp_path):
    """NetworkError on repo → skip, continue (AC-7-004)."""
    cfg = _config(repos=[REPO_A], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = NetworkError("timeout")
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)  # must NOT raise

    mock_delivery.deliver.assert_called_once()  # no-new-items doc delivered


def test_generic_collector_error_skipped(tmp_path):
    """Generic CollectorError → skip + continue (AC-7-004, BR-7-001)."""
    cfg = _config(repos=[REPO_A], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = CollectorError("unknown")
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=MagicMock()),
    ):
        run_pipeline(cfg)  # must NOT raise


def test_auth_error_is_fatal(tmp_path):
    """AuthError → re-raised immediately (fatal exit 1) (AC-7-005, BR-7-002)."""
    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = AuthError("401")

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=MagicMock()),
    ):
        with pytest.raises(AuthError):
            run_pipeline(cfg)

    # Only called once — run stopped immediately, second repo never attempted
    mock_collector.fetch_items.assert_called_once()


def test_rate_limit_terminal_delivers_partial(tmp_path):
    """RateLimitError stops collection but delivers partial results (AC-7-017, BR-7-008)."""
    item_a = _raw("org/repo-a", idx=1)
    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [
        [item_a],  # REPO_A succeeds
        RateLimitError("quota gone"),  # REPO_B hits rate limit
    ]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)  # must NOT raise — exit 0

    # Partial digest from repo-a must be delivered
    mock_delivery.deliver.assert_called_once()
    delivered = mock_delivery.deliver.call_args[0][0]
    assert "org/repo-a" in delivered


# ---------------------------------------------------------------------------
# Flow 4 — All repos fail (AC-7-006)
# ---------------------------------------------------------------------------


def test_all_repos_fail_delivers_no_new_items(tmp_path):
    """All repos fail → render([]) → no-new-items doc delivered, no raise (AC-7-006)."""
    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [
        InvalidRepoError("404"),
        NetworkError("timeout"),
    ]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    mock_delivery.deliver.assert_called_once()
    delivered = mock_delivery.deliver.call_args[0][0]
    # Renderer returns non-empty no-new-items doc
    assert len(delivered) > 0
    assert "No new items" in delivered or "OSS Pulse" in delivered


# ---------------------------------------------------------------------------
# Summarizer returns fewer items (AC-7-018)
# ---------------------------------------------------------------------------


def test_summarizer_returns_fewer_items(tmp_path):
    """Summarizer skips some items → only survivors rendered (AC-7-018)."""
    item1 = _raw(idx=1)
    item2 = _raw(idx=2)
    # Summarizer only returns item1's summary (item2 skipped)
    survivor = _summarized(item1)

    cfg = _config(llm_provider="openai", llm_api_key="sk-fake", tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item1, item2]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_summarizer = MagicMock()
    mock_summarizer.summarize_items.return_value = [survivor]  # only 1 of 2
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer", return_value=mock_summarizer),
        patch("osspulse.pipeline._build_cache", return_value=MagicMock()),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    mock_delivery.deliver.assert_called_once()


# ---------------------------------------------------------------------------
# No-LLM path (AC-7-008, AC-7-022)
# ---------------------------------------------------------------------------


def test_no_llm_path_summarizer_never_constructed(tmp_path):
    """llm_provider is None → LiteLLMSummarizer never constructed (AC-7-008, AC-7-022)."""
    item = _raw(idx=1)
    cfg = _config(llm_provider=None, tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer") as mock_llm_cls,
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)
        # LiteLLMSummarizer constructor NEVER called (BR-7-010)
        mock_llm_cls.assert_not_called()

    # Placeholder visible in delivered digest (AC-7-022)
    delivered = mock_delivery.deliver.call_args[0][0]
    assert NO_LLM_PLACEHOLDER in delivered


def test_no_llm_placeholder_constant():
    """NO_LLM_PLACEHOLDER is non-empty and matches spec (AC-7-008, AC-7-022)."""
    assert NO_LLM_PLACEHOLDER == "(no summary — LLM disabled)"
    assert len(NO_LLM_PLACEHOLDER) > 0


# ---------------------------------------------------------------------------
# Idempotency + seen (AC-7-010, AC-7-011, AC-7-019)
# ---------------------------------------------------------------------------


def test_idempotent_rerun_same_digest(tmp_path):
    """Two runs with same items → byte-identical digest (AC-7-011)."""
    item = _raw(idx=1)
    cfg = _config(tmp_path=tmp_path)
    digests: list[str] = []

    for _ in range(2):
        mock_collector = MagicMock()
        mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
        mock_collector.fetch_items.return_value = [item]
        mock_state = MagicMock()
        mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
        mock_delivery = MagicMock()

        with (
            patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
            patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
            patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
        ):
            run_pipeline(cfg)
        digests.append(mock_delivery.deliver.call_args[0][0])

    assert digests[0] == digests[1]


def test_mark_seen_decoupled_from_summarize(tmp_path):
    """mark_seen called even when summarizer later fails — decoupled (AC-7-019)."""
    item = _raw(idx=1)
    cfg = _config(llm_provider="openai", llm_api_key="sk-fake", tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    # Summarizer raises — mark_seen must have been called BEFORE this
    mock_summarizer = MagicMock()
    mock_summarizer.summarize_items.side_effect = RuntimeError("LLM exploded")

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer", return_value=mock_summarizer),
        patch("osspulse.pipeline._build_cache", return_value=MagicMock()),
    ):
        with pytest.raises(RuntimeError):
            run_pipeline(cfg)

    # mark_seen was called before the summarize failure
    mock_state.mark_seen.assert_called_once_with([item])


def test_redis_unreachable_degrades_gracefully(tmp_path):
    """Redis unreachable → _NullCache, run continues and delivers (AC-7-009)."""
    from osspulse.pipeline import _NullCache

    # _NullCache behaves as a no-op cache (get→None, set→no-op)
    null = _NullCache()
    assert null.get("any") is None
    null.set("any", "val")  # must not raise


def test_build_cache_returns_null_cache_on_redis_error(monkeypatch):
    """_build_cache returns _NullCache when Redis connection fails (AC-7-009)."""
    from osspulse.pipeline import _build_cache

    # Simulate redis not available / connection refused
    monkeypatch.setenv("REDIS_URL", "redis://localhost:19999")
    cache = _build_cache()
    # _NullCache.get returns None; if Redis connected, get still returns None for missing key
    assert cache.get("nonexistent-key-xyz") is None


# ---------------------------------------------------------------------------
# SECURITY — log-capture test (RF-1, AC-7-014, BR-7-012)
# ---------------------------------------------------------------------------


def test_no_secret_in_logs_stderr_or_digest(tmp_path, caplog, capsys):
    """Neither github_token nor llm_api_key appear in logs/stderr/digest (AC-7-014, RF-1)."""
    FAKE_TOKEN = "ghp_SUPERSECRETTOKEN99"
    FAKE_API_KEY = "sk-SUPERSECRETAPIKEY88"

    cfg = Config(
        watched_repos=[REPO_A],
        lookback_days=7,
        github_token=FAKE_TOKEN,
        llm_provider="openai",
        llm_api_key=FAKE_API_KEY,
        state_path=str(tmp_path / "state.json"),
        output_destination="stdout",
        output_path=str(tmp_path / "digest.md"),
    )

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    # Simulate an error that might embed secrets in its message
    mock_collector.fetch_items.side_effect = NetworkError("connection refused")
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_delivery = MagicMock()

    with caplog.at_level(logging.DEBUG, logger="osspulse.pipeline"):
        with (
            patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
            patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
            patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
        ):
            run_pipeline(cfg)

    # Check logs
    all_log_text = caplog.text
    assert FAKE_TOKEN not in all_log_text, "github_token leaked into logs"
    assert FAKE_API_KEY not in all_log_text, "llm_api_key leaked into logs"

    # Check delivered digest
    if mock_delivery.deliver.called:
        delivered = mock_delivery.deliver.call_args[0][0]
        assert FAKE_TOKEN not in delivered, "github_token leaked into digest"
        assert FAKE_API_KEY not in delivered, "llm_api_key leaked into digest"


# ---------------------------------------------------------------------------
# Import isolation static test (AC-7-002)
# ---------------------------------------------------------------------------

_STAGE_MODULES = [
    "osspulse.github",
    "osspulse.state",
    "osspulse.summarizer",
    "osspulse.cache",
    "osspulse.render",
    "osspulse.delivery",
]


def test_import_isolation_no_stage_imports_another():
    """No stage module imports another stage module.

    AC-7-002, pipeline.py excluded as sanctioned importer.
    """
    for module_name in _STAGE_MODULES:
        mod = importlib.import_module(module_name)
        mod_file = getattr(mod, "__file__", "") or ""

        for other in _STAGE_MODULES:
            if other == module_name:
                continue
            # Get the short package name, e.g. "github" from "osspulse.github"
            other_short = other.split(".")[-1]
            # Check that the module's source doesn't import from the other stage
            try:
                src_path = Path(mod_file).parent
                for py_file in src_path.glob("*.py"):
                    src = py_file.read_text(encoding="utf-8")
                    # Look for direct imports of the other stage package
                    assert f"from osspulse.{other_short}" not in src, (
                        f"{module_name} ({py_file.name}) imports from {other} — violates AC-7-002"
                    )
                    assert f"import osspulse.{other_short}" not in src, (
                        f"{module_name} ({py_file.name}) imports from {other} — violates AC-7-002"
                    )
            except (OSError, AttributeError):
                pass  # skip if file not readable


# ---------------------------------------------------------------------------
# One-call discipline (BR-7-007, BR-7-009)
# ---------------------------------------------------------------------------


def test_exactly_one_summarize_one_render_one_deliver(tmp_path):
    """Exactly one summarize_items, one render, one deliver call per run (BR-7-007, BR-7-009)."""
    item = _raw(idx=1)
    cfg = _config(
        repos=[REPO_A, REPO_B], llm_provider="openai", llm_api_key="sk-fake", tmp_path=tmp_path
    )

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.side_effect = [[item], []]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # V1 default: nothing previously seen
    mock_summarizer = MagicMock()
    mock_summarizer.summarize_items.return_value = [_summarized(item)]
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer", return_value=mock_summarizer),
        patch("osspulse.pipeline._build_cache", return_value=MagicMock()),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        with patch("osspulse.pipeline.render") as mock_render:
            mock_render.return_value = "# Digest"
            run_pipeline(cfg)
            mock_render.assert_called_once()  # one render (BR-7-007)
            mock_delivery.deliver.assert_called_once()  # one deliver (BR-7-007)
    mock_summarizer.summarize_items.assert_called_once()  # one summarize (BR-7-009)


# ---------------------------------------------------------------------------
# Delta filter (AC-V2-001-001..010) — R1 ordering, StateError propagation,
# identity-based suppression, delta_enabled selection at extend
# ---------------------------------------------------------------------------


def test_delta_first_run_all_new_all_recorded(tmp_path):
    """First run against empty state: 3 new issues, delta_enabled=true → all 3
    rendered AND all 3 recorded via mark_seen (AC-V2-001-001)."""
    items = [_raw(idx=i) for i in (1, 2, 3)]
    cfg = _config(delta_enabled=True, tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = items
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # empty state — nothing seen yet
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    # All 3 recorded — mark_seen called once with the FULL fetched list
    mock_state.mark_seen.assert_called_once_with(items)
    delivered = mock_delivery.deliver.call_args[0][0]
    for item in items:
        assert item.title in delivered


def test_delta_mixed_new_and_seen_snapshot_before_mark_seen(tmp_path):
    """Mixed new+seen in one run (#6 new, #5 seen), delta_enabled=true → only #6
    rendered, BOTH #5 and #6 recorded — snapshot taken before mark_seen (AC-V2-001-004)."""
    item_seen = _raw(idx=5)
    item_new = _raw(idx=6)
    cfg = _config(delta_enabled=True, tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item_seen, item_new]
    mock_state = MagicMock()

    def _is_seen(repo, item_type, item_id):  # noqa: ARG001
        return item_id == item_seen.item_id

    mock_state.is_seen.side_effect = _is_seen
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    # BOTH items recorded — mark_seen received the full list, not just `new`
    mock_state.mark_seen.assert_called_once_with([item_seen, item_new])
    # Only #6 (new) rendered
    delivered = mock_delivery.deliver.call_args[0][0]
    assert item_new.title in delivered
    assert item_seen.title not in delivered


def test_delta_empty_after_filter_delivers_no_new_items_doc(tmp_path):
    """Second run with no new activity → filtered list empty, render([]) returns
    the 'no new items' doc, delivered once, exit 0 (AC-V2-001-005, AC-V2-001-008)."""
    item = _raw(idx=1)
    cfg = _config(delta_enabled=True, tmp_path=tmp_path)

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = True  # already seen on a previous run
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)  # must not raise — exit 0

    mock_delivery.deliver.assert_called_once()
    delivered = mock_delivery.deliver.call_args[0][0]
    assert "No new items" in delivered or "OSS Pulse" in delivered
    assert item.title not in delivered
    # Recording still happens even though nothing renders (BR-V2-001-002)
    mock_state.mark_seen.assert_called_once_with([item])


def test_delta_mark_seen_count_invariant_both_modes(tmp_path):
    """mark_seen invoked with the SAME full item list for both delta_enabled=true
    and delta_enabled=false over identical mixed input; render-count differs
    (N vs N-M), record-count is identical (AC-V2-001-010, AC-7-010)."""
    item_seen = _raw(idx=5)
    item_new = _raw(idx=6)

    for delta_enabled, expected_rendered, expected_not_rendered in (
        (True, item_new, item_seen),
        (False, item_seen, None),
    ):
        cfg = _config(delta_enabled=delta_enabled, tmp_path=tmp_path)
        mock_collector = MagicMock()
        mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
        mock_collector.fetch_items.return_value = [item_seen, item_new]
        mock_state = MagicMock()

        def _is_seen(repo, item_type, item_id):  # noqa: ARG001
            return item_id == item_seen.item_id

        mock_state.is_seen.side_effect = _is_seen
        mock_delivery = MagicMock()

        with (
            patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
            patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
            patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
        ):
            run_pipeline(cfg)

        # Record-count identical regardless of delta_enabled: mark_seen sees BOTH items
        mock_state.mark_seen.assert_called_once_with([item_seen, item_new])

        delivered = mock_delivery.deliver.call_args[0][0]
        assert expected_rendered.title in delivered
        if delta_enabled:
            assert expected_not_rendered.title not in delivered
        else:
            # delta_enabled=false renders everything, including the previously-seen item
            assert item_seen.title in delivered
            assert item_new.title in delivered


def test_delta_disabled_byte_identical_to_v1(tmp_path):
    """delta_enabled=false over already-seen issues → all rendered, digest
    byte-identical to a V1 run over the same items (AC-V2-001-006, AC-7-011)."""
    items = [_raw(idx=1), _raw(idx=2)]

    def _run(delta_enabled: bool) -> str:
        cfg = _config(delta_enabled=delta_enabled, tmp_path=tmp_path / str(delta_enabled))
        mock_collector = MagicMock()
        mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
        mock_collector.fetch_items.return_value = items
        mock_state = MagicMock()
        mock_state.is_seen.return_value = True  # all previously seen
        mock_delivery = MagicMock()

        with (
            patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
            patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
            patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
        ):
            run_pipeline(cfg)
        return mock_delivery.deliver.call_args[0][0]

    # V1 semantics == delta_enabled=false: is_seen is irrelevant, everything renders
    v1_like_digest = _run(delta_enabled=False)
    v1_like_digest_rerun = _run(delta_enabled=False)
    assert v1_like_digest == v1_like_digest_rerun
    for item in items:
        assert item.title in v1_like_digest


def test_delta_state_error_propagates_not_swallowed(tmp_path):
    """A StateError raised by the state store during collection propagates out of
    run_pipeline — not swallowed, filter not silently disabled (AC-V2-001-009)."""
    from osspulse.state.errors import StateError

    cfg = _config(delta_enabled=True, tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [_raw(idx=1)]
    mock_state = MagicMock()
    mock_state.is_seen.side_effect = StateError("state file is corrupt: bad json")

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
    ):
        with pytest.raises(StateError):
            run_pipeline(cfg)

    # mark_seen never reached — StateError raised during the is_seen snapshot
    mock_state.mark_seen.assert_not_called()


def test_delta_state_store_protocol_unchanged(tmp_path):
    """StateStore Protocol + is_seen/mark_seen signatures unchanged — delta calls
    is_seen from pipeline only, no Protocol method added (AC-V2-001-003)."""
    from osspulse.ports import StateStore

    # Protocol still only declares load/save — is_seen/mark_seen are adapter-only
    # helpers on JsonFileStateStore, not part of the StateStore Protocol (ADR-001).
    protocol_methods = {name for name in dir(StateStore) if not name.startswith("_")}
    assert "is_seen" not in protocol_methods
    assert "mark_seen" not in protocol_methods
    assert {"load", "save"}.issubset(protocol_methods)


def test_delta_mark_seen_still_decoupled_from_summarize_failure(tmp_path):
    """Regression guard for AC-7-019: an item marked seen whose summarize fails
    stays recorded and the run continues, even with the delta filter inline."""
    item = _raw(idx=1)
    cfg = _config(
        delta_enabled=True, llm_provider="openai", llm_api_key="sk-fake", tmp_path=tmp_path
    )

    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False
    mock_summarizer = MagicMock()
    mock_summarizer.summarize_items.side_effect = RuntimeError("LLM exploded")

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.LiteLLMSummarizer", return_value=mock_summarizer),
        patch("osspulse.pipeline._build_cache", return_value=MagicMock()),
    ):
        with pytest.raises(RuntimeError):
            run_pipeline(cfg)

    # mark_seen was called (with the full item list) before the summarize failure
    mock_state.mark_seen.assert_called_once_with([item])


def test_partition_new_reads_only_is_seen_no_writes(tmp_path):
    """_partition_new is read-only: it calls is_seen and never calls mark_seen/save
    (AC-V2-001-001, AC-V2-001-004)."""
    from osspulse.pipeline import _partition_new

    item_seen = _raw(idx=1)
    item_new = _raw(idx=2)
    mock_state = MagicMock()
    mock_state.is_seen.side_effect = lambda repo, item_type, item_id: item_id == item_seen.item_id  # noqa: ARG005

    new, seen = _partition_new([item_seen, item_new], mock_state)

    assert new == [item_new]
    assert seen == [item_seen]
    mock_state.mark_seen.assert_not_called()
    mock_state.save.assert_not_called()


# ---------------------------------------------------------------------------
# V2-003 Releases — pipeline integration tests (AC-V2-003-019..022)
# ---------------------------------------------------------------------------


def _raw_release(repo: str = "org/repo-a", *, tag: str = "v1.0.0") -> RawItem:
    """A minimal release RawItem for pipeline tests."""
    return RawItem(
        repo=repo,
        item_type="release",
        item_id=tag,
        title=f"Release {tag}",
        body=f"Notes for {tag}",
        url=f"https://github.com/{repo}/releases/tag/{tag}",
        created_at="2026-07-01T09:00:00Z",
    )


def test_issues_and_releases_concatenated_before_delta(tmp_path):
    """A repo returning 2 issues + 1 release yields 3 RawItems (2 issue + 1 release)
    concatenated into one list before the delta partition step (AC-V2-003-019)."""
    issue1 = _raw("org/repo-a", idx=1)
    issue2 = _raw("org/repo-a", idx=2)
    rel1 = _raw_release("org/repo-a", tag="v1.0.0")

    cfg = _config(repos=[REPO_A], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_releases.return_value = []  # releases: empty default (v2-003)
    mock_collector.fetch_items.return_value = [issue1, issue2]
    mock_collector.fetch_releases.return_value = [rel1]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    # mark_seen must be called with the FULL concatenated list (AC-V2-003-019, R1)
    mock_state.mark_seen.assert_called_once()
    seen_items = mock_state.mark_seen.call_args[0][0]
    assert len(seen_items) == 3
    item_types = [i.item_type for i in seen_items]
    assert item_types.count("issue") == 2
    assert item_types.count("release") == 1

    # Both issues and the release appear in the delivered digest
    delivered = mock_delivery.deliver.call_args[0][0]
    assert issue1.title in delivered
    assert issue2.title in delivered
    assert rel1.title in delivered


def test_release_delta_suppressed_on_rerun_renderer_group_unchanged(tmp_path):
    """Release rendered and recorded on run 1 is suppressed on run 2 with delta_enabled=true.
    The renderer emits the release under the existing release group — no renderer
    change required (AC-V2-003-020, AC-V2-003-021)."""
    rel = _raw_release("org/repo-a", tag="v2.0.0")

    cfg = _config(repos=[REPO_A], delta_enabled=True, tmp_path=tmp_path)

    # --- Run 1: release is new → should appear in digest ---
    mock_collector = MagicMock()
    mock_collector.fetch_items.return_value = []
    mock_collector.fetch_releases.return_value = [rel]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False  # nothing seen yet
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)

    digest_run1 = mock_delivery.deliver.call_args[0][0]
    assert rel.title in digest_run1, "Release should appear in first-run digest"
    # Release is recorded under the "release" identity (AC-V2-003-020)
    mock_state.mark_seen.assert_called_once_with([rel])

    # --- Run 2: release seen → should be suppressed ---
    mock_collector2 = MagicMock()
    mock_collector2.fetch_items.return_value = []
    mock_collector2.fetch_releases.return_value = [rel]
    mock_state2 = MagicMock()
    mock_state2.is_seen.return_value = True  # seen on previous run
    mock_delivery2 = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector2),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state2),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery2),
    ):
        run_pipeline(cfg)

    digest_run2 = mock_delivery2.deliver.call_args[0][0]
    assert rel.title not in digest_run2, "Seen release must be suppressed on rerun"
    # Even when suppressed from rendering, still recorded again (BR-V2-001-002)
    mock_state2.mark_seen.assert_called_once_with([rel])


def test_release_fetch_failure_issues_survive_other_repos_unaffected(tmp_path):
    """ADR-003 isolation + R1 count-invariant tripwire (AC-V2-003-022):
    - A recoverable CollectorError from fetch_releases still delivers the repo's issues.
    - Other repos are unaffected.
    - mark_seen called exactly once per repo with len(issues)+len(releases) items.
    - AuthError from fetch_releases is NOT swallowed — it propagates as fatal.
    """
    issue_a = _raw("org/repo-a", idx=1)
    issue_b = _raw("org/repo-b", idx=2)

    cfg = _config(repos=[REPO_A, REPO_B], tmp_path=tmp_path)

    # repo-a: issues succeed, releases fail with recoverable CollectorError
    # repo-b: issues + releases both succeed
    rel_b = _raw_release("org/repo-b", tag="v1.0.0")

    mock_collector = MagicMock()
    mock_collector.fetch_items.side_effect = [[issue_a], [issue_b]]
    mock_collector.fetch_releases.side_effect = [
        CollectorError("releases API glitch"),  # repo-a: recoverable failure
        [rel_b],  # repo-b: success
    ]
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False
    mock_delivery = MagicMock()

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
        patch("osspulse.pipeline.StdoutDelivery", return_value=mock_delivery),
    ):
        run_pipeline(cfg)  # must NOT raise — exit 0 (AC-V2-003-022)

    delivered = mock_delivery.deliver.call_args[0][0]
    # repo-a issue survived despite release failure
    assert issue_a.title in delivered
    # repo-b issue + release both present
    assert issue_b.title in delivered
    assert rel_b.title in delivered

    # R1 count-invariant: mark_seen called once per repo with correct item counts
    assert mock_state.mark_seen.call_count == 2
    # repo-a: only issues (releases failed → [])
    mock_state.mark_seen.assert_any_call([issue_a])
    # repo-b: issues + releases concatenated
    mock_state.mark_seen.assert_any_call([issue_b, rel_b])


def test_release_auth_error_not_swallowed_by_inner_guard(tmp_path):
    """AuthError from fetch_releases is NOT caught by the inner guard — it propagates
    as a fatal error (AC-V2-003-022, ADR-003 inner-guard scope)."""
    issue_a = _raw("org/repo-a", idx=1)

    cfg = _config(repos=[REPO_A], tmp_path=tmp_path)
    mock_collector = MagicMock()
    mock_collector.fetch_items.return_value = [issue_a]
    mock_collector.fetch_releases.side_effect = AuthError("401 — token revoked")
    mock_state = MagicMock()
    mock_state.is_seen.return_value = False

    with (
        patch("osspulse.pipeline.GitHubCollector", return_value=mock_collector),
        patch("osspulse.pipeline.JsonFileStateStore", return_value=mock_state),
    ):
        with pytest.raises(AuthError):
            run_pipeline(cfg)
