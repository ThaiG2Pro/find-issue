# S5 QA Report — V2-001 (v2-001-delta-filter)
Date: 2026-07-03
QA Mode: Smart (dev-test-report.md present)

## Gate Checklist
| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% | ✅ 98.55% (QA-independent run: 285 passed) |
| All required tasks `[x]` | ✅ 22/22 (tasks.md verified) |
| Self-review log present | ✅ 4 findings (2 HIGH, 2 MEDIUM) in dev-test-report.md |
| Integration smoke test | ✅ See Step 4C below |
| `.env.example` ≥ 10 lines | ✅ 33 lines |
| `README.md` ≥ 10 lines | ✅ 208 lines |
| Structured logging wired | ✅ `logging.getLogger("osspulse.pipeline")` in pipeline.py; `StateError → exit 1` in cli.py |

## QA-Independent Test Run (Step 4A)
- Command: `uv run pytest tests/test_pipeline.py tests/test_config.py -q` → **55 passed**, 0 failed ✅
- Command: `uv run pytest --cov=osspulse --cov-report=term-missing -q` → **285 passed**, 98.55% ✅
- Count matches dev-test-report.md exactly — dev did not misreport.

## Integration Smoke Tests (Step 4C)
| Scenario | Command / Action | Expected | Result |
|----------|-----------------|----------|--------|
| Invalid config path → exit 1 | `osspulse run --config /nonexistent/config.toml` | `Error: cannot read ... file not found`, exit 1 | ✅ |
| `[delta] enabled = "not_a_bool"` → ConfigError | config with `enabled = "not_a_bool"` | `Error: delta.enabled must be a boolean`, exit 1 | ✅ |
| `[delta]` absent → default true, reaches pipeline | config without `[delta]` section | Proceeds past config load, hits AuthError (expected — fake token) | ✅ |
| `[delta] enabled = false` → reaches pipeline | config with `enabled = false` | Proceeds past config load, hits AuthError (expected — fake token) | ✅ |

Note: full end-to-end delivery not possible without a valid GitHub token in this env. Auth-failure
path confirms config validation passes and delta config is parsed correctly before any network call.

## Test Scenarios (qa-analysis Phase 2 — Spec-TC Gap Review)

All 10 delta ACs and 3 modified living ACs (AC-7-010, AC-7-011, AC-7-019) are covered by
name-referenced tests. Gap map:

| AC-ID | Dev Coverage | QA Gap Assessment | Independent Verify | Result |
|-------|-------------|-------------------|--------------------|--------|
| AC-V2-001-001 | test_delta_first_run_all_new_all_recorded, test_partition_new_reads_only_is_seen_no_writes | COVERED | Code review confirms _partition_new called before mark_seen | ✅ |
| AC-V2-001-002 | test_delta_section_absent_defaults_true, test_delta_enabled_true_explicit | COVERED | config.py _validate_delta defaults True when [delta] absent | ✅ |
| AC-V2-001-003 | test_delta_state_store_protocol_unchanged | COVERED | ports.py inspected — Protocol has only load/save | ✅ |
| AC-V2-001-004 | test_delta_mixed_new_and_seen_snapshot_before_mark_seen | COVERED | R1 tripwire: mark_seen.assert_called_once_with([item_seen, item_new]) | ✅ |
| AC-V2-001-005 | test_delta_empty_after_filter_delivers_no_new_items_doc | COVERED | Delivery not suppressed; "No new items" in digest | ✅ |
| AC-V2-001-006 | test_delta_enabled_false, test_delta_disabled_byte_identical_to_v1, test_delta_mark_seen_count_invariant_both_modes | COVERED — see SHALLOW_TC-001 below | Code review: only `extend()` argument differs | ✅ (with note) |
| AC-V2-001-007 | test_delta_enabled_non_bool_string_raises, test_delta_enabled_int_raises | COVERED | Smoke confirmed via CLI — ConfigError, exit 1 | ✅ |
| AC-V2-001-008 | test_delta_empty_after_filter_delivers_no_new_items_doc | COVERED | deliver.assert_called_once(); digest confirmed non-empty | ✅ |
| AC-V2-001-009 | test_delta_state_error_propagates_not_swallowed | COVERED | AST verified no StateError caught by _collect_all except arms | ✅ |
| AC-V2-001-010 | test_delta_mark_seen_count_invariant_both_modes, test_delta_mixed_new_and_seen_snapshot_before_mark_seen | COVERED | Both tripwire tests confirm mark_seen receives full list | ✅ |
| AC-7-010 | test_delta_mark_seen_count_invariant_both_modes | COVERED | mark_seen count verified for both delta modes | ✅ |
| AC-7-011 | test_delta_disabled_byte_identical_to_v1 | COVERED — see SHALLOW_TC-001 | Code review confirms extend() is the only conditional | ✅ (with note) |
| AC-7-019 | test_delta_mark_seen_still_decoupled_from_summarize_failure | COVERED | mark_seen.assert_called_once_with([item]) before RuntimeError | ✅ |

## Code Review Findings (Step 4B)

### Security Audit (OWASP)

**1. Secrets Management** ✅
- No hardcoded tokens, keys, or secrets in any modified file.
- `_collect_all` logs repo name and error class only — never the raw exception (which could embed a tokened URL). Verified: `logger.warning("skipped %s: %s", repo_name, type(exc).__name__)`.
- `github_token` and `llm_api_key` passed to constructors only, never stored on shared objects (pre-existing pattern, unchanged).
- `.env.example` present (33 lines), `.env` in `.gitignore`.

**2. Input Validation** ✅
- `_validate_delta`: `type(value) is not bool` guard — rejects `1`, `"yes"`, `None`. Confirmed via unit tests and CLI smoke.
- Bool-trap correctly mirrors `_validate_lookback` (no `isinstance` which would accept `True` as `int`).

**3. SQL Injection** N/A
- No database in this project. State is a JSON file, no query construction.

**4. Auth / Authorization** N/A
- CLI tool, no user-facing API. Auth guard is GitHub token at constructor only.

**5. Logging Security** ✅
- All 6 logger calls in pipeline.py verified: none log token, api_key, raw exception, or PII.
- New log line: `"collected %d item(s) from %s (seen=%d new=%d)"` — counts only, no content.
- Run-summary: `"run complete — repos: %d, collected: %d, seen: %d, new: %d, summarized: %d, skipped: %d"` — counts only.

**6. XSS / Headers / File Upload** N/A — CLI tool.

**7. OWASP A06 — Vulnerable Components** ✅
- `uv tool run pip-audit --desc`: **No known vulnerabilities found**.

### ADR-003 Structural Verification (StateError propagation)
AST analysis of `_collect_all`'s except arms:
- Line 183: `except AuthError`
- Line 189: `except RateLimitError`
- Line 198: `except (InvalidRepoError, NetworkError, CollectorError)`
- `StateError` (inherits `Exception` directly) is in **none** of these. ✅
- The only `except Exception` in the file is `_build_cache` Redis degradation (pre-existing, unrelated). ✅

### AC-V2-001-006 Byte-Identical Guarantee
Code review of `_collect_all`:
```python
all_items.extend(new if config.delta_enabled else items)
```
This is the **only** line in the entire function body that references `config.delta_enabled`.
No other conditional on `delta_enabled` exists in `_collect_all` or `run_pipeline`. ✅

### R1 Ordering (ADR-001)
Exact order in `_collect_all` hot loop:
1. `items = collector.fetch_items(...)` — fetch
2. `new, seen = _partition_new(items, state)` — snapshot BEFORE write
3. `state.mark_seen(items)` — write full list
4. `all_items.extend(new if config.delta_enabled else items)` — select for render

`mark_seen(items)` — full `items` list, never `new`. ✅

### `_partition_new` Identity-Only (BR-V2-001-004, EC-005)
```python
if state.is_seen(item.repo, item.item_type, item.item_id):
```
Key = `(repo, item_type, item_id)` only. No content comparison, no hashing, no `item.body`/`item.title` access. ✅

## Test Quality Review — Step B1 (Hollow Assertion Analysis)

| Test | H1 (existence only) | H1-b (log without caplog) | H1-c (delivered-not-what) | H4 (BVA missing) | Assessment |
|------|---------------------|--------------------------|---------------------------|------------------|------------|
| test_delta_first_run_all_new_all_recorded | — | — | — (content checked per-item) | — | ✅ SOLID |
| test_delta_mixed_new_and_seen_snapshot_before_mark_seen | — | — | — (content + not-in) | — | ✅ SOLID — R1 tripwire |
| test_delta_empty_after_filter_delivers_no_new_items_doc | — | — | `.assert_called_once()` then content checked | — | ✅ SOLID |
| test_delta_mark_seen_count_invariant_both_modes | — | — | content checked both branches | — | ✅ SOLID — R1 tripwire |
| test_delta_disabled_byte_identical_to_v1 | — | — | ⚠ See SHALLOW_TC-001 | — | ⚠ SHALLOW |
| test_delta_state_error_propagates_not_swallowed | — | — | — (pytest.raises) | — | ✅ SOLID |
| test_delta_state_store_protocol_unchanged | — | — | — (structural check) | — | ✅ SOLID |
| test_delta_mark_seen_still_decoupled_from_summarize_failure | — | — | — (mark_seen arg asserted) | — | ✅ SOLID |
| test_partition_new_reads_only_is_seen_no_writes | — | — | — (new/seen lists + no-writes asserted) | — | ✅ SOLID |

**All pre-existing fixtures**: verified by script — all 13 tests using `mock_state` have explicit
`is_seen.return_value = False` or `is_seen.side_effect`. Zero bare `MagicMock()` without `is_seen`
contract. ✅

## Bug List

| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| — | — | — | — | — | — |

### Shallow TC Finding (not a code bug — test quality only)

**SHALLOW_TC-001: test_delta_disabled_byte_identical_to_v1 only verifies False→False idempotency, not False==(V1-equivalent)**

AC-V2-001-006 wording: "the digest is byte-identical to a V1 run over the same items."
The test runs `_run(delta_enabled=False)` twice and asserts the two results are equal to each
other — it proves the False-path is deterministic (idempotent), but it doesn't explicitly
compare a `delta_enabled=False` run against a `delta_enabled=True` first-run (where `is_seen`
is all-False, same as V1 empty-state behavior).

Severity: Low (the code review confirms `extend(new if delta_enabled else items)` is the only
delta conditional — a code change that broke the False==V1 equivalence would be caught by
`test_delta_mark_seen_count_invariant_both_modes` which already runs both modes over the same
items). Classification: [AI-DETECTABLE]. RCA: S4 test authoring.

This does NOT block GO — the AC is sufficiently covered by the combination of the byte-identical
test (determinism), the mark_seen-count invariant test (both modes over same input), and the
code review (single conditional). Recorded as a future test-improvement opportunity.

## AC Coverage Summary
- Total ACs: 10 delta (AC-V2-001-001..010) + 3 modified living (AC-7-010, AC-7-011, AC-7-019)
- Covered by Dev unit tests: 13/13
- Independently verified by QA this session: 13/13 (code review + test review + smoke)
- Not covered: 0
- One AC-V2-001-003 is [ASSUMED] (Protocol unchanged by design intention) — verified by code
  review of `ports.py` and AST check: is_seen/mark_seen not on Protocol. Acceptable.

## CMS UI Visual QA
N/A — CLI tool. No Figma URL present in specs or design.md.

## Dependency Vulnerability Audit
`uv tool run pip-audit --desc` → **No known vulnerabilities found** (0 HIGH, 0 CRITICAL, 0 MODERATE). ✅

## Decision: GO ✅

**Rationale:**
- 0 Critical bugs, 0 High bugs
- All 10 delta ACs + 3 living ACs independently verified by code review, test review, and smoke tests
- 285 tests passing (QA-independent run), 98.55% coverage (floor 80%)
- R1 tripwire tests confirmed solid — mark_seen full-list assertion intact in both tripwire tests
- StateError propagation verified structurally (AST) and by test
- delta_enabled=false byte-identical guarantee confirmed (single conditional in extend())
- Security: no PII/secret in logs, no injection surface, no hardcoded secrets, dep audit clean
- One SHALLOW_TC-001 (Low, [AI-DETECTABLE]) logged — does not block GO, does not misrepresent the AC

## Blockers
None.
