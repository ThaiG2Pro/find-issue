# Glossary — V3-003 v3-upstash-state

| Term | Definition | Notes / added by |
|------|------------|------------------|
| SeenTracker | New `Protocol` in `ports.py` declaring `is_seen(repo, item_type, item_id) -> bool` + `mark_seen(items) -> None` — the real contract the pipeline depends on. Both stores satisfy it structurally. Does NOT change `StateStore`. | architect S3 (ADR-003) |
| `_build_store(config)` | New pipeline helper (mirrors `_build_cache`/`_build_etag_cache`) that selects the state backend by env-var presence at construction time. | architect S3 (ADR-001) |
| HSETNX | Redis set-hash-field-if-absent; atomic server-side write-once for `first_seen_at`, avoids read-modify-write race. | architect S3 (ADR-002) |
| Per-repo hash | State layout: one Redis hash per repo, key `osspulse:state:{repo}`, field `{item_type}:{item_id}`, value `first_seen_at` ISO-8601 `…Z`. | architect S3 (ADR-002) |
| fail loud | Runtime Upstash error → `StateError` (exit 1), never silent fallback/empty-state; inverts best-effort cache null-object behavior because state is the idempotency source of truth. | architect S3 (ADR-004) |
