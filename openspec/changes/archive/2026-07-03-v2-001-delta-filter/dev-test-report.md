## Dev Test Report — V2-001-delta-filter
Date: 2026-07-03

### Unit Test Coverage
| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| src/osspulse/models.py | 36 | 0 | 100% |
| src/osspulse/config.py | 87 | 2 | 98% |
| src/osspulse/pipeline.py | 84 | 2 | 98% |
| **Overall (whole project)** | **689** | **10** | **98.55%** |

Command: `uv run pytest --cov=osspulse --cov-report=term-missing` — 285 passed. Project floor
is ≥80% lines (`context/stack.md`); result clears it with margin. The 2 uncovered lines in
`config.py` (87-89) and 2 in `pipeline.py` (95, 266) are pre-existing paths unrelated to this
change (LLM-key resolution edge case, Redis-connect-success branch, FileDelivery branch).

### AC Coverage by Tests
| AC-ID | Test File | Test Name | Status |
|-------|-----------|-----------|--------|
| AC-V2-001-001 | test_pipeline.py | test_delta_first_run_all_new_all_recorded | ✅ PASS |
| AC-V2-001-001 | test_pipeline.py | test_partition_new_reads_only_is_seen_no_writes | ✅ PASS |
| AC-V2-001-002 | test_config.py | test_delta_section_absent_defaults_true | ✅ PASS |
| AC-V2-001-002 | test_config.py | test_delta_enabled_true_explicit | ✅ PASS |
| AC-V2-001-003 | test_pipeline.py | test_delta_state_store_protocol_unchanged | ✅ PASS |
| AC-V2-001-004 | test_pipeline.py | test_delta_mixed_new_and_seen_snapshot_before_mark_seen | ✅ PASS |
| AC-V2-001-005 | test_pipeline.py | test_delta_empty_after_filter_delivers_no_new_items_doc | ✅ PASS |
| AC-V2-001-006 | test_config.py | test_delta_enabled_false | ✅ PASS |
| AC-V2-001-006 | test_pipeline.py | test_delta_disabled_byte_identical_to_v1 | ✅ PASS |
| AC-V2-001-006 | test_pipeline.py | test_delta_mark_seen_count_invariant_both_modes | ✅ PASS |
| AC-V2-001-007 | test_config.py | test_delta_enabled_non_bool_string_raises | ✅ PASS |
| AC-V2-001-007 | test_config.py | test_delta_enabled_int_raises | ✅ PASS |
| AC-V2-001-008 | test_pipeline.py | test_delta_empty_after_filter_delivers_no_new_items_doc | ✅ PASS |
| AC-V2-001-009 | test_pipeline.py | test_delta_state_error_propagates_not_swallowed | ✅ PASS |
| AC-V2-001-010 | test_pipeline.py | test_delta_mark_seen_count_invariant_both_modes | ✅ PASS |
| AC-V2-001-010 | test_pipeline.py | test_delta_mixed_new_and_seen_snapshot_before_mark_seen | ✅ PASS |
| AC-7-010 | test_pipeline.py | test_delta_mark_seen_count_invariant_both_modes | ✅ PASS |
| AC-7-011 | test_pipeline.py | test_delta_disabled_byte_identical_to_v1 | ✅ PASS |
| AC-7-019 | test_pipeline.py | test_delta_mark_seen_still_decoupled_from_summarize_failure | ✅ PASS |

All 10 delta ACs (AC-V2-001-001..010) + the 3 modified/regression ACs (AC-7-010, AC-7-011,
AC-7-019) have at least one green test referencing their AC-ID by name.

### Pipeline / Config Test Results (delta-filter-specific, full list)
| Test | Status |
|------|--------|
| test_delta_first_run_all_new_all_recorded | ✅ PASS |
| test_delta_mixed_new_and_seen_snapshot_before_mark_seen | ✅ PASS |
| test_delta_empty_after_filter_delivers_no_new_items_doc | ✅ PASS |
| test_delta_mark_seen_count_invariant_both_modes | ✅ PASS |
| test_delta_disabled_byte_identical_to_v1 | ✅ PASS |
| test_delta_state_error_propagates_not_swallowed | ✅ PASS |
| test_delta_state_store_protocol_unchanged | ✅ PASS |
| test_delta_mark_seen_still_decoupled_from_summarize_failure | ✅ PASS |
| test_partition_new_reads_only_is_seen_no_writes | ✅ PASS |
| test_delta_section_absent_defaults_true | ✅ PASS |
| test_delta_enabled_false | ✅ PASS |
| test_delta_enabled_true_explicit | ✅ PASS |
| test_delta_enabled_non_bool_string_raises | ✅ PASS |
| test_delta_enabled_int_raises | ✅ PASS |

### Regression Results (pre-existing suite, full project)
- `uv run pytest -q` (project-wide): **285 passed**, 0 failed.
- `tests/test_pipeline.py` (all 27, including 18 pre-existing V1 flows): all green after fixture
  update (see Design Deviations).
- `tests/test_config.py` (all 33, including 28 pre-existing): all green.

### Self-Review Findings
| Severity | Finding | Resolution |
|----------|---------|------------|
| [HIGH] | R1 ordering risk — `_partition_new` must run before `mark_seen`, sharing the store's `_cached` dict | Verified structurally in `json_store.py` (`is_seen`/`mark_seen` both read/write `self._cached`); placed `_partition_new` call between `fetch_items` and `mark_seen` per ADR-001; added 2 tests asserting `mark_seen.assert_called_once_with(<full items>)` as the tripwire (AC-V2-001-010) |
| [HIGH] | `StateError` silent-catch risk (AC-V2-001-009) | No try/except added around `is_seen`/`_partition_new`/`load`; added inline comment (ADR-003) + `test_delta_state_error_propagates_not_swallowed` asserting `pytest.raises(StateError)` escapes `run_pipeline` and `mark_seen` is never reached |
| [MEDIUM] | 12 pre-existing `test_pipeline.py` fixtures used bare `mock_state = MagicMock()`; default `is_seen(...)` return is a truthy `MagicMock`, which after adding `_partition_new` made every V1-flow test treat all items as already-seen (4 tests failed on first run) | Added `mock_state.is_seen.return_value = False` to all 12 fixtures — restores original "nothing seen yet" V1 semantics; logged in `_decisions.jsonl` (this is the same class of stub→real mocking-boundary issue noted in `memory/developer.md`) |
| [MEDIUM] | Identity-vs-content scope creep risk (BR-V2-001-004, EC-005) | `_partition_new` compares `(repo, item_type, item_id)` only via `is_seen`; no hashing/content diff added anywhere |

### Design Deviations
None from `design.md` / ADR-001..004. One test-infrastructure fix (not a design deviation,
logged as `type: implementation` in `_decisions.jsonl`): updated 12 pre-existing
`test_pipeline.py` mock fixtures to set `is_seen.return_value = False`, required because the
new `_partition_new` call reads `is_seen` on every mocked `mock_state` and a bare `MagicMock()`
default is truthy.

### Known Limitations
None. All 10 delta ACs + the 3 touched V1 ACs (AC-7-010, AC-7-011, AC-7-019) have passing tests.

### Coverage Verification
- Command: `uv run pytest --cov=osspulse --cov-report=term-missing`
- Result: ✅ PASS — 285 passed, 0 failed
- Overall: 98.55% lines (project floor: ≥80%)
- Lint: `uv run ruff check src tests` → ✅ PASS (0 errors)
- Format: `uv run ruff format --check src tests` → ✅ PASS (all files formatted)
- `openspec change validate "v2-001-delta-filter"`: see S4 gate step (run separately below)
