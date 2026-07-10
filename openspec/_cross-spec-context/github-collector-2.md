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
