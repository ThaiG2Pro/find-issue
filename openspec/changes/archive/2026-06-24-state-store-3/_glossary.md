| Term | Definition | Phase | Source |
|------|------------|-------|--------|
| State store | The S3 component persisting "what has been seen" to enable idempotency (V1) and delta (V2); a single JSON file in V1 | S1 | PROJECT_SPEC §6/§7, project.md |
| Seen item | An item (issue in V1) already recorded by the state store, keyed by `repo` + `item_type` + `item_id` | S1 | clarification Q2/Q3 |
| Identity key | The stable key for a seen item: `repo` → `"{item_type}:{item_id}"` | S1 | cross-spec context, RawItem fields |
| first_seen_at | UTC ISO-8601 timestamp with trailing `Z` (e.g. `2026-06-24T13:05:00Z`), recorded the first time an item is marked seen; never overwritten on re-mark | S1/S2 | clarification Q2 |
| state_path | Config field for the JSON state file location; default `./.osspulse/state.json` | S1 | clarification Q1 |
| Atomic write | Write-to-temp-then-`os.replace` strategy ensuring a crash mid-write never corrupts the state file | S1 | architecture.md, clarification |
| version (state) | Top-level integer field in the state JSON document marking the format version; V1 = `1`. Shape: `{"version":1,"seen":{...}}` | S1/S2 | A-A2 design choice |
| StateError | The clear, readable error raised on corrupt/unwritable state; surfaced as `Error: <msg>` exit 1 | S1 | conventions.md |
| is_seen / mark_seen | Concrete adapter helpers (NOT on the shared Protocol in V1) for dedup ergonomics | S1 | clarification Q3 |
| JsonFileStateStore | The V1 concrete state-store adapter (`src/osspulse/state/json_store.py`) implementing the `StateStore` Protocol structurally | S3 | ADR-001 |
| Atomic-write recipe | `tempfile.NamedTemporaryFile(dir=state_path.parent)` → write → flush → `os.fsync` → `os.replace` | S3 | ADR-002 |
| Corrupt-vs-empty boundary | Parse failure / bad version = loud `StateError`; absent/0-byte/missing-`seen` = empty state | S3 | design Sequence Flow 1 |
