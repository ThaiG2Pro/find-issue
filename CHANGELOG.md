# Changelog

All notable changes to OSS Pulse are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.0] — 2026-07-13

### Added (V4-002 Digest UX)
- **Retry x7 backoff**: LiteLLM summarizer now retries up to 7 times (raised from 3) with
  exponential backoff on transient LLM errors — fewer failed digests on flaky providers
  (AC-V4-002-001, AC-V4-002-002)
- **`max_items_per_type` cap** (default 10): a `_truncate_per_type` pipeline step runs
  *before* summarize, keeping the newest N items per `(repo, item_type)` by `created_at`
  desc and dropping the rest — prevents runaway LLM cost on prolific repos (AC-V4-002-003,
  AC-V4-002-004, AC-V4-002-005, AC-V4-002-006)
- **Truncation alert**: `render()` now emits `⚠️ +{count} items not shown (limit: {N})`
  immediately after each repo header when items were dropped; the alert aggregates counts
  across all item types for that repo (AC-V4-002-007, AC-V4-002-012)
- **Option-A per-item Discord embeds**: Discord delivery now sends one embed per item
  (title/summary/type-colour/footer) plus one yellow header embed per repo, replacing the
  v4-001 one-embed-per-repo layout; colours: issue=`0xED4245`, release=`0x57F287`,
  discussion=`0x5865F2`, header=`0xFEE75C`; unknown types use a neutral fallback
  (AC-V4-002-008, AC-V4-002-009, AC-V4-002-010, AC-V4-002-011)
- `mark_seen` still records the full pre-truncation item set — truncation is
  presentation-only and does not affect idempotency (AC-V4-002-006)
- `render()` gains `dropped_counts` and `max_items_per_type` keyword params with `None`
  defaults; calling without them is byte-identical to the previous version (AC-V4-002-012)

---

## [0.14.0] — 2026-07-13

### Added (V4-001 Discord Rich Embeds)
- `[discord] use_embeds = true` config opt-in — send digest as Discord Embed objects instead of plain text (AC-V4-001-008)
- `_parse_sections`: split renderer Markdown at `## ` boundaries → per-repo embed sections (AC-V4-001-001)
- `_color_for_repo`: deterministic per-repo sidebar colour via `hashlib.md5` % 6-colour palette — stable across runs (AC-V4-001-002)
- `_build_embeds`: title, description (≤4096 code points), color, footer `OSS Pulse • {timestamp}` per section (AC-V4-001-001/003)
- `_batch_embeds`: group embeds into requests of ≤10 (AC-V4-001-004)
- Fallback to plain text when no `## ` sections found (e.g. "No new items") (AC-V4-001-006)
- Fatal `DeliveryError` on embed POST failure — URL never leaked in message (AC-V4-001-007)
- 23 new tests (681 total)



---

## [0.13.0] — 2026-07-11

### Added (v3-upstash-state — V3-003)

- **`UpstashStateStore`** (`src/osspulse/state/upstash_store.py`): new state backend
  persisting seen-items in Upstash Redis over HTTP REST (`upstash-redis>=1.7,<2`).
  Implements `is_seen` via `HGET`, `mark_seen` via `HSETNX` (write-once
  `first_seen_at`, no read-modify-write race), plus `load`/`save` for
  `StateStore` Protocol conformance (AC-V3-003-001, AC-V3-003-002, AC-V3-003-003).
- **Env-driven backend selection** (`pipeline._build_store`): both
  `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` present (non-empty) →
  `UpstashStateStore`; either absent/empty → `JsonFileStateStore` (unchanged
  fallback). Selection happens at construction time only — no runtime switching
  (AC-V3-003-004, AC-V3-003-005).
- **Fail-loud `StateError`** on all Upstash runtime errors: any exception from the
  `upstash-redis` client is caught, wrapped in `StateError`, and propagated to the
  CLI (`exit 1`) — never swallowed, never falls back to local state mid-run, because
  state is the idempotency source of truth (AC-V3-003-007).
- **No secrets in error messages**: error text uses `type(exc).__name__` only; REST
  URL and token are never interpolated into any log or exception message
  (AC-V3-003-006).
- **`SeenTracker` Protocol** added to `ports.py`: minimal interface (`is_seen`,
  `mark_seen`) widening `_partition_new`/`_collect_all` type hints; `StateStore`
  Protocol is **unchanged** — `load`/`save` only (AC-V3-003-008).
- **`.env.example`** and **README §State backends**: operator documentation for
  Upstash setup, env-var names, and the selection rule.
- **39 new tests** (`tests/state/test_upstash_store.py`,
  `tests/test_pipeline_upstash.py`) covering all 8 ACs; total suite: **658 tests**,
  96% coverage.

## [0.12.0] — 2026-07-11

### Added (v3-github-actions — V3-002)

- **GitHub Actions daily digest workflow** (`.github/workflows/osspulse.yml`): runs
  `osspulse run` on a cron schedule at 08:00 UTC+7 (`0 1 * * *`) and on
  `workflow_dispatch` (AC-V3-002-001, AC-V3-002-002).
- **State persistence via git commit-back**: after each run the workflow force-adds
  `.osspulse/state.json` (gitignored) and commits it back with
  `[skip ci]` in the message so the next stateless runner is delta-aware and the
  push does not re-trigger the workflow (AC-V3-002-003, AC-V3-002-005, AC-V3-002-006).
- **Clean-tree guard**: `git diff --cached --quiet || (git commit … && git push)`
  — no empty commit and no red job when state is unchanged (AC-V3-002-004).
- **Concurrency guard**: `concurrency.group: osspulse-digest` with
  `cancel-in-progress: false` prevents overlapping digest runs (AC-V3-002-007).
- **Install from source**: workflow runs `uv pip install --system -e .` so the
  latest committed source is used, not a PyPI release (AC-V3-002-008).
- **`config.toml.ci.example`**: template operators copy to `config.toml` and
  `git add -f` before the first run; keeps repo secrets out of version control
  (AC-V3-002-009).
- **README §Running on GitHub Actions**: operator setup guide — secrets
  (`GITHUB_TOKEN`, `LLM_API_KEY`, `DISCORD_WEBHOOK_URL`), `config.toml` first-run
  steps, and `workflow_dispatch` smoke-test instructions (AC-V3-002-010).
- **`permissions: contents: write`** scoped to the job only — minimum required for
  the commit-back push (AC-V3-002-011).

### Bug fixes

- **BUG-1 (bash precedence)**: fixed spurious `git push` on clean-tree runs caused
  by left-to-right `||`/`&&` associativity. Changed
  `… || git commit … && git push` → `… || (git commit … && git push)` so push
  only runs when a new commit is created.

### No breaking changes

- No changes to `src/`. All existing CLI behaviour, config schema, and pipeline
  stages are unchanged.

## [0.11.0] — 2026-07-11

### Added (v3-llm-throttle — V3-001)

- **Token-aware sliding-window throttle**: `SummarizerConfig` gains `tokens_per_minute`
  (default 6000, tuned for Groq free-tier). `_TokenWindow` tracks per-call
  `total_tokens` in a 60-second rolling window; `sleep_if_needed()` pauses before
  issuing a call when the window is near the budget. Cache hits and skipped items are
  **not** counted into the window (AC-V3-001-004).
- **Vietnamese-language summaries**: `SummarizerConfig.language` (default `"vi"`) is
  injected into the system prompt so the LLM returns summaries in Vietnamese by default.
  Operators can override to any language in `config.toml` (AC-V3-001-001).
- **`response.usage` None-safety**: token recording now guards against providers and
  mocks that return `None` for `response.usage` — treats as 0 tokens and never crashes
  (AC-V3-001-003).
- **429 retry-then-skip**: `RateLimitError` triggers exponential-backoff retry up to 3
  attempts, honouring the `Retry-After` header when present. Only after exhausting
  retries does the existing skip-log-continue fallback apply (AC-V3-001-002,
  AC-V3-001-005..010). API key is never logged during retry (AC-V3-001-012).

### Tests

- 10 new unit tests added; suite total: **619 tests** (0 failures).

### No breaking changes

- All 4 new `SummarizerConfig` fields carry defaults; zero config changes required for
  existing deployments.

---

## [0.10.0] — 2026-07-10

### Added (v2-007-cache-etag)

- **GitHub HTTP ETag conditional-request caching**: the REST collector now sends
  `If-None-Match` on the first page of every endpoint (issues, releases). A `304 Not
  Modified` response is treated as an empty delta for that endpoint — no further pages
  are fetched and no rate-limit quota is consumed (AC-V2-007-001..005).
- **`ConditionalCache` port** (`ports.py`): `get(key) → str | None`, `set(key, validator)`,
  `commit()` — in-memory during the fetch loop, durable on `commit()`. Key format
  `{repo}:{endpoint}`. `_NullConditionalCache` is the no-op default (AC-V2-007-006..009,
  AC-2-015 port-boundary enforcement).
- **`JsonFileETagStore` adapter** (`src/osspulse/cache/etag_store.py`): persists ETags to
  `.osspulse/etags.json` using atomic temp-then-rename. Best-effort corrupt-tolerant —
  an unreadable or malformed file logs a WARNING and returns an empty cache, never raising
  `StateError` (inverted from `JsonFileStateStore` semantics per ADR-001,
  AC-V2-007-010..017).
- **First-page-only conditional requests**: `If-None-Match` is sent only on page 1.
  Pages 2..N are fetched unconditionally, preserving correctness for partial-cache
  scenarios (AC-V2-007-018..020, ADR-003).
- **RISK-001 crash-safety**: `commit()` is called exactly once, after `mark_seen`, outside
  the per-repo collection loop. A mid-loop `AuthError` or `RateLimitError` propagates
  before `commit()` — no partial ETag state is persisted for a failed run
  (AC-V2-007-021..025, ADR-004).
- **Pipeline E2E integration** (AC-V2-007-026..028): three end-to-end pipeline tests use
  real `JsonFileStateStore` + real `JsonFileETagStore` on `tmp_path` to verify the
  full conditional-cache flow without mocking the file layer.
- **Config opt-in** (`config.toml` `[etag_cache]` section): `enabled = true`,
  `path = ".osspulse/etags.json"`. Guarded by two-flag gate: conditional requests active
  only when `etag_cache_enabled AND delta_enabled` (AC-V2-007-029..034).
- **59 new tests** — 609 total; 97% coverage on touched modules
  (`etag_store` 92%, `github/client` 99%, `pipeline` 93%, `config` 98%).

---

## [0.9.0] — 2026-07-09

### Added (v2-006-discussions)

- **GitHub Discussions collection** via GraphQL API: `fetch_discussions` on
  `GitHubCollector` queries the GitHub GraphQL endpoint and returns discussions as
  `RawItem(item_type="discussion")` — same model as issues and releases (AC-V2-006-001).
- **Approach A inclusion**: discussions are included if their `createdAt` falls within
  `lookback_days` from the run time — identical logic to issues; not hotness-based
  (AC-V2-006-001, AC-V2-006-002).
- **Always-on collection**: every run attempts to collect discussions for every watched
  repo; no opt-in config required (AC-V2-006-018).
- **Disabled-Discussions silently skipped**: repos where GitHub Discussions is disabled
  (or not found) return an empty list — the run continues with the remaining repos
  and item types unaffected (AC-V2-006-003, ADR-003).
- **`200-with-errors` model**: the GraphQL endpoint always returns HTTP 200. A null
  `discussions` connection (shape-first detection) signals disabled/not-found → skip
  repo; a non-null connection with `errors` → raise `CollectorError` (ADR-003).
- **ADR-002 `json_body` routing**: `_request_with_retry` sends `GET` for REST calls
  (issues/releases) and `POST` for GraphQL calls (`json_body=dict`). One shared
  retry/classify path — no duplication (ADR-002).
- **Discussion identity**: `repo + "discussion" + str(number)` — same pattern as
  other item types; idempotency via the state store (AC-V2-006-005, AC-V2-006-020).
- **Digest grouping**: discussions appear under `### Discussions (N)` within each
  repo section of the rendered Markdown digest (AC-V2-006-021).
- **Token discipline**: `GITHUB_TOKEN` is applied only to the httpx client
  Authorization header — never stored on `self`, never in the GraphQL POST body,
  never in error messages or logs (AC-V2-006-017).
- **Pipeline inner-guard**: `AuthError` and `RateLimitError` propagate out of the
  discussions-collection loop (fatal/terminal treatment), matching the behaviour of
  the issues/releases guard (AC-V2-006-022).

### Changed

- `pipeline._collect_all`: discussions for each repo are fetched after issues and
  releases and concatenated before `_partition_new` / `mark_seen` — the R1
  partition-before-mark-seen invariant is preserved (AC-V2-006-019).
- `GitHubCollector`: extended with `fetch_discussions` (adapter-only, no change to
  `GitHubClient` Protocol) and shared `_request_with_retry` POST path (ADR-002).

### Tests

- 73 new tests; suite total: 550. Coverage 96.25% (client.py 99%, pipeline.py 93%).

---

## [0.8.0] — 2026-07-09

### Added (v2-005-push-delivery)

- **Discord webhook delivery** (`destination = "discord"`): digest POSTs to a Discord
  channel webhook after every run. Configure via `[output] destination = "discord"` in
  config.toml and `DISCORD_WEBHOOK_URL` in .env (AC-V2-005-001).
- **Smart 2000-char split**: long digests split automatically at `## repo` section
  boundaries first, then line, then hard char-slice — every message ≤ 2000 Unicode code
  points (Discord API limit) (AC-V2-005-004..007).
- **Configurable webhook env var**: `webhook_env` key overrides the env var name
  (AC-V2-005-012).
- **Security**: webhook URL never in logs/errors — DeliveryError uses status codes and
  exception type names only (AC-V2-005-011, STRIDE T1).
- **SSRF guard**: https + discord.com/discordapp.com host enforced at config-load
  (AC-V2-005-014..015).
- **10s timeout**: DeliveryError on timeout/network failure → exit 1 (AC-V2-005-010).

### Config snippet

```toml
[output]
destination = "discord"
# webhook_env = "DISCORD_WEBHOOK_URL"   # optional override
```

```bash
# .env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### Known limitations

- Partial multi-message delivery: messages 1..k-1 already sent if message k fails;
  no rollback (RISK-1, accepted — retry/backoff in V4).
- pipeline.py discord branch (291-294) not covered by pipeline tests; adapter fully
  tested (24 tests).

---

## [0.7.0] — 2026-06-30

### Added (scheduler-cli-7, ticket #7)

- **End-to-end pipeline** (`osspulse run`): `run_pipeline(config)` now wires all five V1
  stages — GitHub collect → state mark-seen → LLM summarise → Markdown render → deliver.
  Previously the function raised `NotImplementedError` (AC-7-001, AC-7-003).
- **Per-repo failure isolation**: `InvalidRepoError`, `NetworkError`, and `CollectorError`
  are logged and the repo is skipped; remaining repos continue normally (AC-7-004).
- **Auth is fatal**: `AuthError` (401/403) aborts the run immediately with a token-safe
  `Error:` message on stderr, exit 1 (AC-7-005, AC-7-014).
- **Rate-limit graceful termination**: `RateLimitError` stops collection, delivers
  already-collected items as a partial digest, exit 0 (AC-7-017).
- **No-LLM mode**: omit `[llm]` from `config.toml` → full digest produced with
  `(no summary — LLM disabled)` placeholders; no LLM cost (AC-7-008, AC-7-022).
- **Default model inference**: if `model` is omitted, a sensible per-provider default is
  used (`openai/gpt-4o-mini`, `ollama/llama3`, `anthropic/claude-3-haiku-20240307`,
  `groq/llama3-8b-8192`). Explicit `model` setting still recommended (AC-7-007, ADR-002).
- **Redis degrades gracefully**: missing or unreachable Redis falls back to a no-op
  `_NullCache`; run always continues (AC-7-009).
- **`BrokenPipeError` handler**: `osspulse run | head -1` exits 0, no traceback (AC-7-013).
- **Idempotent runs**: `mark_seen` is called per repo during collection, decoupled from
  summarisation; re-running produces a byte-identical digest (AC-7-010, AC-7-011, AC-7-019).
- **README**: Usage section updated with no-LLM path, default model table, Redis config.

### Changed

- `pyproject.toml`: `pipeline.py` removed from coverage `omit` list (was excluded while
  the function was a stub — now fully exercised at 97%+).
- `tests/test_cli.py`: `test_run_valid_config_exits_zero` updated to mock `run_pipeline`
  (the function is now real and would call GitHub with the fake token).

### Known limitations (Low — next cycle)

- `test_run_summary_log_emitted_on_success` (H1-b, AC-7-021): verifies exit code only;
  caplog assertion not wired. Behaviour confirmed by code review.
- `test_summarizer_returns_fewer_items` (H1-c, AC-7-018): confirms `deliver` is called but
  doesn't assert digest content. Behaviour confirmed by code review.
- Import isolation test (AC-7-002) passes vacuously from a wheel install without source.

---

## [0.6.0] — 2026-06-29

### Added (delivery-6, ticket #6)

- **S6 Delivery stage**: `StdoutDelivery` (pipe-friendly, `BrokenPipeError`-safe) and
  `FileDelivery` (atomic write via write-temp-then-rename).
- `[output]` config section: `destination = "file" | "stdout"`, `output_path`.
- `Delivery` port (`osspulse.ports.Delivery`) and `DeliveryError` exception.
- CLI `run` command wired to delivery adapters.

---

## [0.5.0] — 2026-06-29

### Added (digest-renderer-5, ticket #5)

- **S5 Digest Renderer**: `render(items, lookback_days)` pure Markdown transform.
- Alphabetical repo sections, fixed item-type ordering (Issues → Discussions → Releases →
  Kh\u00e1c), `no-new-items` document when list is empty.

---

## [0.4.0] — 2026-06-25

### Added (summarizer-llm-4, ticket #4)

- **S4 Summariser**: `LiteLLMSummarizer` with Redis cache-aside, input cap at 8000 chars,
  graceful per-item LLM failure (log + skip).
- `SummaryCache` port + `RedisSummaryCache` adapter.

---

## [0.3.0] — 2026-06-24

### Added (state-store-3, ticket #3)

- **S3 State Store**: `JsonFileStateStore` — atomic write-temp-rename, `mark_seen` /
  `has_seen` for idempotency.
- `StateStore` port + `StateError`.

---

## [0.2.0] — 2026-06-24

### Added (github-collector-2, ticket #2)

- **S2 GitHub Collector**: `GitHubCollector` (httpx, pagination, retry/backoff).
- `AuthError`, `RateLimitError`, `NetworkError`, `InvalidRepoError`, `CollectorError`.

---

## [0.1.0] — 2026-06-21

### Added (project-foundation-1, ticket #1)

- Project skeleton: `models.py` (RawItem, SummarizedItem, Config), `ports.py`
  (GitHubClient, LLMClient, StateStore, SummaryCache, Delivery), CLI skeleton
  (`osspulse run` -> NotImplementedError stub), `pyproject.toml` (uv + hatchling),
  `.env.example`, `config.example.toml`, mise/ruff/pytest/pytest-cov configuration.
