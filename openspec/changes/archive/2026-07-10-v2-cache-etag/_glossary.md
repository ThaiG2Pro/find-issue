# Glossary — v2-cache-etag (ticket V2-007)

| Term | Definition | Phase |
|------|------------|-------|
| ETag | An opaque HTTP validator GitHub returns on every REST response; echoed back in `If-None-Match` to make a conditional request | S1 |
| Conditional request | A GET carrying `If-None-Match: <etag>`; GitHub answers `304 Not Modified` (no body) if unchanged, or `200` with the fresh body if changed | S1 |
| 304 Not Modified | GitHub's response when the resource is unchanged since the cached ETag; **does not count against the rate limit** | S1 |
| Empty delta (304) | The collector's treatment of a first-page `304` — return an empty list for that endpoint, no further pages; sound only because the endpoint is fetched newest-first | S1 |
| ConditionalCache (port) | The `osspulse.ports` Protocol: `get(key)->str\|None`, `set(key,validator)` (in-memory), `commit()` (durable, best-effort) | S1 |
| JsonFileETagStore | The concrete adapter persisting the ETag cache to a separate `etags.json`, atomic-write, best-effort corrupt-tolerant | S1 |
| ETag cache key | `"{repo}:{endpoint}"` — e.g. `"owner/name:issues"`, `"owner/name:releases"` | S1 |
| etags.json | The per-repo-per-endpoint ETag store file (default `./.osspulse/etags.json`), separate from `state.json` | S1 |
| Best-effort cache | A cache whose loss/corruption degrades gracefully (WARN + empty + unconditional fetch) and NEVER changes which items are collected — opposite of `state.json` (fatal on corruption) | S1 |
| First-page-only conditional | The rule that `If-None-Match` is sent only on page 1 of an endpoint; pages 2..N are unconditional | S1 |
| Commit ordering (crash-safety) | `set()` is in-memory; the pipeline calls `commit()` only after `mark_seen`, so an aborted run leaves `etags.json` unchanged and no item is `304`-skipped before it was recorded seen | S1 |
| `[etag_cache]` section | Config section: `enabled` (bool, default true) + `path` (str, default `./.osspulse/etags.json`) | S1 |
| Two-flag gate | Conditional requests active only when `etag_cache_enabled` AND `delta_enabled` are both true | S1 |
| `_NullConditionalCache` | Architect S3 — the no-op `ConditionalCache` (`get`→`None`, `set`/`commit`→`pass`); the collector's default ctor arg and the disabled/failed-build result, so callers need no null checks (ADR-002) | S3 |
| `extra_headers` kwarg | Architect S3 — new keyword-only arg on `_request_with_retry` so the `If-None-Match` header rides the SINGLE existing retry/`_classify`/backoff path (no duplicated caller) | S3 |
| `first_page` gate | Architect S3 — the boolean in `fetch_items`/`fetch_releases` ensuring the conditional header is attached to page 1 only; pages 2..N stay unconditional (ADR-003) | S3 |
| `_build_etag_cache(config)` | Architect S3 — pipeline helper mirroring `_build_cache`: returns a `JsonFileETagStore` only when `etag_cache_enabled AND delta_enabled` (best-effort; any error → `_NullConditionalCache`), else the null cache | S3 |
| Unguarded post-loop commit | Architect S3 — `commit()` placed after `_collect_all` returns with NO surrounding try/except, so a fatal exception propagates before it (crash-safety, ADR-004) | S3 |
| `_ensure_loaded()` | Developer S4 — internal lazy-load helper in `JsonFileETagStore`; sets `_cache = {}` on first call, then loads from disk best-effort; subsequent calls are no-ops (cache hit) | S4 |
| Port-layer null object | Developer S4 — `_NullConditionalCache` lives in `ports.py` (not `etag_store.py`) so the collector imports only from the port layer, preserving AC-2-015 isolation | S4 |
