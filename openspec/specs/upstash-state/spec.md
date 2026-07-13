# upstash-state Specification

## Purpose
TBD - created by archiving change v3-upstash-state. Update Purpose after archive.
## Requirements
### Requirement: Upstash Redis state backend implements the seen-item store over HTTP
The system SHALL provide an `UpstashStateStore` adapter that persists seen-item state in
Upstash Redis via its HTTP REST API using the `upstash-redis` client. The adapter SHALL
implement the existing `osspulse.ports.StateStore` Protocol (`load() -> dict`,
`save(state: dict) -> None`) AND the `is_seen(repo, item_type, item_id) -> bool` /
`mark_seen(items: list[RawItem]) -> None` helpers the pipeline calls, with semantics
identical to `JsonFileStateStore`. State SHALL be stored as one Redis hash per repo with the
key `osspulse:state:{repo}`, each hash field named `{item_type}:{item_id}` and its value the
UTC ISO-8601 `first_seen_at` timestamp (trailing `Z`). This change SHALL NOT alter the
`osspulse.ports.StateStore` Protocol signature.

> ACs: AC-V3-003-001 [ASSUMED], AC-V3-003-002 [CONFIRMED], AC-V3-003-003 [ASSUMED], AC-V3-003-008 [CONFIRMED]
> Business rules: BR-V3-003-001, BR-V3-003-002
> Integration: INT-V3-003-001 (consumes the StateStore contract + is_seen/mark_seen helpers used by pipeline)

#### Scenario: A new item is recorded in Upstash and then reported as seen (AC-V3-003-001) [ASSUMED]
- **WHEN** `is_seen(repo, item_type, item_id)` is false for an item, then `mark_seen([item])` is called against the Upstash adapter
- **THEN** the item is written to the hash `osspulse:state:{repo}` under field `{item_type}:{item_id}` with a UTC ISO-8601 `first_seen_at` value, and a subsequent `is_seen(repo, item_type, item_id)` returns true

#### Scenario: Key and field layout is one hash per repo (AC-V3-003-002) [CONFIRMED]
- **WHEN** items for repo `vercel/next.js` of type `issue` with id `42` are recorded
- **THEN** they are stored in the Redis key `osspulse:state:vercel/next.js`, field `issue:42` — the repo slug (including `/` and `.`) sits in the key and the `{item_type}:{item_id}` pair is the field, with no collision or escaping required

#### Scenario: Re-marking a seen item preserves the original first_seen_at (AC-V3-003-003) [ASSUMED]
- **WHEN** an item already recorded with `first_seen_at = T1` is passed to `mark_seen` again at a later time `T2`
- **THEN** its stored `first_seen_at` remains `T1` (write-once, enforced set-if-absent per field), and the operation is idempotent — no duplicate entry and no timestamp overwrite

#### Scenario: The StateStore Protocol signature is unchanged (AC-V3-003-008) [CONFIRMED]
- **WHEN** this change is inspected
- **THEN** `osspulse.ports.StateStore` still declares exactly `load() -> dict` and `save(state: dict) -> None`; `is_seen`/`mark_seen` remain concrete adapter helpers (present on both `JsonFileStateStore` and `UpstashStateStore`), not on the Protocol

### Requirement: Backend is selected by Upstash env-var presence, defaulting to the JSON file
The pipeline SHALL select the state backend at construction time based on the presence of BOTH
`UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` environment variables. When both are set
and non-empty, the pipeline SHALL use `UpstashStateStore`. When either is absent or empty, the
pipeline SHALL fall back to the existing `JsonFileStateStore(config.state_path)` with unchanged
behavior. The Upstash REST URL and token SHALL be read only from the environment and SHALL NEVER
be logged, embedded in an error message, or written to a committed file.

> ACs: AC-V3-003-004 [CONFIRMED], AC-V3-003-005 [CONFIRMED], AC-V3-003-006 [ASSUMED]
> Business rules: BR-V3-003-003, BR-V3-003-004
> Integration: INT-V3-003-002 (mirrors _build_cache / _build_etag_cache env-driven construction in pipeline)

#### Scenario: Both env vars present selects the Upstash backend (AC-V3-003-004) [CONFIRMED]
- **WHEN** the pipeline builds the state store and both `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are set to non-empty values
- **THEN** it constructs and uses `UpstashStateStore` (not `JsonFileStateStore`), and no local `state.json` is read or written for that run

#### Scenario: Missing either env var falls back to the JSON file store (AC-V3-003-005) [CONFIRMED]
- **WHEN** the pipeline builds the state store and `UPSTASH_REDIS_REST_URL` or `UPSTASH_REDIS_REST_TOKEN` is absent or empty
- **THEN** it constructs `JsonFileStateStore(config.state_path)` with its existing behavior unchanged, and no Upstash client is created — so local dev needs no new runtime dependency

#### Scenario: The Upstash credentials never appear in logs or errors (AC-V3-003-006) [ASSUMED]
- **WHEN** the Upstash backend is constructed or a state operation fails
- **THEN** no log line, exception message, or committed file contains the REST URL or token value — credentials are read from env only

### Requirement: Runtime Upstash failure fails loud rather than silently degrading
The adapter SHALL fail loud on any runtime Upstash failure because the state store is the
idempotency source of truth. When the Upstash backend is selected (both env vars present) and an
Upstash operation fails at runtime (network error, auth failure, service error), the adapter SHALL
surface a clear `StateError` (reported as `Error: <message>` on stderr, exit code 1 per CLI
conventions) instead of silently falling back to the local file,
returning empty state, or swallowing the write. Backend fallback to the JSON file SHALL happen
ONLY at construction time on env-var absence, NEVER as a runtime catch. Unlike the best-effort
summary/ETag caches, a failed state read or write is fatal to the run.

> ACs: AC-V3-003-007 [ASSUMED]
> Business rules: BR-V3-003-005
> Risk: R-4 (Availability / idempotency — a silent degrade drops or re-renders items)

#### Scenario: A runtime Upstash write failure raises StateError, not a silent fallback (AC-V3-003-007) [ASSUMED]
- **WHEN** the Upstash backend is selected and a `mark_seen` (or `is_seen`) call fails because Upstash is unreachable or returns an error
- **THEN** a clear `StateError` propagates to the CLI (exit 1, `Error: <message>`), the run does NOT silently fall back to the local `state.json`, does NOT treat the store as empty, and does NOT continue as if the write succeeded — so idempotency is never silently lost

