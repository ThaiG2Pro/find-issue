# Analyst memory — v2-cache-etag (V2-007)

## 2026-07-10 — v2-cache-etag: HTTP caching on a pure-I/O adapter hides a crash-safety data-loss trap

Adding conditional-request (ETag/If-None-Match) caching to a collector that is deliberately pure-I/O
raises three requirement traps the raw "add ETag caching" ask never mentions:

1. **Boundary preservation** — the collector must not touch the State Store, so the ETag cache has to
   be a NEW injected port (`ConditionalCache`) + adapter, not a field on `state.json`. Mirror the
   existing best-effort-injected dependency (here: the Redis `SummaryCache` via `_build_cache`).
   Persist to a SEPARATE file so you don't bump the state store's locked schema version.

2. **Opposite corruption semantics** — an optimization cache (etags.json) must be BEST-EFFORT
   (corrupt → empty + WARN + unconditional fetch, never fatal), the deliberate inverse of the
   idempotency store (state.json → StateError-fatal). Spell this out or the developer will copy the
   fatal-on-corrupt logic.

3. **Commit-after-record crash-safety (the real bug)** — persisting a validator for items that were
   fetched-but-not-yet-recorded-seen lets the NEXT run's 304 silently skip un-rendered items = data
   loss. Resolution: `set()` in-memory during fetch; pipeline `commit()` ONCE after `mark_seen`; an
   aborted run leaves the cache file unchanged. This is the highest-risk AC and needs an explicit
   "commit not called when a fatal error fires mid-loop" tripwire test.

Plus: a 304-as-empty-delta is only sound on the NEWEST-FIRST FIRST PAGE (any new in-window item
changes page-1's ETag) — send If-None-Match on page 1 only; and gate conditional requests on
delta_enabled too (delta off = "show everything", so a 304-empty would violate it).

Also reconfirmed the recurring OpenSpec parser lesson: a requirement's SHALL/MUST must be in the
first clause BEFORE any comma, or `openspec validate` reports "must contain SHALL or MUST".
