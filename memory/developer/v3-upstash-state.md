## 2026-07-11 — v3-upstash-state: Upstash state adapter + env-driven backend selection

### Lesson 1: `_build_*` helpers — state INVERTS cache fail-loud behavior

**Pattern**: The project has `_build_cache` and `_build_etag_cache` that swallow all construction
errors to a null-object (best-effort, caches don't matter). For the state backend this is
**exactly wrong** — state is the idempotency source of truth. When `_build_store` was added it
deliberately follows the same shape (reads env, returns the backend) but does NOT wrap runtime
calls in `except Exception → null`. State fails loud (`StateError`, exit 1); caches don't.

**Reusable rule**: When a new `_build_*` helper wraps a stateful component (database, state store),
check whether fail-loud vs best-effort is appropriate. Do NOT copy the null-object swallow pattern
from caches without thinking.

### Lesson 2: Pipeline type hint coupling to concrete adapter

**Trap**: `_partition_new` and `_collect_all` had `state: JsonFileStateStore` concrete type hints.
Adding a second backend required widening to a shared Protocol (`SeenTracker`). The `StateStore`
Protocol (`load`/`save`) was NOT the right port because the pipeline never calls those — it calls
`is_seen`/`mark_seen` directly on the concrete adapter.

**Reusable rule**: When the pipeline depends on helpers NOT on the Protocol, add a SECOND Protocol
(e.g. `SeenTracker`) that documents the real contract. Do NOT change the existing Protocol (scope
constraint); do NOT use Union of concrete adapters (couples core to infra).

### Lesson 3: Never str(exc) for Upstash/bearer-credential errors

**Pattern**: Upstash client exceptions may embed the tokened REST URL in `str(exc)`. Always
compose error messages as `f"Upstash {op} failed: {type(exc).__name__}"`. This gives enough
diagnostic context without leaking credentials. Apply to any bearer-token-based HTTP client.

### Lesson 4: Lazy import for optional upstash-redis dependency

When a dependency is only needed when specific env vars are set, do the import inside the
`if url and token` branch (not at module top). This avoids requiring the package for users who
never set the env vars. The pattern: `from osspulse.state.upstash_store import UpstashStateStore
# noqa: PLC0415` inside the branch.
