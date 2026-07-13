# Design: V3-003 — Upstash Redis state backend (`v3-upstash-state`)

> Type: **CR** · Rigor: **lite** · Scope: **tiny** · Ticket: **V3-003**
> One new adapter + env-driven backend selection. No `StateStore` Protocol change.

## Sketch — Gap Analysis

**No critical gaps found.** The proposal + spec deltas (8 ACs, 5 BRs, 2 INTs) fully
specify the adapter contract, key/field layout, backend-selection rule, and fail-loud
semantics. Codebase read confirms the two real traps the analyst already flagged:

- **R-1 (verified in `pipeline.py`)**: `_partition_new` / `_collect_all` call
  `state.is_seen(repo, item_type, item_id)` and `state.mark_seen(items)` **directly on the
  concrete adapter** — the `StateStore` Protocol (`load`/`save`) is never called by the
  pipeline. Any backend implementing only the Protocol `AttributeError`s at runtime. The
  Upstash adapter MUST implement `is_seen`/`mark_seen` with byte-for-byte identical semantics
  to `JsonFileStateStore` (write-once `first_seen_at`, empty-list no-op,
  `repo+item_type+item_id` identity). → **ADR-002**.
- **R-2 (verified)**: `_partition_new(items, state: JsonFileStateStore)` and
  `_collect_all(..., state: JsonFileStateStore)` are type-hinted to the **concrete** class.
  They must widen to a shared seen-tracker type to accept the new backend. → **ADR-003**.

No contradictory BRs, no undefined entities. `StateError` already exists
(`src/osspulse/state/errors.py`) and the CLI already maps it to `Error: <msg>` exit 1, so
fail-loud reuses the existing path. Proceeding to full (condensed) design.

## Context

A GitHub Actions runner is stateless — the local `.osspulse/state.json` that makes runs
idempotent/delta-aware is discarded when the runner dies. V3-002 committed `state.json` back
into the repo (fragile: needs `contents: write`, force-add, clean-tree guard, leaks history).
Upstash Redis exposes a plain **HTTP REST API** that works from any stateless environment, so
persisting seen-state there makes CI runs idempotent with **no** commit-back.

Current state store: `JsonFileStateStore` (`src/osspulse/state/json_store.py`) — the reference
semantics this adapter mirrors. Constructed unconditionally in `pipeline.run_pipeline`.

## Goals / Non-Goals

**Goals:**
- New `UpstashStateStore` adapter (HTTP REST via `upstash-redis`) implementing the
  `StateStore` Protocol **plus** the `is_seen`/`mark_seen` helpers the pipeline calls.
- Env-driven backend selection at construction: both `UPSTASH_REDIS_REST_URL` +
  `UPSTASH_REDIS_REST_TOKEN` present → Upstash, else `JsonFileStateStore` (unchanged).
- Fail loud on any runtime Upstash error (`StateError`, exit 1) — never silent fallback.

**Non-Goals:** (per proposal) migrating the LLM summary cache; TTL/expiry; multi-tenant
namespacing; changing the `StateStore` Protocol signature; retiring the V3-002 git commit-back;
a local→Upstash migration tool.

## Architecture Overview

Ports/adapters (hexagonal-lite), unchanged style. The new adapter sits alongside
`JsonFileStateStore` in the S3 State Store bounded context; both are concrete adapters selected
by a new `_build_store(config)` helper that mirrors the existing `_build_cache` /
`_build_etag_cache` env-driven construction in `pipeline.py`.

```
pipeline.run_pipeline
  └─ _build_store(config)          # NEW — env-driven selection (ADR-001)
        ├─ both env vars set  → UpstashStateStore(url, token)   # NEW adapter
        └─ else               → JsonFileStateStore(state_path)  # unchanged
  └─ _collect_all(config, collector, state: SeenTracker)   # type widened (ADR-003)
        └─ _partition_new(items, state: SeenTracker) → state.is_seen(...)
        └─ state.mark_seen(items)
```

- **Cross-spec deps**: reuses `StateError` (`state/errors.py`), `RawItem` (`models.py`), and
  the CLI's existing `StateError → exit 1` mapping. No conflict with prior state-store ACs
  (AC-3-*) — those constrain `JsonFileStateStore`, which is untouched.
- **Boundary**: adapter imports only `osspulse.models`, `osspulse.state.errors`, `os`, stdlib,
  and `upstash_redis` — no GitHub/LLM/network-of-other-modules coupling (mirrors json_store's
  import discipline).

## Decisions (ADRs)

### ADR-001 — Backend selection at construction time by env-var presence

- **Context**: The pipeline must pick Upstash vs JSON file. AC-V3-003-004/005 require: both env
  vars present+non-empty → Upstash; either absent/empty → JSON file, unchanged.
- **Options**:

  | Option | Pros | Cons |
  |---|---|---|
  | A. `_build_store(config)` helper mirroring `_build_cache`/`_build_etag_cache` | Consistent with existing pattern; testable; single decision point | one new function |
  | B. Inline the `if` in `run_pipeline` | fewer lines | not unit-testable in isolation; diverges from the two existing `_build_*` helpers |
  | C. Config-flag driven (`[state] backend=`) instead of env presence | explicit | contradicts AC-004/005 (env-presence is the CONFIRMED selector); adds config surface |

- **Decision**: **A**. A `_build_store(config)` helper. Reads both env vars; if both are set and
  non-empty → `UpstashStateStore(url, token)`, else `JsonFileStateStore(config.state_path)`.
  Wired into `run_pipeline` in place of the direct `JsonFileStateStore(...)` construction.
  Matches the established `_build_cache`/`_build_etag_cache` convention (INT-V3-003-002).
- **Consequences**: Selection is unit-testable via monkeypatched env. Local dev with no env
  vars creates **no** Upstash client and needs no new runtime dep (AC-V3-003-005). Empty-string
  env vars count as absent (`os.environ.get(...)` truthiness check).

### ADR-002 — Adapter implements `is_seen`/`mark_seen` (the real contract), not just the Protocol

- **Context (R-1)**: `pipeline._partition_new` / `_collect_all` call `is_seen`/`mark_seen`
  directly on the concrete store; the `StateStore` Protocol (`load`/`save`) is never called by
  the pipeline. An adapter with only `load`/`save` `AttributeError`s at runtime. Also,
  write-once `first_seen_at` must survive concurrent/re-marked writes without a
  read-modify-write race (AC-V3-003-003).
- **Options**:

  | Option | Pros | Cons |
  |---|---|---|
  | A. Implement `load`/`save` + `is_seen`/`mark_seen`; `mark_seen` uses `HSETNX` per field | write-once is atomic server-side; no RMW race; identical semantics to json_store | per-item `HSETNX` = N commands per repo |
  | B. `mark_seen` does `HGETALL` → merge → `HSET` (read-modify-write) | fewer round-trips | RMW race can overwrite `first_seen_at`; violates AC-003 write-once |
  | C. Implement only `load`/`save`, reconstruct dict in memory | matches Protocol literally | `AttributeError` at runtime (R-1) — non-starter |

- **Decision**: **A**. Key `osspulse:state:{repo}` (hash), field `{item_type}:{item_id}`, value
  = UTC ISO-8601 `first_seen_at` (`…Z`). `is_seen` → `HGET` (truthy = seen). `mark_seen` →
  per not-locally-known item, `HSETNX(key, field, now_z())` — set-if-absent enforces write-once
  atomically server-side (AC-V3-003-003), no RMW race. Empty `items` list → no-op
  (identical to json_store, AC-V3-003-001). `load`/`save` implemented for Protocol conformance
  (`load` → scan `osspulse:state:*` into the `{"version":1,"seen":{...}}` dict shape; `save` →
  best-effort `HSET` per field) but are not on the pipeline's hot path.
- **Consequences**: `first_seen_at` is preserved on re-mark exactly like json_store (AC-003).
  Per-item `HSETNX` is N commands/repo; acceptable at 1 run/day over a small watchlist
  (free tier = 10k commands/day). Reuse the existing `_identity_key` / `_now_utc_z` shapes
  (`{item_type}:{item_id}`, `%Y-%m-%dT%H:%M:%SZ`) so field/value formats match json_store
  byte-for-byte (EC-002 empty-id → `"issue:"` accepted, not rejected).

### ADR-003 — Widen pipeline type hints to a `SeenTracker` Protocol (adds a Protocol, does NOT change `StateStore`)

- **Context (R-2)**: `_partition_new` / `_collect_all` are typed to the concrete
  `JsonFileStateStore`. The new backend must be accepted. Scope constraint 5 forbids changing
  the `StateStore` Protocol.
- **Options**:

  | Option | Pros | Cons |
  |---|---|---|
  | A. Add a `SeenTracker(Protocol)` in `ports.py` with `is_seen`/`mark_seen`; hint both fns to it | documents the real contract the pipeline depends on; structural typing → no adapter change; `StateStore` untouched | one new Protocol (5 lines) |
  | B. Union hint `JsonFileStateStore \| UpstashStateStore` | explicit | pipeline imports concrete adapters → couples core to infra (anti-pattern); grows with each backend |
  | C. Add `is_seen`/`mark_seen` to the `StateStore` Protocol | one type | **violates scope constraint 5** (changes the Protocol signature); AC-V3-003-008 forbids |

- **Decision**: **A**. Add `class SeenTracker(Protocol)` to `ports.py` declaring
  `is_seen(repo, item_type, item_id) -> bool` and `mark_seen(items: list[RawItem]) -> None`.
  Widen `_partition_new`/`_collect_all` `state:` hints to `SeenTracker`. `StateStore` is
  **unchanged** — `is_seen`/`mark_seen` stay concrete adapter helpers on both stores, exactly
  as AC-V3-003-008 requires.
- **Consequences**: Core depends on a port interface, not a concrete adapter (respects the
  architecture rule). Both stores satisfy `SeenTracker` structurally with zero changes to
  `JsonFileStateStore`. `ports.py` is coverage-omitted (pure Protocols) so no coverage impact.

### ADR-004 — Fail loud: runtime Upstash error → `StateError`, never silent fallback

- **Context (R-4, AC-V3-003-007)**: State is the idempotency source of truth. When Upstash is
  selected and a call fails at runtime (network/auth/service), a silent fallback to the (empty,
  on a fresh CI runner) local file would re-render everything or lose seen-state.
- **Decision** _(one reasonable approach — scope=tiny R8 exception)_: Wrap every Upstash client
  call in the adapter; on **any** exception raise `StateError(<class-based message>)` (chained
  `from exc`). The CLI already maps `StateError → Error: <msg>` exit 1. Fallback to
  `JsonFileStateStore` happens **only** at construction time on env-var absence (ADR-001),
  **never** as a runtime catch. This deliberately **inverts** the best-effort summary/ETag cache
  behavior (`_build_cache`/`_build_etag_cache` swallow to a null object) — state is fatal, caches
  are not (contrast noted in the v2-cache-etag memory lesson).
- **Consequences**: A down Upstash aborts the run (exit 1) rather than silently corrupting
  idempotency; next run safely re-processes. Error messages are composed from
  status/exception-type only — **never** `str(exc)` and never the URL/token (R-3, AC-006).

## DB Schema

_(No relational DB — Redis key/field layout only.)_ One hash per repo:

| Redis key | Field | Value |
|---|---|---|
| `osspulse:state:{repo}` (e.g. `osspulse:state:vercel/next.js`) | `{item_type}:{item_id}` (e.g. `issue:42`) | `first_seen_at` UTC ISO-8601 `…Z` |

Repo slug (`/`, `.`) lives in the key — valid in Redis, no escaping, no collision with the
field separator `:` because the pair sits inside the per-repo hash (AC-V3-003-002, E-7).

## API Design

_(N/A — CLI tool, no HTTP API surface. R5/R9/openapi.yaml do not apply; deviation is inherent to
the project per `context/conventions.md` "no HTTP API".)_ The internal contract is the
`SeenTracker` Protocol (ADR-003) + the `upstash-redis` HTTP client calls (`HGET`/`HSETNX`).

## Error Mapping

| Condition | Handling | AC |
|---|---|---|
| Upstash unreachable / network error on `is_seen`/`mark_seen`/`load`/`save` | raise `StateError` (chained), exit 1, `Error: <msg>` on stderr — message from exception-type, no secret | AC-V3-003-007, R-3 |
| Upstash auth/service error (4xx/5xx from REST) | raise `StateError` — never silent fallback / empty-state | AC-V3-003-007 |
| Both env vars absent/empty at construction | construct `JsonFileStateStore` (not an error) | AC-V3-003-005 |
| Re-mark existing field | `HSETNX` no-op (write-once preserved) — not an error | AC-V3-003-003 |
| Empty `items` in `mark_seen` | no-op, no client call | AC-V3-003-001 |

## Sequence Flows

**Selection** (`run_pipeline` → `_build_store`): read `UPSTASH_REDIS_REST_URL` +
`UPSTASH_REDIS_REST_TOKEN` → both non-empty? → `UpstashStateStore(url, token)` : else
`JsonFileStateStore(config.state_path)`.

**mark_seen** (per repo, unchanged call site): `_partition_new` reads `is_seen` (→ `HGET`) for
each item BEFORE any write (R1 snapshot invariant, already enforced in `_collect_all`) →
`mark_seen(items)` iterates, `HSETNX(osspulse:state:{repo}, {item_type}:{item_id}, now_z())`
per item. Any client exception anywhere → `StateError` propagates out of `_collect_all` (it is
NOT a `CollectorError` subclass, so the existing per-repo except arms don't catch it) → CLI
exit 1.

## Edge Cases

Covered by proposal E-1..E-7: fail-loud on mid-run write error (E-1); no-env local path
unchanged (E-2); `HSETNX` idempotent re-mark (E-3); empty `item_id` → `"issue:"` accepted
(E-4); CI runner survives restart (E-5); secret never logged (E-6); slug with `/`,`.` valid
in key (E-7). All map to existing ACs; no new edge cases introduced.

## Performance

1 run/day over a small watchlist. Per repo: 1 `HGET` per fetched item (`is_seen`) + up to 1
`HSETNX` per new item (`mark_seen`) = ~2N commands/repo worst case. Well within Upstash free
tier (10k commands/day). No batching optimization needed at this scale; `load`/`save`
(full-scan) are off the pipeline hot path. _(No perf regression to the JSON path — unchanged.)_

## Security

- **R-3 / AC-V3-003-006 (Information disclosure)**: REST URL + token are bearer credentials.
  Read ONLY from env; never logged, never in an exception message (compose from
  exception-type/status, never `str(exc)`), never written to a committed file. `.env.example`
  documents the names only.
- **R-5 (Tampering)**: remote data shared by token holders; low sensitivity (public-repo issue
  IDs), accepted. Note in README: private watchlist → dedicated DB + rotate token.
- STRIDE: only I (disclosure) + D (availability, handled by fail-loud ADR-004) are material;
  both mitigated. No auth/payment/PII → no full STRIDE model required (`security.stride_analysis`
  = auto).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Adapter implements only Protocol → runtime `AttributeError` (R-1) | med | high | ADR-002 implements `is_seen`/`mark_seen`; checkpoint test round-trips both |
| Type hint stays concrete → new backend rejected by type checker (R-2) | med | low | ADR-003 `SeenTracker` Protocol widening |
| Silent fallback loses idempotency (R-4) | low | high | ADR-004 fail-loud `StateError`, construction-time fallback only |
| Secret leaks into log/error (R-3) | low | high | env-only read; message from exception-type; no `str(exc)` |
| `HSETNX` semantics misunderstood (RMW race) | low | med | ADR-002 set-if-absent is atomic server-side |

## Implementation Guide

**Recommended order** (follows `tasks.md` 1→7, dependency order data→adapter→wiring→docs→test):
1. `pyproject.toml`: add `upstash-redis>=1.7,<2` to `[project].dependencies` (pinned major).
2. `src/osspulse/state/upstash_store.py`: `UpstashStateStore` — mirror `json_store.py`'s
   `_identity_key` / `_now_utc_z` helpers (copy the field/value format exactly), `__init__(url,
   token)` constructs `upstash_redis.Redis(url=url, token=token)`, implement `is_seen`
   (`HGET`), `mark_seen` (per-item `HSETNX`, empty-list no-op), `load`/`save` for Protocol.
3. Wrap all client calls → `StateError` (fail loud); compose messages from exception-type only.
4. `pipeline.py`: add `_build_store(config)` (mirror `_build_etag_cache`); wire into
   `run_pipeline` replacing `JsonFileStateStore(config.state_path)`.
5. `ports.py`: add `SeenTracker(Protocol)`; widen `_partition_new`/`_collect_all` `state:` hints.
6. README + `.env.example`: document the two secrets + selection rule.
7. **Checkpoint**: module-scope tests (`state/`, `pipeline`) + lint; Upstash MOCKED (no live
   network — mock the `upstash_redis.Redis` client); assert `StateStore` Protocol unchanged;
   both backends round-trip `is_seen`/`mark_seen`; grep no secret substring in code/logs.

**Patterns to follow:**
- `src/osspulse/state/json_store.py` — copy `_identity_key`, `_now_utc_z`, empty-list no-op,
  write-once discipline, import discipline (no cross-module imports), `StateError` raising.
- `src/osspulse/pipeline.py::_build_etag_cache` / `_build_cache` — the env-driven `_build_*`
  helper shape (but INVERT the swallow-to-null behavior: state fails loud, caches don't).
- `src/osspulse/ports.py::ConditionalCache` / `_NullConditionalCache` — how a Protocol is added
  to the port layer.

**Gotchas:**
- ⚠️ Do NOT catch `StateError` in `_collect_all` — it must propagate to the CLI (an existing
  comment in `_collect_all` already forbids a defensive catch here; the same applies).
- ⚠️ `_partition_new` MUST run before `mark_seen` (existing R1 invariant) — unchanged; the
  Upstash adapter does not cache in memory, so each `is_seen` is a live `HGET`. That's fine:
  `_partition_new` reads all items before any `mark_seen` write, so the snapshot is still
  pre-write per repo.
- ⚠️ Empty-string env var = absent (truthiness check, not just `in os.environ`).
- ⚠️ Never `str(exc)` an Upstash error into a `StateError` message — it may embed the tokened
  URL. Compose from `type(exc).__name__` / status only.
- ⚠️ `upstash-redis` sync client is `from upstash_redis import Redis` — use the sync (not async)
  class to match the synchronous pipeline.
