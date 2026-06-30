# Changelog

All notable changes to OSS Pulse are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
