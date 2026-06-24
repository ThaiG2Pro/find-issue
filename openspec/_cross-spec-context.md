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
