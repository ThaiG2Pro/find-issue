"""Pipeline orchestrator — wires all five V1 stages (ADR-001..006, AC-7-001..022).

This is the ONLY module permitted to import multiple stage modules (AC-7-002).
No stage module (github, state, summarizer, cache, render, delivery) imports another.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import litellm

from osspulse.cache.etag_store import JsonFileETagStore
from osspulse.cache.redis_cache import RedisSummaryCache
from osspulse.delivery.discord_delivery import DiscordDelivery
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
from osspulse.ports import _NullConditionalCache
from osspulse.render.renderer import render
from osspulse.state.json_store import JsonFileStateStore
from osspulse.summarizer.client import LiteLLMSummarizer
from osspulse.summarizer.config import SummarizerConfig

if TYPE_CHECKING:
    from osspulse.ports import ConditionalCache, SeenTracker, SummaryCache

# ---------------------------------------------------------------------------
# Suppress LiteLLM's verbose stderr banners (Give Feedback URL, LiteLLM.Info
# lines) that are printed on every error via print() — not the Python logging
# system. Setting this flag to True disables those print() calls without
# affecting actual error handling logic or our own logger output.
# See: litellm/litellm_core_utils/exception_mapping_utils.py
# ---------------------------------------------------------------------------
litellm.suppress_debug_info = True

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


def _build_etag_cache(config: Config) -> ConditionalCache:
    """Construct a JsonFileETagStore best-effort, gated by two flags (AC-V2-007-019/022/023).

    Gate: ``etag_cache_enabled AND delta_enabled`` (ADR-002).
    - If either flag is False → return ``_NullConditionalCache`` immediately (no file
      written, no conditional headers sent — AC-V2-007-023).
    - If both True → construct ``JsonFileETagStore(config.etag_cache_path)``; any
      construction/load error → WARN + return ``_NullConditionalCache`` (AC-V2-007-019).
    Mirrors ``_build_cache`` for the Redis summary cache.
    """
    if not (config.etag_cache_enabled and config.delta_enabled):
        # AC-V2-007-023: either flag False → unconditional fetches; etags.json untouched
        return _NullConditionalCache()

    try:
        return JsonFileETagStore(config.etag_cache_path)
    except Exception as exc:  # noqa: BLE001 — intentional: any failure → null cache
        logger.warning(
            "ETag cache unavailable (%s); running without conditional requests",
            type(exc).__name__,
        )
        return _NullConditionalCache()


def _build_store(config: Config) -> SeenTracker:
    """Construct the state backend based on env-var presence (ADR-001, AC-V3-003-004/005).

    Selection rule:
    - Both ``UPSTASH_REDIS_REST_URL`` AND ``UPSTASH_REDIS_REST_TOKEN`` non-empty
      → ``UpstashStateStore(url, token)`` (HTTP REST, fail-loud semantics).
    - Either absent/empty → ``JsonFileStateStore(config.state_path)`` (unchanged behavior).

    DELIBERATELY inverts ``_build_cache``/``_build_etag_cache``:
    - Caches swallow errors → null-object (best-effort).
    - State fails loud → ``StateError`` (idempotency source of truth, ADR-004).
    No try/except here for runtime Upstash errors — they propagate out as ``StateError``.
    Construction-time fallback (env-absent path) is the ONLY fallback (AC-V3-003-005).
    """
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if url and token:
        # Both env vars non-empty → use Upstash backend (AC-V3-003-004).
        # Import here (lazy) so the package is only required when Upstash is configured.
        from osspulse.state.upstash_store import UpstashStateStore  # noqa: PLC0415

        logger.debug("state backend: Upstash Redis")
        return UpstashStateStore(url=url, token=token)

    # Either absent/empty → local JSON file (AC-V3-003-005).
    logger.debug("state backend: JsonFileStateStore (%s)", config.state_path)
    return JsonFileStateStore(config.state_path)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------


def _partition_new(items: list[RawItem], state: SeenTracker) -> tuple[list[RawItem], list[RawItem]]:
    """Split *items* into (new, seen) using a pre-``mark_seen`` snapshot (ADR-001).

    Reads ``state.is_seen(repo, item_type, item_id)`` only — no writes. MUST be called
    BEFORE ``state.mark_seen(items)`` in ``_collect_all``: ``is_seen``/``mark_seen`` share
    the same in-memory cache, so calling this after ``mark_seen`` would read the mutated
    cache and report everything as seen (R1 bug, AC-V2-001-004/010).

    No content hashing — identity is ``repo+item_type+item_id`` only (BR-V2-001-004,
    EC-005); an edited-but-same-id item is still "seen".
    """
    new: list[RawItem] = []
    seen: list[RawItem] = []
    for item in items:
        if state.is_seen(item.repo, item.item_type, item.item_id):
            seen.append(item)
        else:
            new.append(item)
    return new, seen


def _collect_all(
    config: Config,
    collector: GitHubCollector,
    state: SeenTracker,
) -> tuple[list[RawItem], dict[str, int]]:
    """Collect issues across all watched repos with per-repo failure isolation (ADR-003).

    Returns (all_items, stats) where stats = {repos, collected, skipped, seen, new}.
    mark_seen is called per repo at collect time, decoupled from summarization (AC-7-019).
    The delta filter (_partition_new) reads the pre-mark_seen snapshot so first-seen-this-run
    items still render (AC-V2-001-004); mark_seen always records the FULL fetched list,
    never just `new` (BR-V2-001-002, AC-V2-001-010).

    Exception → action (ADR-003, most-specific-first — ORDER IS LOAD-BEARING):
      AuthError        → re-raise (fatal; all repos share one token)      AC-7-005
      RateLimitError   → break loop (deliver partial results)              AC-7-017
      Other CollectorError → log WARN + skip repo + continue               AC-7-004

    NOTE (ADR-003, AC-V2-001-009): no try/except is added around `is_seen`/`_partition_new`
    or `state.load()` — a `StateError` from a corrupt/unreadable state file MUST propagate
    out of this function (it is not a `CollectorError` subclass, so the except arms below do
    not catch it) all the way to the CLI, which already maps `StateError → Error: <msg>` exit 1.
    A defensive catch here would silently disable the delta filter — the exact anti-pattern
    AC-V2-001-009 forbids.
    """
    all_items: list[RawItem] = []
    stats = {"repos": len(config.watched_repos), "collected": 0, "skipped": 0, "seen": 0, "new": 0}

    for repo in config.watched_repos:
        repo_name = repo.full_name
        try:
            issues = collector.fetch_items(repo_name, config.lookback_days)
            # ADR-003 (AC-V2-003-022): inner guard wraps ONLY fetch_releases.
            # Issues already collected survive a release-fetch failure.
            # AuthError + terminal RateLimitError are deliberately NOT caught here —
            # they must propagate to the outer arms above so the fatal/partial-deliver
            # semantics (AC-7-005 / AC-7-017) are preserved.
            try:
                releases = collector.fetch_releases(repo_name, config.lookback_days)
            except (InvalidRepoError, NetworkError) as exc:
                # Recoverable per-release failures — issues already collected survive.
                # CollectorError base NOT listed here because AuthError and RateLimitError
                # are subclasses of CollectorError and must NOT be swallowed:
                #   AuthError → outer arm re-raises as fatal (AC-7-005)
                #   RateLimitError → outer arm breaks + partial-deliver (AC-7-017)
                logger.warning("skipped releases for %s: %s", repo_name, type(exc).__name__)
                releases = []
            except CollectorError as exc:
                # Any other concrete CollectorError subclass (not Auth/RateLimit) is
                # treated as recoverable. Auth and RateLimit are caught by outer arms.
                if isinstance(exc, (AuthError, RateLimitError)):
                    raise  # propagate fatal / terminal errors to outer arms
                logger.warning("skipped releases for %s: %s", repo_name, type(exc).__name__)
                releases = []
            # AC-V2-006: inner guard wraps ONLY fetch_discussions — mirrors the release guard.
            # Issues and releases already collected survive a discussion-fetch failure.
            # AuthError + terminal RateLimitError are deliberately NOT caught here —
            # they must propagate to the outer arms so fatal/partial-deliver semantics
            # (AC-7-005 / AC-7-017) are preserved (v2-003 memory lesson: AuthError ⊂
            # CollectorError — never swallow it in an inner guard).
            try:
                discussions = collector.fetch_discussions(repo_name, config.lookback_days)
            except (InvalidRepoError, NetworkError) as exc:
                logger.warning("skipped discussions for %s: %s", repo_name, type(exc).__name__)
                discussions = []
            except CollectorError as exc:
                if isinstance(exc, (AuthError, RateLimitError)):
                    raise  # propagate fatal / terminal errors to outer arms (AC-V2-006-022)
                logger.warning("skipped discussions for %s: %s", repo_name, type(exc).__name__)
                discussions = []

            # AC-V2-006-019: concatenate issues + releases + discussions before partition
            # so _partition_new sees one list and mark_seen records the full 3-source set
            # in one call (R1 invariant — one _partition_new BEFORE one mark_seen).
            items = issues + releases + discussions
            # R1 (ADR-001): partition BEFORE mark_seen — snapshot is_seen while it still
            # reflects the PREVIOUS run's state, not this run's writes.
            new, seen = _partition_new(items, state)
            # mark_seen BEFORE summarize — decoupled (AC-7-019); empty list is safe no-op.
            # Always pass the FULL `items` (never `new`) — recording is unconditional and
            # orthogonal to rendering (BR-V2-001-002, AC-V2-001-010).
            state.mark_seen(items)
            # Selection-at-extend (ADR-004): delta_enabled picks what's RENDERED; what's
            # RECORDED (above) never changes. Never re-query is_seen after mark_seen.
            all_items.extend(new if config.delta_enabled else items)
            stats["collected"] += len(items)
            stats["seen"] += len(seen)
            stats["new"] += len(new)
            # AC-7-015: exactly one outcome log line per repo, no secret
            logger.info(
                "collected %d item(s) from %s "
                "(issues=%d releases=%d discussions=%d seen=%d new=%d)",
                len(items),
                repo_name,
                len(issues),
                len(releases),
                len(discussions),
                len(seen),
                len(new),
            )

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
        config=SummarizerConfig(
            model=config.llm_model or _model_for(config.llm_provider)  # ADR-002: no default
        ),
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
    conditional_cache = _build_etag_cache(config)  # AC-V2-007-019: best-effort, two-flag gate
    collector = GitHubCollector(config.github_token, conditional_cache=conditional_cache)
    state = _build_store(config)  # AC-V3-003-004/005: env-driven Upstash vs JSON file

    # --- Collect (per-repo isolation) ---
    all_items, stats = _collect_all(config, collector, state)

    # ⚠️  CRASH-SAFETY CRITICAL (ADR-004, AC-V2-007-024/025):
    # commit() is called EXACTLY ONCE here, AFTER _collect_all returns.
    # _collect_all calls mark_seen() per-repo INSIDE the loop, so all fetched items are
    # durably recorded before we commit the ETags.
    # A fatal AuthError or StateError propagates out of _collect_all BEFORE this line,
    # leaving etags.json UNCHANGED so the next run re-fetches (no lost items).
    # A terminal RateLimitError is caught INSIDE _collect_all (break+partial), so commit()
    # runs for repos that completed — correct, because their items were mark_seen-recorded.
    # DO NOT: wrap in try/except, move earlier, or call per-repo. (See design.md ADR-004.)
    conditional_cache.commit()  # once, unguarded, after the loop — CRASH-SAFETY-CRITICAL

    # --- Summarize (LLM or no-LLM) ---
    summarized = _summarize(config, all_items)
    stats["summarized"] = len(summarized)

    # --- Render ONCE (empty list → valid no-new-items doc, AC-7-006) ---
    digest = render(summarized, lookback_days=config.lookback_days)

    # --- Deliver ONCE (BR-7-007) ---
    if config.output_destination == "stdout":
        delivery = StdoutDelivery()
    elif config.output_destination == "discord":
        delivery = DiscordDelivery(  # AC-V2-005-001, AC-V4-001-005
            config.webhook_url,
            timeout=10.0,
            use_embeds=config.discord_use_embeds,
        )
    else:
        delivery = FileDelivery(config.output_path)
    delivery.deliver(digest)

    # --- Run-summary log (AC-7-021); no secret in line --- (AC-V2-001-010: seen/new counts)
    logger.info(
        "run complete — repos: %d, collected: %d, seen: %d, new: %d, summarized: %d, skipped: %d",
        stats["repos"],
        stats["collected"],
        stats.get("seen", 0),
        stats.get("new", 0),
        stats.get("summarized", 0),
        stats["skipped"],
    )
