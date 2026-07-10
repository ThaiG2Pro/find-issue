# Changelog

All notable changes to OSS Pulse are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
