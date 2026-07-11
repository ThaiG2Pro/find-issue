## ADDED Requirements

### Requirement: ConditionalCache port for per-repo per-endpoint HTTP validators
The system SHALL define a `ConditionalCache` port in `osspulse.ports` exposing exactly three
methods: `get(key: str) -> str | None` (return the stored validator for a key, or `None` on miss),
`set(key: str, validator: str) -> None` (record a validator **in memory only**), and
`commit() -> None` (durably persist the in-memory state, best-effort). The key SHALL be the compound
string `"{repo}:{endpoint}"` where `endpoint` is one of the REST endpoints (`issues`, `releases`).
The port SHALL store only opaque validator strings — never the `GITHUB_TOKEN`, response bodies, or
any PII. A `JsonFileETagStore` adapter SHALL implement this port structurally.

> ACs: AC-V2-007-001 [CONFIRMED], AC-V2-007-002 [CONFIRMED], AC-V2-007-006 [CONFIRMED]
> Business rules: BR-V2-007-001
> Integration: INT-V2-007-001

#### Scenario: The port defines get/set/commit and the store implements it (AC-V2-007-001) [CONFIRMED]
- **WHEN** `JsonFileETagStore` is checked against the `ConditionalCache` Protocol
- **THEN** it structurally satisfies `get(key) -> str | None`, `set(key, validator) -> None`, and `commit() -> None`

#### Scenario: A validator round-trips per repo+endpoint across instances (AC-V2-007-002) [CONFIRMED]
- **WHEN** one `JsonFileETagStore` does `set("owner/name:issues", '"abc123"')` then `commit()`, and a fresh `JsonFileETagStore` over the same path is created
- **THEN** the new instance's `get("owner/name:issues")` returns `'"abc123"'`, and `get("owner/name:releases")` (never set) returns `None`

#### Scenario: The persisted file contains only keys and validators, never secrets (AC-V2-007-006) [CONFIRMED]
- **WHEN** validators are stored for several repos/endpoints in an environment where `GITHUB_TOKEN` is set, and `etags.json` is read back as text
- **THEN** the file contents consist solely of `"{repo}:{endpoint}"` keys and their validator strings — the token value and any issue/release body text never appear

### Requirement: The ETag store persists atomically to a separate file
`JsonFileETagStore` SHALL persist its state to a JSON file (default `./.osspulse/etags.json`) that
is **separate** from the State Store's `state.json`. `commit()` SHALL write atomically: create a
temp file in the target's parent directory, `fsync`, then `os.replace` onto the target path, so a
concurrent reader never observes a partially-written file. The store SHALL NOT read, write, or
otherwise alter `state.json`, and SHALL NOT depend on the `JsonFileStateStore`.

> ACs: AC-V2-007-003 [CONFIRMED], AC-V2-007-008 [CONFIRMED]
> Business rules: BR-V2-007-003
> Integration: INT-V2-007-003, INT-V2-007-005

#### Scenario: commit writes atomically via temp file and os.replace (AC-V2-007-003) [CONFIRMED]
- **WHEN** `commit()` persists the cache
- **THEN** it writes to a temp file in the same directory as `etags.json`, flushes+fsyncs, and `os.replace`s it onto `etags.json`, so any reader sees either the old or the new complete file — never a torn one

#### Scenario: The ETag store never touches the state file (AC-V2-007-008) [CONFIRMED]
- **WHEN** a `JsonFileETagStore` and a `JsonFileStateStore` operate over the same directory during a run
- **THEN** the ETag store reads/writes only `etags.json` and the state store reads/writes only `state.json` — neither file is opened or modified by the other component

### Requirement: The ETag store is best-effort and tolerates a corrupt cache
`JsonFileETagStore` SHALL be **best-effort**: a missing, empty (0-byte/whitespace), corrupt
(unparseable JSON), or unreadable `etags.json` SHALL be treated as an empty cache — the store SHALL
log a WARN and continue, never raising. Losing or ignoring the cache SHALL NEVER change which items a
run collects or renders (it only affects whether a conditional request is sent). This is the
deliberate opposite of the State Store, whose corruption is fatal because it drives idempotency.

> ACs: AC-V2-007-004 [CONFIRMED]
> Business rules: BR-V2-007-002

#### Scenario: A missing etags.json yields an empty cache (AC-V2-007-004a) [CONFIRMED]
- **WHEN** `etags.json` does not exist and `get(any_key)` is called
- **THEN** it returns `None` (empty cache) and no error is raised

#### Scenario: A corrupt etags.json degrades to an empty cache with a warning (AC-V2-007-004b) [CONFIRMED]
- **WHEN** `etags.json` contains invalid JSON (or is unreadable) and the store loads it
- **THEN** the store logs a WARN, treats the cache as empty (every `get` returns `None`), and the run continues without raising — no `StateError`-equivalent fatal

### Requirement: set is in-memory only; commit is the sole durable write
`JsonFileETagStore.set()` SHALL update only the in-memory cache and SHALL NOT write to disk; the file
SHALL be written only when `commit()` is called. A `_NullConditionalCache` no-op implementation
(`get` → `None`, `set` → no-op, `commit` → no-op) SHALL also satisfy the port, for use when the ETag
cache is disabled or unavailable so callers need no null checks.

> ACs: AC-V2-007-005 [CONFIRMED], AC-V2-007-007 [CONFIRMED]
> Business rules: BR-V2-007-008

#### Scenario: set does not write to disk before commit (AC-V2-007-005) [CONFIRMED]
- **WHEN** `set("owner/name:issues", '"e1"')` is called but `commit()` is NOT
- **THEN** `etags.json` is not created/modified on disk, and a fresh `JsonFileETagStore` over the same path returns `None` for that key (the un-committed value is not durable)

#### Scenario: The null cache satisfies the port as a no-op (AC-V2-007-007) [CONFIRMED]
- **WHEN** `_NullConditionalCache` is used
- **THEN** `get(any_key)` returns `None`, `set(...)` and `commit()` are no-ops that touch no file, and it is accepted anywhere a `ConditionalCache` is expected
