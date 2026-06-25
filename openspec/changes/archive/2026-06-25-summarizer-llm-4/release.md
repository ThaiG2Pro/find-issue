# Release Notes — summarizer-llm-4
# S4 Summarizer (LLM) — OSS Pulse V1

**Change**: `summarizer-llm-4`
**Branch**: `feature/4-summarizer-llm`
**Base branch**: `feature/3-state-store`
**Release date**: 2026-06-25
**Author**: developer (S6)
**Gate status**: SPEC LOCK ✅ · DESIGN REVIEW ✅ · BUILD ✅ · QA GO ✅ (user-approved 2026-06-25T15:48:00Z)

---

## Release Notes

### What is included

This change delivers the **S4 Summarizer (LLM) module** — the component that turns raw
GitHub issue text into short, readable summaries via LiteLLM, with a Redis-backed cache
to avoid re-calling the LLM for items already seen.

| Area | Description | ACs |
|------|-------------|-----|
| `LiteLLMSummarizer` adapter | Single-item `summarize(item)->str` with cache-aside: cache hit returns stored summary (zero LLM calls); cache miss calls LiteLLM once and stores the result | AC-4-001, AC-4-002, AC-4-003, AC-4-004, AC-4-005 |
| Cache key design | Stable `summary:{repo}:{item_type}:{item_id}:{sha256(title+"\n"+body)}` — edit-sensitive, collision-resistant | AC-4-006, AC-4-007, AC-4-008 |
| Graceful LLM degradation | Timeout / 4xx / 5xx / 429 caught, item skipped, run continues — a single item failure never aborts the digest | AC-4-009, AC-4-010, AC-4-011 |
| Secret-safe logging | Failure logs contain item identity and error class only — never the LLM key, prompt, or issue body | AC-4-012 |
| Best-effort cache | Redis get/set failures treated as miss/no-op; the pipeline never crashes on a cache error | AC-4-013, AC-4-014 |
| Output normalization | LLM output stripped of code fences / markdown, collapsed to ≤ 2 sentences; empty output raises `SummarizationFailed` (item skipped) | AC-4-015, AC-4-016 |
| Dirty-data guard | `None` / missing title or body handled; fully-empty item skipped without an LLM call | AC-4-017, AC-4-018 |
| Input cap | Issue body truncated to 8 000 chars before hashing and sending — keeps token cost predictable | AC-4-019 |
| Idempotent re-run | Second run over unchanged items with warm cache makes zero new LLM calls | AC-4-020 |
| Hard S2/S4 boundary | Summarizer imports only `osspulse.models`, `osspulse.ports`, `litellm`, `redis`, stdlib — no GitHub or state-store code | AC-4-021 |
| No hardcoded secrets | `api_key` sourced from runtime env only; never a config field, never logged, never in repr | AC-4-022 |
| `RedisSummaryCache` adapter | Thin, faithful `SummaryCache` port over `redis.Redis`; best-effort policy lives in the summarizer, not the adapter | AC-4-004, AC-4-005, AC-4-013, AC-4-014 |
| `.env.example` expanded | All env vars (`GITHUB_TOKEN`, `LLM_PROVIDER`, `LLM_API_KEY`, `STATE_PATH`, `REDIS_URL`) documented with placeholder values | BUG-002 |
| README.md | RF-1 privacy disclosure (only title+body sent to the single configured provider), setup guide, config schema, key technical decisions | BUG-003 |

### Files added / changed

**New source files:**
- `src/osspulse/summarizer/errors.py` — `SummarizerError`, `SummarizationFailed`
- `src/osspulse/summarizer/config.py` — frozen `SummarizerConfig`
- `src/osspulse/summarizer/keys.py` — `content_hash`, `cache_key`
- `src/osspulse/summarizer/normalize.py` — `prepare_input`, `normalize_summary`
- `src/osspulse/summarizer/client.py` — `LiteLLMSummarizer` (cache-aside, batch, degradation)
- `src/osspulse/summarizer/__init__.py` — public exports
- `src/osspulse/cache/redis_cache.py` — `RedisSummaryCache`
- `src/osspulse/cache/__init__.py` — public exports

**New test files:**
- `tests/test_summarizer_normalize.py` (key + normalize unit tests)
- `tests/test_redis_cache.py` (cache adapter unit tests)
- `tests/test_summarizer_client.py` (LiteLLMSummarizer unit + batch tests)

**Updated project files:**
- `.env.example` — expanded to 33 lines covering all env vars with placeholders
- `README.md` — created (RF-1 privacy disclosure + setup + config schema)

**Not changed (by design):**
- `src/osspulse/pipeline.py` — `summarize_items` is not wired into the pipeline in this change; that is a future change when S5 renderer is ready.
- `src/osspulse/ports.py` — `LLMClient` Protocol is unchanged (AC-4-003).

### Known deviations

| ID | Description | Impact |
|----|-------------|--------|
| DEV-001 | LLM error boundary uses `except openai.APIError` instead of `except litellm.exceptions.APIError`; verified at runtime that all litellm exceptions inherit from `openai.APIError`, not `litellm.exceptions.APIError` | None — design intent fully preserved; all four guard tests pass with real `litellm.exceptions.*` instances; monitor litellm upgrades |

### Non-blocking follow-up (not blocking release)

- **BUG-001**: Tighten `test_api_key_passed_to_completion_not_hardcoded_AC_4_022` assertion — remove the `or completion.call_args[0]` branch. Source behavior is correct; only the test assertion is weaker than intended.

---

## Migration Checklist

**N/A — this change introduces no database schema, no ORM migration, and no persistent data-format change.**

Rationale: OSS Pulse V1 uses a plain JSON file as its state store (no DB server). The S4 summarizer module is purely additive — it adds new Python source files and uses Redis as a best-effort cache (Redis is optional; its absence degrades gracefully). There is nothing to migrate, no schema to alter, and no existing data to transform.

| Migration item | Status |
|----------------|--------|
| DB schema migration | N/A — no database |
| Data format migration | N/A — no existing summarizer state |
| Redis schema | N/A — Redis cache is keyed by content hash; any prior cache entries are inert and expire naturally (or can be flushed with `redis-cli FLUSHDB`) |
| Config file migration | N/A — `SummarizerConfig` is code-only; operator adds `[llm]` block to `config.toml` on first use |
| Env var additions | `.env.example` documents all new vars; operator copies and fills in values |

---

## Rollback Plan

Because there is no DB migration and no irreversible data change, rollback is a simple branch revert:

1. **Revert the feature branch merge** (git revert the merge commit, or reset the base branch pointer to the pre-merge SHA). No data migration needs to be undone.
2. **Flush Redis cache** (optional): if the cache was populated during a test run, flush with `redis-cli FLUSHDB` or let keys expire naturally. Cache entries have no side effects on other components.
3. **Remove env vars** (optional): `LLM_PROVIDER`, `LLM_API_KEY`, `REDIS_URL` added to `.env` can be removed; their absence does not affect the GitHub collector or state store.
4. **Verify rollback**: run the test suite (`uv run pytest -q`) — the pre-existing 120 tests (before this change) should still pass. The three new test files (`test_summarizer_normalize.py`, `test_redis_cache.py`, `test_summarizer_client.py`) will be absent.

There is no risk of data loss: the JSON state store and any Redis cache entries are independent of the summarizer code. Rolling back the code does not corrupt either.

---

## Post-Deploy Smoke Test

Run these checks after deploying to confirm the summarizer is operational:

```bash
# 1. Confirm import is clean — no startup errors
uv run python -c "from osspulse.summarizer import LiteLLMSummarizer, SummarizerConfig; print('imports OK')"
uv run python -c "from osspulse.cache import RedisSummaryCache; print('cache import OK')"

# 2. Run lint + full test suite (should be 164/164 green, 99.38% coverage)
uv run ruff check src tests
uv run pytest --cov=osspulse --cov-report=term-missing -q

# 3. Smoke-test cache-aside round-trip (requires a running Redis)
#    Replace redis://localhost:6379/0 with your actual Redis URL if different.
uv run python - <<'EOF'
import redis
from osspulse.cache import RedisSummaryCache
from osspulse.summarizer.keys import cache_key, content_hash
from osspulse.models import RawItem

r = redis.from_url("redis://localhost:6379/0")
cache = RedisSummaryCache(r)

item = RawItem(repo="test/repo", item_type="issue", item_id="1",
               title="Smoke test", body="This is a smoke test.", created_at="2026-06-25")
h = content_hash("Smoke test", "This is a smoke test.")
k = cache_key(item, h)

cache.set(k, "Cache round-trip OK.")
result = cache.get(k)
assert result == "Cache round-trip OK.", f"Unexpected: {result!r}"
print(f"Cache round-trip PASS — key: {k}")
r.delete(k)
print("Cleanup done.")
EOF

# 4. Exercise LiteLLMSummarizer with a mock completion (no real LLM call)
uv run python - <<'EOF'
from unittest.mock import MagicMock
from osspulse.summarizer import LiteLLMSummarizer, SummarizerConfig
from osspulse.models import RawItem

class _NoCache:
    def get(self, key): return None
    def set(self, key, value): pass

mock_completion = MagicMock()
mock_completion.return_value.choices[0].message.content = "A clear summary. Done."

cfg = SummarizerConfig(model="openai/gpt-4o-mini")
summarizer = LiteLLMSummarizer(
    provider="openai", api_key="smoke-test-key",
    cache=_NoCache(), config=cfg, completion=mock_completion,
)
item = RawItem(repo="test/repo", item_type="issue", item_id="42",
               title="Hello", body="World", created_at="2026-06-25")
result = summarizer.summarize(item)
assert result == "A clear summary. Done.", f"Unexpected: {result!r}"
assert mock_completion.call_count == 1
print(f"Summarizer smoke PASS — summary: {result!r}")
EOF

# 5. Second run (same item, cache warm) — confirm zero LLM calls (idempotency)
uv run python - <<'EOF'
from unittest.mock import MagicMock
from osspulse.summarizer import LiteLLMSummarizer, SummarizerConfig
from osspulse.summarizer.keys import cache_key, content_hash
from osspulse.models import RawItem

class _WarmCache:
    def get(self, key): return "Cached summary from prior run."
    def set(self, key, value): pass

mock_completion = MagicMock()
cfg = SummarizerConfig(model="openai/gpt-4o-mini")
summarizer = LiteLLMSummarizer(
    provider="openai", api_key="smoke-test-key",
    cache=_WarmCache(), config=cfg, completion=mock_completion,
)
item = RawItem(repo="test/repo", item_type="issue", item_id="42",
               title="Hello", body="World", created_at="2026-06-25")
result = summarizer.summarize(item)
assert result == "Cached summary from prior run."
assert mock_completion.call_count == 0, "LLM should NOT be called on cache hit"
print(f"Idempotency smoke PASS — zero LLM calls, returned: {result!r}")
EOF
```

Expected outcome: all five steps print PASS with no exceptions.

---

## Deploy Strategy

This change is a **pure additive code drop** to a CLI tool. There is no server, no HTTP API,
and no shared data store that other services depend on. The deploy strategy is correspondingly simple:

| Step | Action |
|------|--------|
| 1. Merge | Merge `feature/4-summarizer-llm` into `feature/3-state-store` (or main when the full pipeline is assembled). Confirm CI green post-merge. |
| 2. Env vars | Operator adds `LLM_PROVIDER`, `LLM_API_KEY` (and optionally `REDIS_URL`) to their `.env` file, following `.env.example`. |
| 3. Config | Operator adds `[llm]` block to `config.toml` (see README.md §Configuration). |
| 4. Redis (optional) | Start a local or remote Redis instance and set `REDIS_URL`. If Redis is absent, the tool still works — summaries are re-computed on every run (more LLM cost, no functional difference). |
| 5. Smoke test | Run the five smoke checks above. Confirm `164 passed` and PASS messages. |
| 6. Monitor (post-deploy, 30 min) | Run `osspulse run` against the live watchlist. Confirm: digest produced, no unhandled exceptions, no secrets visible in logs, LLM calls within expected count. |

**Rollout risk**: LOW. The summarizer is not wired into `pipeline.py` yet — `pipeline.py` still
raises `NotImplementedError`. This change cannot break any currently-working CLI flow. It only
adds importable, testable code that the next pipeline-wiring change will call.

**Feature-flag**: N/A. Because `pipeline.py` does not call `summarize_items` yet, there is no
live traffic risk from this merge. The feature is dormant until the pipeline-wiring change ships.
