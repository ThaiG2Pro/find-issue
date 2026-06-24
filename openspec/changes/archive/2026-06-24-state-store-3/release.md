# Release Notes — state-store-3 (ticket 3)

**Change**: `state-store-3`
**Branch**: `feature/3-state-store`
**Date**: 2026-06-24
**QA Decision**: GO (S5-retest, 18/18 ACs, 119/119 tests, 98.94% lines / 98.21% branches)

---

## What Shipped

### V1 JSON-file State Store (`src/osspulse/state/`)

The pipeline's S3 stage is now fully implemented. `osspulse run` can record "what has been seen" to enable idempotency — re-running over the same window will not re-emit or re-summarize already-seen items in V2.

#### New files
- `src/osspulse/state/errors.py` — `StateError` exception class (mirrors `ConfigError` per-module pattern)
- `src/osspulse/state/json_store.py` — `JsonFileStateStore`: concrete implementation of the existing `osspulse.ports.StateStore` Protocol

#### Modified files
- `src/osspulse/config.py` — `Config` dataclass gains `state_path: str` field (default `"./.osspulse/state.json"`); `load_config` reads an optional `[state].state_path` key from TOML
- `src/osspulse/models.py` — minor: no functional change (fields already existed; this change added no new model fields)

#### New test file
- `tests/test_state_store.py` — 119 tests total (38 original + 5 BUG-001 regression tests + existing suite); all ACs tagged with AC-ID per R3

#### Capabilities delivered (18 ACs)

| AC | Description |
|----|-------------|
| AC-3-001 | `save` → `load` round-trip returns equivalent dict |
| AC-3-002 | Missing file → empty state, no file created until first `save` |
| AC-3-003 | New item recorded via `mark_seen`; `is_seen` subsequently true; `first_seen_at` UTC-Z timestamp |
| AC-3-004 | Re-marking an already-seen item preserves original `first_seen_at` (idempotent) |
| AC-3-005 | Item identity = `repo` + `"{item_type}:{item_id}"`; same `item_id` in different repo/type = distinct entries |
| AC-3-006 | `mark_seen([])` is a safe no-op; state and file unchanged |
| AC-3-007 | `save` writes via temp file in same directory, then `os.replace` (atomic rename) |
| AC-3-008 | Interrupted write leaves prior valid file intact; no half-written JSON at `state_path` |
| AC-3-009 | Malformed JSON (including syntactically valid but structurally non-dict roots: `null`, `[]`, `42`, `"string"`) raises `StateError`; corrupt file is NOT overwritten |
| AC-3-010 | Unknown/newer `version` in state file raises `StateError` instead of mis-parsing |
| AC-3-011 | Zero-byte or whitespace-only file → empty state, no error |
| AC-3-012 | State document missing the top-level `seen` key → treated as empty, no crash |
| AC-3-013 | `state_path` read from `Config`; default `./.osspulse/state.json`; no hardcoding in adapter |
| AC-3-014 | Saved document carries integer `version: 1` and `seen` object at top level |
| AC-3-015 | Missing parent directory created (`mkdir -p`) on first `save` |
| AC-3-016 | Unwritable path or failed `mkdir` raises `StateError`; state never silently dropped |
| AC-3-017 | State store performs only local filesystem I/O; no GitHub, no LLM, no network |
| AC-3-018 | `osspulse.ports.StateStore` Protocol signature unchanged (`load() -> dict`, `save(state: dict) -> None`); `is_seen`/`mark_seen` are concrete adapter helpers only |

#### Key design decisions (ADRs)
- **ADR-001**: `is_seen`/`mark_seen` live on the concrete `JsonFileStateStore`, not on the shared `StateStore` Protocol (AC-3-018 forbids altering the Protocol in V1).
- **ADR-002**: Atomic write via temp file in `state_path.parent` + `os.fsync` + `os.replace` (same filesystem guaranteed; mitigates RF-1 crash-corruption).
- **ADR-003**: `StateError` defined in `src/osspulse/state/errors.py` (mirrors `ConfigError`; self-contained; reusable for future adapters).
- **ADR-004**: No `openapi.yaml` (CLI-only change; no inbound HTTP surface).

#### Bug fixed in S4-FIX (before S5 GO)
- **BUG-001 / FIX-001** (High, AC-3-009): `load()` now has an `isinstance(data, dict)` guard between the `JSONDecodeError` catch and the version check. Syntactically-valid but structurally-non-dict JSON roots (`null`, `[]`, `42`, `"string"`) previously raised `AttributeError`; they now correctly raise `StateError`. Five regression tests added and verified at 100% branch coverage.

---

## Migration Checklist

**No database migrations.** This is a V1 JSON-file store — no DB server, no ORM, no schema.

| Item | Status | Notes |
|------|--------|-------|
| DB migrations | N/A | V1 is a JSON file; no DB involved |
| Config breaking change | None | `Config.state_path` has a default (`"./.osspulse/state.json"`); existing `Config(...)` call-sites that do not pass `state_path` are unaffected |
| TOML config files | Non-breaking | Existing `config.toml` files without a `[state]` section continue to work; the default path is used |
| State file format | New (version=1) | First run creates `.osspulse/state.json` with `{"version": 1, "seen": {}}`. The `version` integer field is the migration path for V2 if the schema changes |
| Ports interface | Unchanged | `osspulse.ports.StateStore` Protocol signature is identical to before this change |

---

## Rollback Plan

This is a CLI/library change with no running server, no DB migration, and no deployed artifact to roll back independently.

**Rollback = `git revert` the feature branch merge.**

Steps:
1. `git revert -m 1 <merge-commit-sha>` (or `git revert <commit>` if the branch was squash-merged)
2. The revert removes `src/osspulse/state/`, restores the pre-change `config.py` (without `state_path`), and restores `models.py`.
3. Any state files already written to disk (`.osspulse/state.json` or operator-configured paths) are standalone JSON files — they are NOT deleted by the revert and do not interfere with the reverted code (the reverted code simply does not import the state module).
4. Operators who created a `[state]` section in their `config.toml` will get an "unrecognized key" warning from `load_config` after rollback (the key is ignored; the TOML parser does not error on unknown sections in the current implementation).

**State-file safety**: The `version: 1` top-level field means a future V2 migrator can detect and handle V1 files cleanly. Rolling back does not corrupt or lose state data — the JSON file remains on disk unchanged.

**No rollback of external systems required** — no DB, no migration, no cache key schema change, no API surface change.

---

## Post-Deploy Smoke Test

After merging the branch, verify the following on a clean environment:

1. **Import check**: `python -c "from osspulse.state.json_store import JsonFileStateStore; from osspulse.state.errors import StateError; print('OK')"` — should print `OK` with no import error.

2. **Round-trip**: Run `uv run pytest tests/test_state_store.py -q` — should report 119 passed.

3. **Save→load round-trip (manual)**:
   ```python
   import tempfile, pathlib
   from osspulse.config import Config
   from osspulse.state.json_store import JsonFileStateStore
   with tempfile.TemporaryDirectory() as d:
       cfg = Config(state_path=str(pathlib.Path(d) / "state.json"))
       store = JsonFileStateStore(cfg)
       store.save({"version": 1, "seen": {"myorg/myrepo": {"issue:1": "2026-06-24T00:00:00Z"}}})
       state = store.load()
       assert state["seen"]["myorg/myrepo"]["issue:1"] == "2026-06-24T00:00:00Z"
       print("round-trip OK")
   ```

4. **Corrupt state raises `StateError` (not a traceback)**:
   ```python
   import tempfile, pathlib
   from osspulse.config import Config
   from osspulse.state.json_store import JsonFileStateStore
   from osspulse.state.errors import StateError
   with tempfile.TemporaryDirectory() as d:
       p = pathlib.Path(d) / "bad.json"
       p.write_text("null")
       cfg = Config(state_path=str(p))
       store = JsonFileStateStore(cfg)
       try:
           store.load()
           print("FAIL — expected StateError")
       except StateError as e:
           print(f"StateError raised correctly: {e}")
   ```
   Should print `StateError raised correctly: state file is corrupt: ...` — not an `AttributeError` traceback.

5. **Full suite**: `uv run pytest tests/ --cov=src/osspulse --cov-branch -q` — 119 passed, coverage ≥ 98%.

---

## Deploy Strategy

**No server deployment.** OSS Pulse V1 is a CLI tool installed locally by the operator.

| Concern | Detail |
|---------|--------|
| Deploy method | Merge `feature/3-state-store` → `main` via PR |
| Server restart | N/A (no server) |
| Cron / scheduler | N/A (V2 feature) |
| Docker image | N/A (V1 has no image) |
| Environment variables | None new. `GITHUB_TOKEN` and any LLM key are pre-existing; no new env var is required for the state store (path is config-driven) |
| Operator action after merge | None required. First `osspulse run` creates `.osspulse/state.json` automatically if it does not exist |
| Parallel run risk | None in V1 (single-operator, single-process assumption A-A3). Atomic write-then-replace means even accidental concurrent runs will not corrupt the file |

---

## Open Project-Level Debt (not a blocker for this release)

Tracked by the orchestrator separately from state-store-3:
- `.env.example` has fewer than 10 lines (pre-existing)
- No `README.md` at project root (pre-existing)
- Structured logging not JSON-formatted in CLI entrypoint (pre-existing)
