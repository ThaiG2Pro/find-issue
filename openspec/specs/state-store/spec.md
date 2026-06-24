# state-store Specification

## Purpose
TBD - created by archiving change state-store-3. Update Purpose after archive.
## Requirements
### Requirement: Persist and load seen-item state as a JSON file
The State Store SHALL implement the existing `osspulse.ports.StateStore` Protocol
(`load() -> dict`, `save(state: dict) -> None`) backed by a single JSON file. `load`
SHALL return the persisted state as a plain dict, and `save` SHALL write the given
dict so a subsequent `load` returns an equivalent dict. The file path SHALL be read
from config (`state_path`), defaulting to `./.osspulse/state.json`, and SHALL NEVER
be hardcoded in the persistence logic.

> ACs: AC-3-001 [CONFIRMED], AC-3-002 [CONFIRMED], AC-3-013 [CONFIRMED]
> Business rules: BR-3-001, BR-3-006

#### Scenario: Save then load round-trips the state (AC-3-001) [CONFIRMED]
- **WHEN** `save(state)` is called with a dict and later `load()` is called against the same path
- **THEN** `load()` returns a dict equivalent to the one saved (no loss or mutation of recorded entries)

#### Scenario: Missing file loads as empty state (AC-3-002) [CONFIRMED]
- **WHEN** `load()` is called and no file exists at `state_path`
- **THEN** an empty (initialized) state is returned and no error is raised, and no file is created until the first `save`

#### Scenario: state_path comes from config, not hardcoded (AC-3-013) [CONFIRMED]
- **WHEN** the store is constructed with a config `state_path = "<tmp>/custom/state.json"`
- **THEN** all reads/writes target that path, and changing the config path changes the target with no code edit

### Requirement: Record seen items by stable identity with first-seen timestamp
The State Store SHALL record each seen item under a stable identity of `repo` →
`"{item_type}:{item_id}"`, storing the UTC ISO-8601 `first_seen_at` timestamp at
which the item was first recorded. The timestamp format SHALL be UTC with a trailing
`Z` (e.g. `"2026-06-24T13:05:00Z"`), consistent with `RawItem.created_at`.
`mark_seen(items: list[RawItem])` SHALL add any not-yet-seen items and SHALL NOT
overwrite the `first_seen_at` of an item already recorded.
`is_seen(repo, item_type, item_id) -> bool` SHALL report whether an item is already
recorded. The persisted document SHALL carry a top-level integer `version` field for
forward migration; the V1 state-format version SHALL be `1`. The persisted shape SHALL
be `{"version": 1, "seen": {"<repo>": {"<item_type>:<item_id>": "<first_seen_at>"}}}`.

> ACs: AC-3-003 [CONFIRMED], AC-3-004 [CONFIRMED], AC-3-005 [ASSUMED], AC-3-014 [CONFIRMED]
> Business rules: BR-3-002, BR-3-003, BR-3-007

#### Scenario: A new item is recorded and then reported as seen (AC-3-003) [CONFIRMED]
- **WHEN** `is_seen` is false for an item, then `mark_seen([item])` is called
- **THEN** `is_seen(repo, item_type, item_id)` subsequently returns true and the entry carries a `first_seen_at` UTC ISO timestamp

#### Scenario: Re-marking a seen item preserves the original first_seen_at (AC-3-004) [CONFIRMED]
- **WHEN** an item recorded with `first_seen_at = T1` is passed to `mark_seen` again at a later time `T2`
- **THEN** its stored `first_seen_at` remains `T1` (not overwritten), and the operation is idempotent

#### Scenario: Identity is repo + item_type + item_id (AC-3-005) [ASSUMED]
- **WHEN** two items share the same `item_id` but differ in `repo` or `item_type`
- **THEN** they are recorded as distinct entries (the key is `repo` + `"{item_type}:{item_id}"`, not `item_id` alone)

#### Scenario: Persisted document carries a version field (AC-3-014) [CONFIRMED]
- **WHEN** a state file is written by `save`
- **THEN** the JSON document includes a top-level integer `version` field equal to `1` (the V1 state-format version) and a `seen` object

### Requirement: Empty mark_seen is a safe no-op
`mark_seen([])` SHALL leave the recorded state unchanged and SHALL NOT add spurious
entries.

> ACs: AC-3-006 [CONFIRMED]
> Business rules: BR-3-003

#### Scenario: Empty list does not alter state (AC-3-006) [CONFIRMED]
- **WHEN** `mark_seen([])` is called on a store with existing entries
- **THEN** the set of recorded entries is unchanged

### Requirement: Atomic, crash-safe writes
The State Store SHALL write state atomically using a write-to-temp-then-replace
strategy (`os.replace` or equivalent atomic rename on the same filesystem), so that a
crash or interruption mid-write SHALL NEVER leave a truncated or corrupt state file:
either the previous valid file or the fully-written new file SHALL be present.

> ACs: AC-3-007 [CONFIRMED], AC-3-008 [CONFIRMED]
> Business rules: BR-3-004
> Risk: RF-1 (Tampering / data integrity)

#### Scenario: Write goes through a temp file then atomic replace (AC-3-007) [CONFIRMED]
- **WHEN** `save(state)` writes the file
- **THEN** content is first written to a temporary file in the same directory and then atomically renamed into place (no direct in-place truncate-and-write of the target)

#### Scenario: Interrupted write leaves a valid file (AC-3-008) [CONFIRMED]
- **WHEN** a previous valid state file exists and a save is interrupted before the atomic rename completes
- **THEN** the previous valid state file remains intact and loadable (no half-written/corrupt JSON at `state_path`)

### Requirement: Fail loud on corrupt state, tolerate benign gaps
The State Store SHALL raise a clear, readable error (a `StateError`, surfaced as
`Error: <message>` on stderr with exit code 1 per CLI conventions) when the state
file exists but contains malformed JSON or an unknown/newer `version`. It SHALL NOT
silently reset corrupt state to empty (which would lose idempotency history). A
zero-byte file or a file missing the expected `seen` key SHALL be tolerated as empty
state rather than treated as corruption.

> ACs: AC-3-009 [CONFIRMED], AC-3-010 [CONFIRMED], AC-3-011 [CONFIRMED], AC-3-012 [CONFIRMED]
> Business rules: BR-3-005
> Risk: RF-2 (data integrity — silent reset forbidden)

#### Scenario: Malformed JSON raises a clear error, no silent reset (AC-3-009) [CONFIRMED]
- **WHEN** the state file contains invalid JSON and `load()` is called
- **THEN** a clear `StateError` is raised (readable one-line message) and the corrupt file is NOT overwritten or reset to empty

#### Scenario: Unknown/newer version raises rather than mis-parsing (AC-3-010) [CONFIRMED]
- **WHEN** the state file declares a `version` the store does not recognize
- **THEN** a clear `StateError` is raised instead of silently mis-reading the data

#### Scenario: Zero-byte file is treated as empty state (AC-3-011) [CONFIRMED]
- **WHEN** the state file exists but is empty (0 bytes) and `load()` is called
- **THEN** an empty state is returned without raising

#### Scenario: Missing seen key tolerated as empty (AC-3-012) [CONFIRMED]
- **WHEN** the state document is valid JSON but lacks the top-level `seen` key
- **THEN** the store treats recorded entries as empty rather than crashing

### Requirement: Create the state directory when absent
The State Store SHALL create the parent directory of `state_path` (including
intermediate directories) before writing when it does not already exist. If the
directory or file cannot be created or written due to filesystem permissions, the
store SHALL surface a clear `StateError` rather than silently dropping state.

> ACs: AC-3-015 [CONFIRMED], AC-3-016 [CONFIRMED]
> Business rules: BR-3-006
> Risk: RF-3 (path handling)

#### Scenario: Missing parent directory is created on save (AC-3-015) [CONFIRMED]
- **WHEN** `state_path` points to a not-yet-existing directory and `save(state)` is called
- **THEN** the directory tree is created and the file is written successfully

#### Scenario: Unwritable path surfaces a clear error (AC-3-016) [CONFIRMED]
- **WHEN** the target directory/file is not writable (permission denied) and `save` is called
- **THEN** a clear `StateError` is raised and the failure is reported (state is not silently lost)

### Requirement: Pure persistence boundary
The State Store SHALL be pure persistence: it SHALL NOT call the GitHub Collector, the
LLM/Summarizer, or any network. It SHALL depend only on `osspulse.models` (for
`RawItem`) and the standard library, implementing the existing
`osspulse.ports.StateStore` Protocol. The V1 change SHALL NOT alter the `StateStore`
Protocol signature; `is_seen`/`mark_seen` are concrete adapter helpers only.

> ACs: AC-3-017 [CONFIRMED], AC-3-018 [CONFIRMED]
> Business rules: BR-3-008
> Integration: INT-3-001, INT-3-002

#### Scenario: No network or cross-stage calls (AC-3-017) [CONFIRMED]
- **WHEN** the store loads, records, and saves state
- **THEN** it performs only local filesystem I/O — no GitHub, no LLM, no network call

#### Scenario: Shared Protocol signature is unchanged (AC-3-018) [CONFIRMED]
- **WHEN** the V1 state store is added
- **THEN** `osspulse.ports.StateStore` still declares exactly `load() -> dict` and `save(state: dict) -> None`; the helpers live on the concrete adapter, not the Protocol

