# Proposal: State Store (S3) — ticket 3

## Why
The pipeline (Config → Collector → **State Store** → Summarizer → Render → Deliver)
must be **idempotent**: re-running `osspulse run` over the same window must not
re-emit or (in V2) re-summarize items already seen. V1 needs a durable record of
"what has been seen" so the run is repeatable and crash-safe. State is a **JSON
file** in V1 (no DB), per PROJECT_SPEC §7. This change builds the S3 State Store
adapter behind the existing `osspulse.ports.StateStore` Protocol.

## What Changes
- **NEW** capability `state-store`: a JSON-file-backed implementation of the existing
  `StateStore` Protocol (`load() -> dict`, `save(state: dict) -> None`).
- **NEW** persistence format: a versioned JSON document recording seen items keyed by
  `repo` → `"{item_type}:{item_id}"` → `first_seen_at` (UTC ISO-8601).
- **NEW** thin adapter helpers `is_seen(repo, item_type, item_id) -> bool` and
  `mark_seen(items: list[RawItem]) -> None` on the concrete adapter (NOT added to the
  shared `StateStore` Protocol in V1 — see Non-Goals / deferred to S3 architect).
- **NEW** config field `state_path` (default `./.osspulse/state.json`), config-driven.
- **NEW** atomic write (write-temp-then-`os.replace`) so a crash mid-run cannot
  corrupt the state file (architecture.md "Transaction & Consistency").
- Tolerant load: a missing file → empty state; a corrupt/unreadable file → clear,
  recoverable error (no silent data loss).

## Capabilities
- **New Capabilities**: `state-store` → `openspec/changes/state-store-3/specs/state-store/spec.md`
- **Modified Capabilities**: none. The `StateStore` Protocol in `ports.py` is reused
  unchanged; `github-collector` is not touched (collector is pure I/O, never reads/writes state — AC-2-015).

## Impact
- **Code**: new `src/osspulse/state/` adapter (e.g. `json_store.py`); `osspulse.config.Config`
  gains `state_path`; `models.py`/`ports.py` unchanged.
- **Consumers**: `RawItem` (frozen, from project-foundation) is the input to `mark_seen`;
  identity is `repo` + `item_type` + `item_id` (cross-spec context watch item).
- **Tests**: pytest with a temp-dir state file (no real FS pollution); no external API.
- **No** DB, no Redis (Redis is the *summary* cache, a separate concern), no HTTP API.

Figma: N/A (CLI tool, no UI).

## Assumptions

### [CONFIRMED]
- A-C1 [CONFIRMED]: State persisted as a single JSON file in V1 — Source: PROJECT_SPEC §7, project.md, stack.md.
- A-C2 [CONFIRMED]: `StateStore` Protocol (`load`/`save`) already exists and is the persistence contract; V1 does NOT change the Protocol — Source: `src/osspulse/ports.py`, clarification Q3.
- A-C3 [CONFIRMED]: Item identity = `repo` + `item_type` + `item_id` — Source: cross-spec context watch item + `RawItem` fields.
- A-C4 [CONFIRMED]: State file path is config-driven via `state_path`, default `./.osspulse/state.json` — Source: clarification Q1.
- A-C5 [CONFIRMED]: Each seen record stores identity key + `first_seen_at` (UTC ISO) — Source: clarification Q2.
- A-C6 [CONFIRMED]: Adapter exposes `is_seen` / `mark_seen` helpers without altering the shared Protocol — Source: clarification Q3.

### [ASSUMED]
- A-A1 [ASSUMED]: V1 only **records** seen state (write side); full delta-filtering of items is V2 — Source: PROJECT_SPEC §5/§6 ("V1 ghi", "V2 dùng cho delta"). Inferred scope boundary.
- A-A2 [ASSUMED]: State file is UTF-8 JSON, pretty-or-compact is irrelevant to correctness; the schema carries a `version` field for forward migration — design choice for V2 readiness.
- A-A3 [ASSUMED]: Single-operator, single-process tool — no cross-process file locking required in V1 (last-write-wins within one `osspulse run`) — Source: project.md "personal/self-host tool (single operator)".

## Edge Cases

### Input Boundary
- EC-001: `mark_seen([])` (empty list) → state unchanged, file still valid (no spurious write churn beyond a no-op save).
- EC-002: A `RawItem` with empty-string `item_id` or `title`/`body` → still keyed by `repo:item_type:item_id`; empty `item_id` is treated as a valid (if unusual) key, not a crash (RawItem fields may be empty strings per cross-spec constraint).
- EC-003: Very large state (10k+ seen items across many repos) → load/save still O(n) JSON, no per-item file ops.

### State Transition
- EC-004: First ever run, no state file exists → `load()` returns empty state, run proceeds, file is created on first `save`.
- EC-005: Item already seen in a prior run, seen again → `is_seen` returns true; `mark_seen` does NOT overwrite the original `first_seen_at` (idempotent — preserves earliest-seen).
- EC-006: New item not in state → `is_seen` false; after `mark_seen` it is recorded with current timestamp.

### Concurrency
- EC-007: Crash (process killed) **during** a save → atomic write-temp-then-rename guarantees the old file remains intact; never a half-written/corrupt JSON. (architecture.md)
- EC-008: Two `osspulse run` processes overlap (not expected in V1 single-operator) → last writer wins; no corruption (each does an atomic replace). Documented as out-of-scope for locking (A-A3).

### Data Integrity
- EC-009: State file exists but is empty (0 bytes) → treated as empty state (recoverable), not a hard crash.
- EC-010: State file contains malformed/corrupt JSON → raise a clear `StateError` (readable one-line message, exit 1 per conventions); do NOT silently reset to empty (silent reset = data loss).
- EC-011: State file has an unknown/newer `version` → raise a clear error rather than mis-parsing (forward-compat guard).
- EC-012: State file missing the expected top-level `seen` key (older/foreign shape) → tolerate by treating absent keys as empty, not crashing.

### Permission / Filesystem
- EC-013: `state_path` parent directory does not exist → create it (mkdir -p semantics) before first write; if creation fails (permission), surface a clear error.
- EC-014: State file/dir is not writable (permission denied) → clear `StateError` on save, run reports failure rather than silently dropping state.

### Integration
- EC-015: Collector returns items for a repo never seen before → all are new; `mark_seen` records them under a new `repo` bucket.
- EC-016: A repo is removed from the watchlist → its stale entries remain in state (harmless); V1 does NOT prune (pruning is a possible V2 nicety, out of scope).

## Early Risk Flags
STRIDE config = `auto`; this feature touches no auth/payment/PII/tokens/upload/admin,
so a full STRIDE pass is not triggered. Security-relevant risks specific to a local
state file are still flagged:
- **RF-1 (Tampering / Data integrity)**: a crash mid-write could corrupt state →
  mitigated by atomic write-temp-then-`os.replace` (AC-3-008).
- **RF-2 (Data integrity)**: a corrupt state file could silently reset idempotency
  (re-process everything or lose "seen" history) → mitigated by failing loud on
  malformed JSON rather than silent reset (AC-3-010).
- **RF-3 (Path handling)**: `state_path` is operator-config, not from untrusted
  network input, so SSRF/path-injection is not in scope; still, the parent dir is
  created with normal FS permissions, no elevation.

## Non-Goals
- ❌ NOT a database / SQLite (V2 may migrate; the `version` field exists for that).
- ❌ NOT full delta filtering — V1 records seen state; V2 consumes it for delta.
  Note: V2's delta key is **not yet specified** (no V2 spec exists). The V1 identity
  key (`repo` + `item_type` + `item_id`) is the natural item identity derived from the
  frozen `RawItem`, and `first_seen_at` covers a possible time-based delta. If V2
  needs a different shape, the top-level `version` field is the migration mechanism —
  AC-3-005 stays `[ASSUMED]` until V2 is designed (see _handoff.md §2 WATCH).
- ❌ NOT changing the shared `StateStore` Protocol signature (helpers live on the
  adapter; promoting them to the Protocol is an S3 architect decision).
- ❌ NOT cross-process file locking (single-operator assumption A-A3).
- ❌ NOT pruning stale entries for repos dropped from the watchlist.
- ❌ NOT the Redis summary cache (that is S4's concern, a separate port).
