# Glossary — scheduler-cli-7

| Term | Definition | AC-IDs | Phase |
|------|-----------|--------|-------|
| `osspulse run` | The single CLI entry point (Typer command in `cli.py`) that triggers one full V1 pipeline run | AC-7-001 | S1 |
| `run_pipeline(config)` | The orchestrator function in `osspulse.pipeline` that wires the five stages; replaces the current `NotImplementedError` stub | AC-7-001, AC-7-003 | S1 |
| Pipeline wiring | Constructing each adapter from `Config` and passing data one direction (Collector→State→Summarizer→Renderer→Delivery); no stage imports another stage | AC-7-002 | S1 |
| Per-repo failure isolation | Recoverable collector errors (404/InvalidRepoError/NetworkError) for one repo are logged + skipped; remaining repos still run | AC-7-004, BR-7-001 | S1 |
| Auth-fatal | `AuthError` (401/403) is fatal (exit 1) because all repos share one token — never a per-repo skip | AC-7-005, BR-7-002 | S1 |
| No-LLM-provider path | When `config.llm_provider is None`, skip the summarizer and render each item with the fixed placeholder summary `(no summary — LLM disabled)` (D-1, AC-7-008/022) | AC-7-008 | S1 |
| Batch summarize | Pipeline calls `LiteLLMSummarizer.summarize_items(list[RawItem])` (graceful skip-log-continue), not per-item `summarize()` | AC-7-007 | S1 |
| Seen-recording (V1) | Run calls `mark_seen` for collected items for idempotency; V1 records but does NOT filter seen items (delta is V2) | AC-7-010, AC-7-011, BR-7-003 | S1 |
| CLI error contract | Handled errors → `Error: <message>` on stderr, no traceback, exit 1; success exit 0; `BrokenPipeError` → clean exit 0 (inherited from delivery-6) | AC-7-012, AC-7-013, INT-7-001 | S1 |
| Per-repo outcome log | Exactly one INFO/WARN line per repo (collected N / skipped: reason), no secret value | AC-7-015, BR-7-005, RF-4 | S1 |
| Success-with-warnings | A run where some/all repos were skipped still exits 0 if it could render+deliver a (possibly "no new items") digest | AC-7-006 | S1 |
| `_PROVIDER_MODEL` / `_model_for(provider)` | Pipeline-private map (`openai`→`openai/gpt-4o-mini`, `ollama`→`ollama/llama3`) + fallback `f"{provider}/{provider}"` supplying the required `SummarizerConfig.model` without a Config field (ADR-002) | AC-7-007 | S3 |
| `_build_cache()` / `_NullCache` | Best-effort Redis cache construction from `REDIS_URL` env inside try/except; on any failure returns a `_NullCache` (get→None/set→no-op) so the run degrades instead of crashing (ADR-002) | AC-7-009 | S3 |
| `NO_LLM_PLACEHOLDER` | Fixed constant `"(no summary — LLM disabled)"` used as the `SummarizedItem.summary` on the no-LLM path; non-empty so the renderer emits it (ADR-006) | AC-7-008, AC-7-022 | S3 |
| Exception→action ladder | Per-repo try ordered most-specific-first: `AuthError`(fatal exit 1) → `RateLimitError`(break+deliver, exit 0) → `InvalidRepoError`/`NetworkError`/`CollectorError`(skip+continue) (ADR-003) | AC-7-004, AC-7-005, AC-7-017 | S3 |
| Sanctioned cross-stage importer | `pipeline.py` is the ONLY module allowed to import multiple stages; the import-isolation static test excludes it and asserts no stage imports another (ADR-001) | AC-7-002 | S3 |
