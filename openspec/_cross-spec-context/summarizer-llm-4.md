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
