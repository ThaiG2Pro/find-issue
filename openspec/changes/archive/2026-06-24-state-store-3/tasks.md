# Tasks — state-store-3 (S3 State Store)

> Order: data/errors → models/config wiring → adapter logic → tests.
> Checkpoints are human-review gates — STOP and wait for the user.

## 1. Errors & Data Layer

- [x] 1.1 Create `StateError(Exception)` for corrupt/unwritable state.
  File: `src/osspulse/state/errors.py`
  _Requirements: AC-3-009, AC-3-010, AC-3-016_

- [x] 1.2 Add `state_path: str = "./.osspulse/state.json"` field to the `Config` frozen dataclass (default keeps existing call-sites valid).
  File: `src/osspulse/models.py`
  _Requirements: AC-3-013_

- [x] 1.3 Read optional `state_path` from TOML in `load_config` (default applies when omitted); pass through to the returned `Config`.
  File: `src/osspulse/config.py`
  _Requirements: AC-3-013_

## 2. State Store Adapter — load + helpers

- [x] 2.1 Scaffold `JsonFileStateStore.__init__(state_path)` + internal `_identity_key(item_type, item_id) -> "{item_type}:{item_id}"` and `now_utc_z()` (UTC ISO with trailing `Z`).
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-003, AC-3-005_

- [x] 2.2 Implement `load() -> dict`: missing file → empty `{"version":1,"seen":{}}`; 0-byte / whitespace-only → empty (check before `json.loads`); missing `seen` key → tolerate as empty.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-002, AC-3-011, AC-3-012_

- [x] 2.3 In `load()`: raise `StateError` on malformed JSON (do NOT reset/overwrite the file) and on unknown/newer `version` (expected `1`).
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-009, AC-3-010_

- [x] 2.4 Implement `is_seen(repo, item_type, item_id) -> bool` against the lazily-loaded state; distinct entries for same `item_id` differing in `repo`/`item_type`; empty `item_id` keys safely.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-003, AC-3-005_

## 3. CHECKPOINT — mid-build review

- [x] 3.1 CHECKPOINT: run `ruff check` + `ruff format --check`, run partial tests for load/is_seen. Verify corrupt-vs-empty boundary behaves per design Sequence Flow 1. STOP for user review before implementing save/atomic-write.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-002, AC-3-009, AC-3-010, AC-3-011, AC-3-012_

## 4. State Store Adapter — atomic save + mark_seen

- [x] 4.1 Implement `save(state)`: `mkdir(parents=True, exist_ok=True)` on `state_path.parent` BEFORE opening temp file; serialize the `{version,seen}` document as UTF-8.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-001, AC-3-014, AC-3-015_

- [x] 4.2 Make `save` atomic: `tempfile.NamedTemporaryFile(dir=state_path.parent, delete=False)` → write → `flush` → `os.fsync` → close → `os.replace(tmp, state_path)`; on error `os.unlink(tmp)` then raise `StateError`.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-007, AC-3-008, AC-3-016_

- [x] 4.3 Implement `mark_seen(items)`: add not-yet-seen items with `now_utc_z()`; never overwrite existing `first_seen_at`; empty list is a safe no-op; persist via atomic `save`.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-003, AC-3-004, AC-3-006_

- [x] 4.4 Enforce the pure-persistence boundary: import only `osspulse.models`, `state.errors`, and stdlib — no collector/LLM/network imports; do NOT change the `StateStore` Protocol signature.
  File: `src/osspulse/state/json_store.py`
  _Requirements: AC-3-017, AC-3-018_

## 5. Tests

- [x] 5.1 Round-trip + path tests: save→load equivalence; `state_path` from config drives target (use `tmp_path`); document carries `version:1` + `seen`.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-001, AC-3-013, AC-3-014_

- [x] 5.2 Identity + idempotency tests: new item recorded then `is_seen` true; re-mark preserves original `first_seen_at`; same `item_id` differing repo/type are distinct; empty `item_id` keys safely; `mark_seen([])` no-op.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-003, AC-3-004, AC-3-005, AC-3-006_

- [x] 5.3 Corrupt-vs-empty tests: missing file → empty; 0-byte → empty; missing `seen` → empty; malformed JSON → `StateError` (file untouched); unknown `version` → `StateError`.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-002, AC-3-009, AC-3-010, AC-3-011, AC-3-012_

- [x] 5.4 Atomic + filesystem tests: missing parent dir created on save; interrupted write leaves prior valid file (simulate replace failure / inspect temp-then-replace); unwritable path → `StateError`.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-007, AC-3-008, AC-3-015, AC-3-016_

- [x] 5.5 Boundary test: no network/cross-stage calls (assert no collector/LLM import or invocation); `osspulse.ports.StateStore` still declares exactly `load`/`save`.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-017, AC-3-018_

## 6. CHECKPOINT — final review

- [x] 6.1 CHECKPOINT (final): full `pytest` with coverage ≥ 80% lines / ≥ 80% branches (≥ 90% on changed lines); `ruff check` + `ruff format --check` clean; confirm all 18 ACs (AC-3-001…AC-3-018) covered. STOP for user sign-off before S5.
  File: `tests/test_state_store.py`
  _Requirements: AC-3-001, AC-3-002, AC-3-003, AC-3-004, AC-3-005, AC-3-006, AC-3-007, AC-3-008, AC-3-009, AC-3-010, AC-3-011, AC-3-012, AC-3-013, AC-3-014, AC-3-015, AC-3-016, AC-3-017, AC-3-018_
