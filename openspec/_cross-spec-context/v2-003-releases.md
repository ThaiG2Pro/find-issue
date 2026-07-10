## V2-003 — v2-003-releases (S3 done: 2026-07-06)

### Dependencies (from other changes)
- v2-001-delta-filter: `_partition_new` helper + `mark_seen(full_list)` R1 invariant — reused unchanged in `_collect_all`
- github-collector-2: `GitHubCollector`, `CollectorConfig`, `_request_with_retry`, `_classify`, `_next_link`, `_parse_created`, `CollectorError` hierarchy — all reused unchanged
- digest-renderer-5: `GROUP_ORDER = ["issue","discussion","release"]` already emits `### Release (N)` — NO renderer delta

### Shared Decisions
- ADR-001: dual-key pagination — early-stop on `created_at` (endpoint sort key), include on `published_at` (requirement); residual RISK-002 miss accepted + regression-tested
- ADR-002: `fetch_releases` adapter-only; `GitHubClient` Protocol frozen (mirroring summarizer-llm-4 ADR-005)
- ADR-003: inner guard wraps ONLY `fetch_releases` in `_collect_all`; one `_partition_new` → one `mark_seen(issues+releases)` per repo preserves v2-001 R1
- ADR-004: no `openapi.yaml` (CLI tool, no HTTP API — consistent with all prior changes)

### Exports (other changes may depend on these)
- `GitHubCollector.fetch_releases(repo, lookback_days) -> list[RawItem]` — adapter-only method; NOT on `GitHubClient` Protocol
- `RawItem(item_type="release", item_id=tag_name, ...)` — release identity key `repo + "release" + tag_name` via existing state-store contract

### Constraints Set (apply to subsequent changes)
- Do NOT add `fetch_releases` to `GitHubClient` Protocol — it is intentionally adapter-only (ADR-002)
- Do NOT open a `digest-renderer` delta for releases — renderer already ships `GROUP_ORDER` with `"release"` (BR-V2-003-004)
- `pipeline.py` remains the only cross-stage importer; any new source follows the same inner-guard + single-partition + single-mark_seen pattern (ADR-003)
- `_collect_all` wiring pattern for a second source: `try: releases = fetch_X(); except (recoverable): releases=[]` — keep `AuthError` + terminal `RateLimitError` outside the inner catch
---
