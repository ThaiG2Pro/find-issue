"""Pipeline orchestrator — wires all five V1 stages (ADR-001..006, AC-7-001..022).

This is the ONLY module permitted to import multiple stage modules (AC-7-002).
No stage module (github, state, summarizer, cache, render, delivery) imports another.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from osspulse.cache.redis_cache import RedisSummaryCache
from osspulse.delivery.file_delivery import FileDelivery
from osspulse.delivery.stdout_delivery import StdoutDelivery
from osspulse.github.client import GitHubCollector
from osspulse.github.errors import (
    AuthError,
    CollectorError,
    InvalidRepoError,
    NetworkError,
    RateLimitError,
)
from osspulse.models import Config, RawItem, SummarizedItem
from osspulse.render.renderer import render
from osspulse.state.json_store import JsonFileStateStore
from osspulse.summarizer.client import LiteLLMSummarizer
from osspulse.summarizer.config import SummarizerConfig

if TYPE_CHECKING:
    from osspulse.ports import SummaryCache

# ---------------------------------------------------------------------------
# Constants (ADR-006, AC-7-008/022)
# ---------------------------------------------------------------------------

NO_LLM_PLACEHOLDER = "(no summary — LLM disabled)"

# ---------------------------------------------------------------------------
# LLM model defaults (ADR-002, resolves GAP-001 — SummarizerConfig.model is REQUIRED)
# Keys are provider names as they appear in config.toml [llm] provider =
# ---------------------------------------------------------------------------

_PROVIDER_MODEL: dict[str, str] = {
    "openai": "openai/gpt-4o-mini",
    "ollama": "ollama/llama3",
    "anthropic": "anthropic/claude-3-haiku-20240307",
    "groq": "groq/llama3-8b-8192",
}

logger = logging.getLogger("osspulse.pipeline")


# ---------------------------------------------------------------------------
# Helpers — ADR-002
# ---------------------------------------------------------------------------


def _model_for(provider: str) -> str:
    """Return the LiteLLM model string for *provider* (ADR-002, AC-7-007).

    Uses a known-good default per provider; falls back to ``"{provider}/{provider}"``
    so the pipeline never raises on an unknown provider string.
    """
    return _PROVIDER_MODEL.get(provider.lower(), f"{provider}/{provider}")


class _NullCache:
    """No-op SummaryCache used when Redis is unreachable (ADR-002, AC-7-009).

    get → None (miss), set → no-op. Satisfies the SummaryCache Protocol structurally.
    """

    def get(self, key: str) -> str | None:  # noqa: ARG002
        return None

    def set(self, key: str, value: str) -> None:  # noqa: ARG002
        pass


def _build_cache() -> SummaryCache:
    """Construct a Redis summary cache best-effort (ADR-002, AC-7-009).

    Reads ``REDIS_URL`` from the environment (default ``redis://localhost:6379``).
    On ANY error (import, connection, config) → returns ``_NullCache`` so the
    run degrades to re-summarize rather than crashing.
    """
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        import redis as redis_lib  # lazy — not required if Redis is unavailable

        client = redis_lib.Redis.from_url(url)
        # Ping to surface a connection error eagerly; caught below.
        client.ping()
        return RedisSummaryCache(client)
    except Exception as exc:  # noqa: BLE001 — intentional: any Redis failure → null cache
        logger.warning("Redis cache unavailable (%s); running without cache", type(exc).__name__)
        return _NullCache()


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------


def _collect_all(
    config: Config,
    collector: GitHubCollector,
    state: JsonFileStateStore,
) -> tuple[list[RawItem], dict[str, int]]:
    """Collect issues across all watched repos with per-repo failure isolation (ADR-003).

    Returns (all_items, stats) where stats = {repos, collected, skipped}.
    mark_seen is called per repo at collect time, decoupled from summarization (AC-7-019).

    Exception → action (ADR-003, most-specific-first — ORDER IS LOAD-BEARING):
      AuthError        → re-raise (fatal; all repos share one token)      AC-7-005
      RateLimitError   → break loop (deliver partial results)              AC-7-017
      Other CollectorError → log WARN + skip repo + continue               AC-7-004
    """
    all_items: list[RawItem] = []
    stats = {"repos": len(config.watched_repos), "collected": 0, "skipped": 0}

    for repo in config.watched_repos:
        repo_name = repo.full_name
        try:
            items = collector.fetch_items(repo_name, config.lookback_days)
            # mark_seen BEFORE summarize — decoupled (AC-7-019); empty list is safe no-op
            state.mark_seen(items)
            all_items.extend(items)
            stats["collected"] += len(items)
            # AC-7-015: exactly one outcome log line per repo, no secret
            logger.info("collected %d item(s) from %s", len(items), repo_name)

        except AuthError:
            # Fatal — shared token is invalid; no point continuing (AC-7-005, BR-7-002)
            # Log the error CLASS only, never the raw exception which may embed a tokened URL
            logger.warning("auth failure for %s — aborting run", repo_name)
            raise  # re-raised; cli.run catches AuthError → exit 1

        except RateLimitError:
            # Terminal — collector's backoff exhausted; deliver what we have (AC-7-017, BR-7-008)
            stats["skipped"] += 1
            logger.warning(
                "rate limit reached at %s — stopping collection, delivering partial results",
                repo_name,
            )
            break  # exit the repo loop; proceed to summarize/render/deliver

        except (InvalidRepoError, NetworkError, CollectorError) as exc:
            # Recoverable per-repo failure — log type + repo, skip, continue (AC-7-004, BR-7-001)
            # NEVER log the raw exception object (ADR-004, RF-1); log class name only
            stats["skipped"] += 1
            logger.warning("skipped %s: %s", repo_name, type(exc).__name__)

    return all_items, stats


def _summarize(config: Config, all_items: list[RawItem]) -> list[SummarizedItem]:
    """Summarize items — LLM or no-LLM path (ADR-006, AC-7-007/008/018/022).

    No-LLM path (config.llm_provider is None):
        Wraps each RawItem as SummarizedItem(summary=NO_LLM_PLACEHOLDER) WITHOUT
        constructing or calling LiteLLMSummarizer (BR-7-010, ADR-006).

    LLM path:
        Constructs LiteLLMSummarizer once, calls summarize_items EXACTLY ONCE (BR-7-009).
        Returns only survivors (fewer than collected is valid — AC-7-018).
    """
    if config.llm_provider is None:
        # ADR-006: no-LLM path — placeholder is non-empty so renderer emits it (AC-7-022)
        return [SummarizedItem(raw=item, summary=NO_LLM_PLACEHOLDER) for item in all_items]

    # LLM path — construct once per run (token to ctor only, never stored — BR-7-006/RF-1)
    summarizer = LiteLLMSummarizer(
        provider=config.llm_provider,
        api_key=config.llm_api_key,
        cache=_build_cache(),
        config=SummarizerConfig(model=_model_for(config.llm_provider)),  # ADR-002: no default
    )
    # ONE batch call — not per-item (BR-7-009, AC-7-007)
    return summarizer.summarize_items(all_items)


# ---------------------------------------------------------------------------
# Orchestrator — replaces NotImplementedError stub (AC-7-003)
# ---------------------------------------------------------------------------


def run_pipeline(config: Config) -> None:
    """Wire all five V1 stages end-to-end (AC-7-001/002/003/016, ADR-001).

    Adapters are locals — the github_token and llm_api_key are passed to their
    respective adapter constructors only and never stored on any shared object (BR-7-006, RF-1).

    Exit semantics delegated to cli.run via exceptions:
        AuthError / StateError / DeliveryError → caught in cli.run → exit 1
        All other flows → return normally → exit 0
    """
    # --- Construct adapters (token/key to ctor only) ---
    collector = GitHubCollector(config.github_token)
    state = JsonFileStateStore(config.state_path)

    # --- Collect (per-repo isolation) ---
    all_items, stats = _collect_all(config, collector, state)

    # --- Summarize (LLM or no-LLM) ---
    summarized = _summarize(config, all_items)
    stats["summarized"] = len(summarized)

    # --- Render ONCE (empty list → valid no-new-items doc, AC-7-006) ---
    digest = render(summarized, lookback_days=config.lookback_days)

    # --- Deliver ONCE (BR-7-007) ---
    if config.output_destination == "stdout":
        delivery = StdoutDelivery()
    else:
        delivery = FileDelivery(config.output_path)
    delivery.deliver(digest)

    # --- Run-summary log (AC-7-021); no secret in line ---
    logger.info(
        "run complete — repos: %d, collected: %d, summarized: %d, skipped: %d",
        stats["repos"],
        stats["collected"],
        stats.get("summarized", 0),
        stats["skipped"],
    )
