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
