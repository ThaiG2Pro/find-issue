# Tasks — scheduler-cli-7 (osspulse run — V1 pipeline wiring)

> Design: `design.md` (ADR-001..006) · Spec: `specs/scheduler-cli/spec.md` (22 ACs).
> Only 2 source files change: `src/osspulse/pipeline.py`, `src/osspulse/cli.py`. CLI-only — no openapi.yaml.
> All external adapters (GitHub/LLM/Redis/delivery) MUST be mocked in tests — never call real APIs.

## 1. Pipeline foundations (constants + helpers)

- [x] 1.1 Add module constants + logger in `run_pipeline` module: `NO_LLM_PLACEHOLDER = "(no summary — LLM disabled)"`, `logger = logging.getLogger("osspulse.pipeline")`.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-008, AC-7-022_

- [x] 1.2 Add `_PROVIDER_MODEL: dict[str, str]` map (`openai`→`openai/gpt-4o-mini`, `ollama`→`ollama/llama3`) + `_model_for(provider: str) -> str` with fallback `f"{provider}/{provider}"` (ADR-002, resolves GAP-001 — supplies the required `SummarizerConfig.model`).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-007_

- [x] 1.3 Add `_NullCache` (get→None, set→no-op) and `_build_cache() -> SummaryCache` constructing `RedisSummaryCache(redis.Redis.from_url(os.environ.get("REDIS_URL","redis://localhost:6379")))` inside try/except → `_NullCache` on any error (ADR-002; AC-7-009 best-effort degradation).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-009_

## 2. Collection with per-repo failure isolation

- [x] 2.1 Implement `_collect_all(config, collector, state, logger) -> tuple[list[RawItem], dict]`: iterate `config.watched_repos` in order; per repo call `collector.fetch_items(repo.full_name, config.lookback_days)`, then `state.mark_seen(items)` (decoupled — even on later summarize failure), aggregate; track stats (repos, collected, skipped).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-001, AC-7-016, AC-7-010, AC-7-019_

- [x] 2.2 Implement the exception→action ladder inside the per-repo try (ADR-003, most-specific-first): `except AuthError` → log WARN + re-raise (fatal); `except RateLimitError` → log WARN + `break` collection (deliver partial); `except (InvalidRepoError, NetworkError, CollectorError)` → log WARN `skipped: <reason>` + continue.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-004, AC-7-005, AC-7-017_

- [x] 2.3 Emit exactly one per-repo outcome log line (`collected N` / `skipped: <reason>`) at INFO/WARN, containing repo name + count/reason only — no secret, no raw upstream exception object (ADR-004).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-015, AC-7-014_

- [x] 2.4 ▟ CHECKPOINT — Verify collection layer: run `pytest tests/test_pipeline.py -k collect` + `ruff`/type check. Confirm per-repo isolation, auth-fatal, rate-limit-break, mark_seen decoupling behave per ADR-003 before wiring summarize/render. STOP for human review.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-004, AC-7-005, AC-7-017, AC-7-019_

## 3. Summarization (LLM + no-LLM paths)

- [x] 3.1 Implement `_summarize(config, all_items) -> list[SummarizedItem]`: when `config.llm_provider is None` → return `[SummarizedItem(raw=it, summary=NO_LLM_PLACEHOLDER) for it in all_items]` WITHOUT constructing/calling the summarizer (ADR-006, BR-7-010).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-008, AC-7-022_

- [x] 3.2 In `_summarize`, LLM-enabled branch: construct `LiteLLMSummarizer(provider=config.llm_provider, api_key=config.llm_api_key, cache=_build_cache(), config=SummarizerConfig(model=_model_for(config.llm_provider)))` and call `summarize_items(all_items)` EXACTLY ONCE; return survivors (fewer-than-collected is valid).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-007, AC-7-018, AC-7-009_

## 4. Orchestrator wiring (run_pipeline)

- [x] 4.1 Implement `run_pipeline(config: Config) -> None` replacing the `NotImplementedError` stub: construct `GitHubCollector(config.github_token)` + `JsonFileStateStore(config.state_path)` (token to collector ctor only, never on a shared object — BR-7-006/RF-1); call `_collect_all` → `_summarize`.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-003, AC-7-002, AC-7-014_

- [x] 4.2 In `run_pipeline`, render once + deliver once: `digest = render(summarized, lookback_days=config.lookback_days)`; select `StdoutDelivery()`/`FileDelivery(config.output_path)` by `config.output_destination`; `delivery.deliver(digest)` — exactly one render + one deliver per run (BR-7-007).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-001, AC-7-016, AC-7-006_

- [x] 4.3 Emit the final run-summary log line (total repos processed, collected, summarized, skipped) at INFO after delivery; no secret in the line.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-7-021, AC-7-014_

## 5. CLI integration (error boundary + exit codes)

- [x] 5.1 Rewrite `cli.run` to call `run_pipeline(cfg)` instead of delivering the hardcoded `"osspulse: pipeline not yet implemented"` stub (move adapter selection into the pipeline; CLI keeps config load + error boundary).
  File: `src/osspulse/cli.py`
  _Requirements: AC-7-003, AC-7-001_

- [x] 5.2 Extend the `except` ladder (most-specific-first, keep `BrokenPipeError` first for clean exit 0): add `AuthError` and fatal `StateError` → `typer.echo(f"Error: {e}", err=True)` + `Exit(code=1)`, no traceback; preserve existing `DeliveryError`/`ConfigError` handlers + exit codes (ADR-005 table).
  File: `src/osspulse/cli.py`
  _Requirements: AC-7-005, AC-7-012, AC-7-013, AC-7-020_

## 6. Tests

- [x] 6.1 `tests/test_pipeline.py` — Flow 1 happy path (LLM mocked): ≥1 repo with issues → one combined `summarize_items` call, one `render`, one `deliver`; exit/normal return; items aggregated into one digest.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-001, AC-7-007, AC-7-016_

- [x] 6.2 `tests/test_pipeline.py` — error taxonomy: one repo `InvalidRepoError`/`NetworkError` skipped (others succeed), `AuthError` re-raised fatal, terminal `RateLimitError` stops loop but delivers partial (ADR-003 / Flow 3).
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-004, AC-7-005, AC-7-017_

- [x] 6.3 `tests/test_pipeline.py` — all repos fail → `render([])` no-new-items doc delivered, normal exit 0 (Flow 4); and summarizer returns fewer items → only survivors rendered.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-006, AC-7-018_

- [x] 6.4 `tests/test_pipeline.py` — no-LLM path: `llm_provider is None` → summarizer never constructed (assert via mock), placeholder `(no summary — LLM disabled)` present in rendered digest.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-008, AC-7-022_

- [x] 6.5 `tests/test_pipeline.py` — idempotency + seen: re-run with same issues → byte-identical digest (V1 records but does not suppress); `mark_seen` called for collected items; Redis unreachable → degrades to miss, no crash.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-010, AC-7-011, AC-7-019, AC-7-009_

- [x] 6.6 `tests/test_pipeline.py` — SECURITY log-capture (RF-1): run with fake non-empty `github_token` + `llm_api_key`; assert neither secret substring appears in captured logs, stderr, or the delivered digest.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-014_

- [x] 6.7 `tests/test_pipeline.py` — import isolation static test: assert no stage module (`github`,`state`,`summarizer`,`cache`,`render`,`delivery`) imports another stage module (`pipeline.py` excluded — sanctioned importer).
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-002_

- [x] 6.8 `tests/test_cli_run.py` — observability: multi-repo mixed-outcome run emits exactly one outcome log line per repo + one final run-summary line.
  File: `tests/test_cli_run.py`
  _Requirements: AC-7-015, AC-7-021_

- [x] 6.9 `tests/test_cli_run.py` — CLI contract: `ConfigError` → exit 1 `Error: ...` no traceback; `AuthError` → exit 1 (no token in message); `DeliveryError` (missing parent dir) → exit 1; `BrokenPipeError` on stdout → clean exit 0; success → exit 0.
  File: `tests/test_cli_run.py`
  _Requirements: AC-7-012, AC-7-005, AC-7-020, AC-7-013_

## 7. Docs + final checkpoint

- [x] 7.1 Update README "Usage": `osspulse run` example, the no-LLM-provider behavior, the default model per provider + `REDIS_URL` override (ADR-002 surfacing).
  File: `README.md`
  _Requirements: AC-7-008, AC-7-009_

- [x] 7.2 ▟ CHECKPOINT (FINAL) — Full gate: `pytest --cov` (≥80% lines, project threshold) green; secret-leak log-capture test passing (RF-1/AC-7-014); import-isolation test passing (AC-7-002); `ruff` + type check clean; verify all 22 ACs covered. STOP for human review before S4 sign-off.
  File: `tests/test_pipeline.py`
  _Requirements: AC-7-014, AC-7-002, AC-7-021_
