## 7 — scheduler-cli-7 (S3 done: 2026-06-30)
### Dependencies (from other changes)
- github-collector-2: `GitHubCollector(token, CollectorConfig)`, `fetch_items(repo, lookback_days)`, errors hierarchy (`CollectorError` base → `AuthError`/`RateLimitError`/`InvalidRepoError`/`NetworkError`)
- state-store-3: `JsonFileStateStore(state_path)`, `.mark_seen(list[RawItem])` (atomic, write-once `first_seen_at`)
- summarizer-llm-4: `LiteLLMSummarizer(*, provider, api_key, cache, config)`, `.summarize_items(list[RawItem]) -> list[SummarizedItem]`; `SummarizerConfig(model: str, ...)` — `model` REQUIRED
- digest-renderer-5: `render(items: list[SummarizedItem], *, lookback_days: int) -> str` (empty list → non-empty no-new-items doc)
- delivery-6: `FileDelivery(path)` / `StdoutDelivery()` `.deliver(content: str)` · `DeliveryError`; `BrokenPipeError` handled at CLI top level
### Shared Decisions
- ADR-002: when a wiring change needs a constructor field not in `Config`, derive it inside the pipeline via a default map + env var rather than adding Config fields — documents the default in README + revisits as Config field in V2
- ADR-003: collector exception→action table is NORMATIVE and ORDER-DEPENDENT (most-specific-first) — `AuthError`(fatal) → `RateLimitError`(break+deliver) → other `CollectorError`(skip+continue)
- ADR-006: no-LLM path wraps items as `SummarizedItem(summary=NO_LLM_PLACEHOLDER)` — summarizer never constructed; placeholder is non-empty so renderer emits it
### Exports (other changes may depend on these)
- `osspulse.pipeline.run_pipeline(config: Config) -> None` — the V1 end-to-end orchestrator (previously `NotImplementedError`)
- `osspulse.cli` — `osspulse run` command with full error boundary + exit-code contract
### Constraints Set (apply to subsequent changes)
- Do NOT add fields to `Config` to pass adapter tunables — use pipeline-level derivation + env vars (ADR-002)
- `pipeline.py` is the ONLY sanctioned cross-stage importer; stage modules must never import each other (AC-7-002)
- `run_pipeline` token/key discipline: pass to ctor only, never store on a retained object, never log raw upstream exceptions (BR-7-006, RF-1/ADR-004)
- `osspulse run` exit-code contract: 0 = success (incl. delivered-but-empty); 1 = fatal (ConfigError/AuthError/DeliveryError/StateError); no distinct "delivered-empty" code (ADR-005)
---
