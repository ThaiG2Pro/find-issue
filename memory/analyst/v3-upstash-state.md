# Analyst memory — v3-upstash-state

## 2026-07-11 — v3-upstash-state: swapping a state-store backend is bounded by the HELPER contract, not the Protocol
`osspulse.ports.StateStore` declares only `load`/`save`, but the pipeline never calls those on
the state store at runtime — it calls the concrete-adapter helpers `is_seen`/`mark_seen`
(`_partition_new`/`_collect_all` in pipeline.py). So "add a new StateStore backend, no Protocol
change" is a trap: a backend implementing only the Protocol AttributeErrors at runtime. The spec
MUST require the new adapter to implement `is_seen`/`mark_seen` with identical semantics, and the
type hints pinned to the concrete `JsonFileStateStore` must widen. Always grep for how the
pipeline actually USES the port before scoping a "just add an adapter" CR.

## 2026-07-11 — v3-upstash-state: idempotency store fails LOUD; caches fail SOFT — opposite defaults
The v2-cache-etag lesson said best-effort corrupt-tolerance for the ETag/summary caches (silent
null-cache degrade). The state store is the INVERSE: it is the idempotency source of truth, so a
runtime backend failure must raise (StateError, exit 1), never silently fall back to the local
file or empty state — a silent degrade drops or re-renders items. Backend fallback (Upstash →
JSON file) is legitimate ONLY at construction time on env-var ABSENCE, never as a runtime catch.
When adding a remote backend to an idempotency store, always spec the runtime-failure = fatal AC
explicitly; the raw "fall back if not configured" ask hides the construction-vs-runtime distinction.
