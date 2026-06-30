# Release — 7 (scheduler-cli-7)
Date: 2026-06-30
Deploy strategy: direct (CLI tool, single-operator, no server infrastructure)

## Release Notes

**Features**

- `osspulse run` command wires all five V1 stages end-to-end into a single pipeline run
  (AC-7-001, AC-7-003, AC-7-016). Previously `run_pipeline` raised `NotImplementedError`.
- Per-repo failure isolation: `InvalidRepoError`, `NetworkError`, and `CollectorError` are
  logged and skipped; the run continues with remaining repos (AC-7-004, AC-7-015).
- Auth is fatal: an `AuthError` (401/403) aborts the entire run with exit 1 and a
  token-safe error message — the shared token is invalid for all repos (AC-7-005, AC-7-014).
- Rate-limit terminal: when the collector exhausts its backoff on a `RateLimitError`, the
  repo loop stops and already-collected items are summarised and delivered — partial results,
  exit 0 (AC-7-017).
- No-LLM path: omitting `[llm]` from `config.toml` produces a full digest with each item's
  summary replaced by `(no summary — LLM disabled)` — zero LLM cost, useful for first-run
  connectivity checks (AC-7-008, AC-7-022, D-1).
- Default model inference: if `model` is omitted from `config.toml`, the pipeline picks a
  sensible default per provider (openai → `openai/gpt-4o-mini`, ollama → `ollama/llama3`,
  anthropic → `anthropic/claude-3-haiku-20240307`, groq → `groq/llama3-8b-8192`) — explicit
  model setting is still recommended for cost predictability (AC-7-007, ADR-002).
- Redis degrades gracefully: if `REDIS_URL` is absent or Redis is unreachable, the pipeline
  continues without a cache — the LLM is called on every run for unseen items, never crashes
  (AC-7-009, ADR-002).
- `BrokenPipeError` handler at the CLI top level: `osspulse run | head -1` exits 0 rather
  than producing a Python traceback (AC-7-013).
- Idempotency: `mark_seen` is called per repo during collection, decoupled from
  summarisation; re-running produces a byte-identical digest (AC-7-010, AC-7-011, AC-7-019).
- README updated: Usage section documents the no-LLM path, default model table, and Redis
  optional cache.

**Bug fixes**

- None (greenfield feature).

**Breaking changes**

- None for operators: the CLI interface (`osspulse run`) is unchanged. Internally,
  `run_pipeline(config)` in `osspulse.pipeline` now has a real implementation instead of
  raising `NotImplementedError`.

## Migration Checklist

| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | No DB migrations (V1 uses JSON file state store only) | N/A | N/A | No | N/A |

No schema changes. No data migrations. The JSON state file (`~/.osspulse/state.json` or
configured `state_path`) is forward-compatible.

## Rollback Plan

1. `git checkout feature/6-delivery` (or the prior release tag once tagging history grows).
2. `uv sync` to reinstall dependencies at the prior version.
3. Re-run `uv run osspulse run` — the `NotImplementedError` stub will return, which is the
   prior behaviour. No state corruption risk (state file is append-only per the store design).

## Post-Deploy Smoke Test

- [ ] `uv run osspulse run --help` → prints help, exit 0.
- [ ] `uv run osspulse run` with no `config.toml` → `Error: Config file not found`, exit 1,
      no traceback.
- [ ] `uv run osspulse run --config config.toml` with `GITHUB_TOKEN` unset →
      `Error: GITHUB_TOKEN is required`, exit 1, no traceback.
- [ ] `uv run osspulse run --config config.toml` with a valid `GITHUB_TOKEN` and no `[llm]`
      section → exit 0, digest written with `(no summary — LLM disabled)` placeholders.
- [ ] `uv run osspulse run | head -1` (stdout mode) → exits 0 cleanly, no Python traceback
      (BrokenPipeError handler — AC-7-013).
- [ ] Re-run immediately → byte-identical digest, `mark_seen` state updated only once
      (idempotency check — AC-7-011).
- [ ] `uv run pytest -q` → 271 passed, 0 failed.

## Known Limitations (Low priority — next cycle)

- **H1-b (AC-7-021)**: `test_run_summary_log_emitted_on_success` asserts exit code only;
  caplog assertion not wired. Behavior verified by code review. Improve in next cycle.
- **H1-c (AC-7-018)**: `test_summarizer_returns_fewer_items` confirms `deliver` is called
  but doesn't assert digest contains only survivor items. Behavior verified by code review.
- **Import isolation test** (AC-7-002): reads `.py` source files — passes vacuously if the
  package is installed as a wheel without source. Acceptable for source-install dev env.

## Archive

- [ ] `openspec archive "scheduler-cli-7"` run — spec deltas merged into the living spec,
      change moved to `openspec/changes/archive/`
