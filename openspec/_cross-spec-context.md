# Cross-Spec Context
> Knowledge bridge — agents read this when starting a NEW change to understand what prior changes exported, decided, or constrained.

## 2 — github-collector-2 (S3 done: 2026-06-23)
### Dependencies (from other changes)
- project-foundation: `osspulse.models.RawItem` (frozen, 7 str fields) · `osspulse.ports.GitHubClient` Protocol · `osspulse.config.REPO_PATTERN` (shared regex)
### Shared Decisions
- ADR-001: collector tunables injected via `CollectorConfig` constructor — port signature + S1 `Config` untouched
- ADR-004: GITHUB_TOKEN set on httpx client at construction; never in repr/logs/errors
- ADR-007: no openapi.yaml when change has no inbound HTTP API (CLI-only tool)
### Exports (other changes may depend on these)
- `GitHubCollector` (`src/osspulse/github/client.py`) — implements `GitHubClient`, returns `list[RawItem]`
- `CollectorConfig` + `RetryPolicy` (`src/osspulse/github/config.py`) — frozen dataclasses for DI
- `osspulse.config.REPO_PATTERN` — promoted public constant for `owner/name` validation
### Constraints Set (apply to subsequent changes)
- Never hardcode `GITHUB_TOKEN` in config objects or log statements — ADR-004
- Any change consuming `RawItem` must treat `body`/`url`/`title` as potentially empty string, never assume non-null
- Per-item cutoff check (not page-level) is mandatory for any pagination over created-desc ordered data
---

## 3 — state-store-3 (S3 done: 2026-06-24)
### Dependencies (from other changes)
- project-foundation: `osspulse.ports.StateStore` Protocol (implemented unchanged) · `osspulse.models.RawItem` (input to `mark_seen`) · `osspulse.config.Config` (gains `state_path`)
- github-collector-2: `RawItem` fields (`item_id`/`body`/`url`/`title`) may be empty strings — empty `item_id` is valid, must key safely
### Shared Decisions
- ADR-001: `is_seen`/`mark_seen` live on the concrete adapter only — `StateStore` Protocol stays `load()->dict`/`save(dict)->None` (AC-3-018)
- ADR-002: atomic write = `tempfile` in `state_path.parent` + `os.replace` (same-fs guarantee); never write-in-place
- ADR-003: `StateError` in `src/osspulse/state/errors.py` (mirrors `ConfigError`)
- ADR-004: no openapi.yaml (CLI-only) — cites github-collector-2 ADR-007
### Exports (other changes may depend on these)
- `JsonFileStateStore` (`src/osspulse/state/json_store.py`) — implements `StateStore`; adds `is_seen`/`mark_seen`
- `StateError` (`src/osspulse/state/errors.py`) — surfaces as `Error: <msg>` exit 1
- `Config.state_path` (default `./.osspulse/state.json`); state doc shape `{version:1, seen:{repo:{"type:id":first_seen_at}}}`
### Constraints Set (apply to subsequent changes)
- Do NOT add methods to the `StateStore` Protocol in V1 — a new `SeenStore` protocol waits for a 2nd impl (SQLite, V2)
- State doc `version=1`; unknown/newer version → `StateError` (never auto-reset); `version` is the V2 migration gate
- `first_seen_at` is write-once — never overwrite on re-mark
---

## 4 — summarizer-llm-4 (S3 done: 2026-06-25)
### Dependencies (from other changes)
- project-foundation: `osspulse.ports.LLMClient` + `SummaryCache` Protocols (unchanged); `osspulse.models.RawItem` (input), `SummarizedItem` (output), `Config` (`llm_provider`/`llm_api_key`)
- github-collector-2: injected-adapter + frozen-config pattern (`GitHubCollector`/`CollectorConfig`)
- state-store-3: adapter-only helpers off Protocol pattern (`is_seen`/`mark_seen`)
### Shared Decisions
- ADR-001: cache-aside lives inside the concrete adapter (injected `SummaryCache`); `LLMClient` Protocol untouched
- ADR-002: LLM error boundary = `openai.APIError` (runtime common base of all litellm exceptions; DEV-001)
- ADR-003: `content_hash` = SHA-256 hex of `title+"\n"+body` (post-truncation, 8000-char cap)
- ADR-005: batch helper `summarize_items()` on adapter only — NOT on `LLMClient` Protocol (AC-4-003)
- ADR-008: only `title`+`body` sent to LLM; `api_key` never logged (RF-1/RF-4)
### Exports (other changes may depend on these)
- `LiteLLMSummarizer` (`src/osspulse/summarizer/client.py`) — implements `LLMClient`; exposes `summarize_items(list[RawItem]) -> list[SummarizedItem]` as the pipeline entry point
- `RedisSummaryCache` (`src/osspulse/cache/redis_cache.py`) — implements `SummaryCache`
- `SummarizerConfig` (`src/osspulse/summarizer/config.py`) — frozen tunables (timeout, cap, model)
- `SummarizerError` / `SummarizationFailed` (`src/osspulse/summarizer/errors.py`)
### Constraints Set (apply to subsequent changes)
- Do NOT import `osspulse.github` or `osspulse.state` from `summarizer/` or `cache/` (AC-4-021)
- `LLMClient` and `SummaryCache` Protocol signatures are frozen — do not add methods in V1
- `api_key` must never appear in log records or error messages (ADR-008, RF-4)
- Future pipeline wiring calls `summarize_items()` (not `summarize()`) for graceful batch degradation
---
