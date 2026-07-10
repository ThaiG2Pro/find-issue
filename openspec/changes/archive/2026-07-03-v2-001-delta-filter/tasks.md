## 1. Config field (data/model layer)

- [x] 1.1 Add `delta_enabled: bool = True` field to the `Config` dataclass (place after `output_path`, keep frozen dataclass)
  - File: `src/osspulse/models.py`
  - _Requirements: AC-V2-001-002_

## 2. Config parsing & validation

- [x] 2.1 Add `_validate_delta(data: dict) -> bool` helper: read `data.get("delta", {})`, default `enabled` to `True`, raise `ConfigError("delta.enabled must be a boolean")` when `type(value) is not bool` (add `# noqa: E721`, mirroring `_validate_lookback`)
  - File: `src/osspulse/config.py`
  - _Requirements: AC-V2-001-002, AC-V2-001-007_
- [x] 2.2 Call `_validate_delta(data)` in `load_config` and pass `delta_enabled=` into the `Config(...)` return (fail-fast at load time, before the pipeline runs)
  - File: `src/osspulse/config.py`
  - _Requirements: AC-V2-001-002, AC-V2-001-007_

## 3. Checkpoint — config layer review

- [x] 3.1 CHECKPOINT: Run `pytest tests/test_config.py` + `ruff check src/osspulse/config.py src/osspulse/models.py`. Verify `[delta]` default-true, `enabled=false`, and non-bool→ConfigError all behave. STOP for human review before touching the pipeline.
  - File: `tests/test_config.py`
  - _Requirements: AC-V2-001-002, AC-V2-001-007_

## 4. Delta filter (pipeline orchestration)

- [x] 4.1 Add module-private `_partition_new(items: list[RawItem], state: JsonFileStateStore) -> tuple[list[RawItem], list[RawItem]]` returning `(new, seen)`, reading only `state.is_seen(item.repo, item.item_type, item.item_id)` (read-only, no writes)
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-001-001, AC-V2-001-004, AC-V2-001-003_
- [x] 4.2 In `_collect_all`, insert `new, seen = _partition_new(items, state)` BETWEEN `fetch_items` and `state.mark_seen(items)`; leave `mark_seen(items)` exactly where it is (records ALL collected items unconditionally)
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-001-004, AC-V2-001-010, AC-7-010, AC-7-019_
- [x] 4.3 Change the accumulation to select the render-list: `all_items.extend(new if config.delta_enabled else items)`; pass `config` into `_collect_all` (already available) — never re-query `is_seen` after `mark_seen`
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-001-001, AC-V2-001-005, AC-V2-001-006, AC-7-011_
- [x] 4.4 Extend the run-summary log line with `seen`/`new` counts (e.g. `collected=N seen=M new=N-M`); keep one-line-per-run, never log raw exceptions or secrets
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-001-010_
- [x] 4.5 Verify NO try/except is added around `is_seen`/`_partition_new`/`load` so `StateError` propagates to the CLI (which already maps it to `Error: <msg>` exit 1); add an inline comment noting this is intentional (ADR-003)
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-001-009_

## 5. Config tests

- [x] 5.1 Test `[delta]` absent → `load_config` returns `Config(delta_enabled=True)`
  - File: `tests/test_config.py`
  - _Requirements: AC-V2-001-002_
- [x] 5.2 Test `[delta] enabled = false` → `Config(delta_enabled=False)`
  - File: `tests/test_config.py`
  - _Requirements: AC-V2-001-006_
- [x] 5.3 Test `[delta] enabled = "yes"` (and `= 1`) → raises `ConfigError` before the pipeline runs (bool-trap guard)
  - File: `tests/test_config.py`
  - _Requirements: AC-V2-001-007_

## 6. Pipeline tests

- [x] 6.1 Test first run against empty/missing state (3 new issues, `delta_enabled=true`) → all 3 rendered AND all 3 recorded via `mark_seen`
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-001_
- [x] 6.2 Test mixed new+seen in one run (#6 new, #5 seen, `delta_enabled=true`) → only #6 rendered, BOTH #5 and #6 recorded (snapshot taken before mark_seen)
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-004_
- [x] 6.3 Test second run with no new activity → filtered list empty, `render([])` returns "no new items" doc, doc delivered once, exit 0 (delivery never suppressed)
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-005, AC-V2-001-008_
- [x] 6.4 Test `mark_seen` invoked exactly N times (N=collected) for BOTH `delta_enabled=true` and `false` over the same mixed input; render-count differs (N vs N−M), record-count identical
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-010, AC-7-010_
- [x] 6.5 Test `delta_enabled=false` over already-seen issues → all rendered, digest byte-identical to a V1 run over the same items
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-006, AC-7-011_
- [x] 6.6 Test a `StateError` raised by the state store during collection propagates out of `run_pipeline` (not swallowed, filter not silently disabled) → CLI-level `Error:`/exit 1
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-009_
- [x] 6.7 Test `StateStore` Protocol + `is_seen`/`mark_seen` signatures unchanged (delta calls `is_seen` from pipeline only; no Protocol method added)
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-003_
- [x] 6.8 Test `mark_seen` decoupled from summarization outcome: an item marked seen whose summarize fails stays recorded and the run continues (regression guard for AC-7-019)
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-7-019_

## 7. Docs

- [x] 7.1 Update README config schema with the `[delta]` section + a note that re-runs suppress previously-seen items (and `enabled=false` restores V1)
  - File: `README.md`
  - _Requirements: AC-V2-001-002, AC-V2-001-006_

## 8. Checkpoint — final QA gate

- [x] 8.1 CHECKPOINT: Run full `pytest` with coverage (≥80% lines, project floor) + `ruff check src tests`. Confirm all 10 delta ACs + AC-7-010/011/019 covered, mark_seen-count invariant green, StateError propagation green, delta-off byte-identical green. STOP for human review before S5.
  - File: `tests/test_pipeline.py`
  - _Requirements: AC-V2-001-001, AC-V2-001-002, AC-V2-001-003, AC-V2-001-004, AC-V2-001-005, AC-V2-001-006, AC-V2-001-007, AC-V2-001-008, AC-V2-001-009, AC-V2-001-010_
