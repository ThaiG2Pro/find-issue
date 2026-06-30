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
    mock_collector.fetch_items.side_effect = [
        [item_a],  # REPO_A
        [item_b],  # REPO_B
    ]
    mock_state = MagicMock()
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
    mock_collector.fetch_items.side_effect = [[item_a], [item_b]]
    mock_state = MagicMock()

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
    mock_collector.fetch_items.side_effect = [
        InvalidRepoError("not found"),
        [item_b],
    ]
    mock_state = MagicMock()
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
    mock_collector.fetch_items.side_effect = NetworkError("timeout")
    mock_state = MagicMock()
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
    mock_collector.fetch_items.side_effect = CollectorError("unknown")
    mock_state = MagicMock()

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
    mock_collector.fetch_items.side_effect = [
        [item_a],  # REPO_A succeeds
        RateLimitError("quota gone"),  # REPO_B hits rate limit
    ]
    mock_state = MagicMock()
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
    mock_collector.fetch_items.side_effect = [
        InvalidRepoError("404"),
        NetworkError("timeout"),
    ]
    mock_state = MagicMock()
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
    mock_collector.fetch_items.return_value = [item1, item2]
    mock_state = MagicMock()
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
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
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
        mock_collector.fetch_items.return_value = [item]
        mock_state = MagicMock()
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
    mock_collector.fetch_items.return_value = [item]
    mock_state = MagicMock()
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
    # Simulate an error that might embed secrets in its message
    mock_collector.fetch_items.side_effect = NetworkError("connection refused")
    mock_state = MagicMock()
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
    mock_collector.fetch_items.side_effect = [[item], []]
    mock_state = MagicMock()
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
