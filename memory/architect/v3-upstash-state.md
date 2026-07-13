# architect memory — v3-upstash-state

## 2026-07-11 — v3-upstash-state: pipeline calls concrete helpers, not the Protocol — design to the REAL contract
The `StateStore` Protocol declared only `load`/`save`, but the pipeline actually calls
`is_seen`/`mark_seen` on the concrete adapter. A new backend implementing only the Protocol
would `AttributeError` at runtime. Lesson: before designing an alternate adapter, grep the
call sites — design to what callers invoke, not to the Protocol signature. Widen the type hint
with an ADDED `SeenTracker(Protocol)` (structural typing) rather than changing the existing
Protocol, so the "no Protocol change" constraint holds.

## 2026-07-11 — v3-upstash-state: an idempotency store INVERTS the best-effort-cache failure pattern
Existing `_build_cache`/`_build_etag_cache` swallow errors to a null object (caches are
best-effort). A state store is the idempotency source of truth — it must fail loud
(`StateError`, exit 1) on any runtime error; silent fallback to an empty local file on a fresh
CI runner re-renders/loses seen-state. Reuse the env-driven `_build_*` selection shape but
explicitly invert the runtime error handling, and say so in an ADR + module comment so S4
doesn't copy the swallow pattern.

## 2026-07-11 — v3-upstash-state: write-once timestamp over a network store = HSETNX, not read-modify-write
`first_seen_at` write-once across a remote hash must use `HSETNX` (atomic set-if-absent),
never HGETALL+merge+HSET which races. Also: never `str(exc)` a remote-client error into a
user-facing message — it can embed the tokened REST URL; compose from exception-type/status.
