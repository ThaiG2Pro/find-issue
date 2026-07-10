# Dev Test Report — V2-003 v2-003-releases

**Change**: v2-003-releases — GitHub Releases as first-class source
**Phase**: S4 Build
**Date**: 2026-07-06
**Developer**: developer agent

---

## Summary

All 13 tasks completed. GitHub Releases are now collected alongside issues in the OSS Pulse
pipeline. Two files modified (`client.py`, `pipeline.py`), three test files created/extended.
All invariants from ADR-001, ADR-002, ADR-003, and the R1 ordering rule verified by dedicated
tripwire tests.

---

## Files Modified

| File | Change |
|------|--------|
| `src/osspulse/github/client.py` | Added `_map_release()` helper + `fetch_releases()` method |
| `src/osspulse/pipeline.py` | Replaced single `fetch_items` call with issues+releases inner-guard pattern (ADR-003) |
| `tests/test_pipeline.py` | Added `fetch_releases.return_value = []` to 21 existing tests + 4 new V2-003 tests |
| `tests/test_cli_run.py` | Added `fetch_releases.return_value = []` to 1 existing test |

## Files Created

| File | Purpose |
|------|---------|
| `tests/github/__init__.py` | Package init for new test subdir |
| `tests/github/test_map_release.py` | 11 unit tests for `_map_release` field mapping |
| `tests/github/test_fetch_releases.py` | 15 unit tests for `fetch_releases` + RISK-002 regression |

---

## Test Results

```
459 passed, 0 failed, 3 warnings
```

Warnings are pre-existing Typer `is_flag` deprecation (documented in memory/developer/v2-002).

### Coverage

| Module | Coverage |
|--------|----------|
| `src/osspulse/github/client.py` | **99%** |
| `src/osspulse/pipeline.py` | **96%** |
| Overall | **96%** |

Threshold: ≥80% ✅

### Secret scan

`grep -rn "ghp_SUPER_SECRET_TOKEN_value" src/osspulse/` → 0 results ✅

Token value never appears in any log or error message (BR-V2-003-005, AC-V2-003-015).

---

## AC Coverage

| AC-ID | Test(s) | Status |
|-------|---------|--------|
| AC-V2-003-001 | `test_releases_in_window_returned` | ✅ |
| AC-V2-003-002 | `test_releases_older_than_cutoff_excluded` | ✅ |
| AC-V2-003-003 | `test_draft_release_skipped_does_not_stop` | ✅ |
| AC-V2-003-004 | `test_prerelease_is_included` | ✅ |
| AC-V2-003-005 | `test_empty_repo_returns_empty_list` | ✅ |
| AC-V2-003-006 | `test_map_release_item_id_is_tag_name` | ✅ |
| AC-V2-003-007 | `test_map_release_title_*` (3 tests) | ✅ |
| AC-V2-003-008 | `test_map_release_null_body_becomes_empty_string` | ✅ |
| AC-V2-003-009 | `test_map_release_null/missing_url_*` (2 tests) | ✅ |
| AC-V2-003-010 | `test_map_release_created_at_is_published_at_unchanged` | ✅ |
| AC-V2-003-011 | `test_map_release_returns_none_when_both_missing`, `test_map_release_uses_id_when_tag_name_missing` | ✅ |
| AC-V2-003-012 | `test_config_tunables_drive_per_page_and_cap` | ✅ |
| AC-V2-003-013 | `test_early_stop_on_created_at_mid_pagination`, `test_risk002_regression_*` | ✅ |
| AC-V2-003-014 | `test_truncation_log_at_max_items_cap` | ✅ |
| AC-V2-003-015 | `test_token_never_in_log_or_error`, `test_token_never_in_auth_error_message` | ✅ |
| AC-V2-003-016 | `test_rate_limit_429_retried_then_succeeds`, `test_rate_limit_exhausted_raises_*` | ✅ |
| AC-V2-003-017 | `test_404_returns_empty_list`, `test_410_returns_empty_list`, `test_401_raises_auth_error` | ✅ |
| AC-V2-003-018 | Code review (no state/LLM imported in client.py — 2.3) | ✅ |
| AC-V2-003-019 | `test_issues_and_releases_concatenated_before_delta` | ✅ |
| AC-V2-003-020 | `test_release_delta_suppressed_on_rerun_*` | ✅ |
| AC-V2-003-021 | `test_release_delta_suppressed_on_rerun_*` | ✅ |
| AC-V2-003-022 | `test_release_fetch_failure_issues_survive_*`, `test_release_auth_error_not_swallowed_*` | ✅ |

---

## Design Deviations

### 1. Inner guard catch tuple (minor deviation)

**Design says**: `except (InvalidRepoError, NetworkError, CollectorError) as exc`

**Implemented**: `except (InvalidRepoError, NetworkError) as exc` + `except CollectorError as exc` with `isinstance(exc, (AuthError, RateLimitError))` re-raise.

**Why**: `AuthError` and `RateLimitError` are subclasses of `CollectorError`. Listing `CollectorError` base in the catch would silently swallow both fatal (`AuthError`) and terminal (`RateLimitError`) errors, contradicting ADR-003. The two-arm pattern ensures only truly recoverable errors are absorbed. Confirmed by `test_release_auth_error_not_swallowed_by_inner_guard`.

### 2. Existing test compatibility stubs

**Not in design** (anticipated but not listed as a task): added `mock_collector.fetch_releases.return_value = []` to 22 pre-existing test sites in `test_pipeline.py` and `test_cli_run.py`.

**Why**: `MagicMock()` returns another `MagicMock` for any attribute access. Once `_collect_all` calls `collector.fetch_releases(...)`, `issues + MagicMock` raises `TypeError` in every existing test. The stub is the minimal, idiomatic fix — equivalent to how existing tests already stub `fetch_items`.

---

## Self-Review Log

**[CRITICAL]** None.

**[HIGH]**
- ADR-001 stop key verified: `_parse_created(created_at) < cutoff` triggers `return items`; `_parse_created(published_at) < cutoff` triggers `continue`. Keys are on different fields — confirmed by RISK-002 regression test (task 3.3).
- R1 ordering verified: `_partition_new` called before `mark_seen`; `mark_seen` receives `issues + releases` (the full concatenated list); called exactly once per repo. Count-invariant confirmed by `test_release_fetch_failure_issues_survive_*`.
- AuthError escape verified: `test_release_auth_error_not_swallowed_by_inner_guard` passes — `AuthError` raised inside `fetch_releases` propagates through the inner guard and is caught by the outer `except AuthError: raise` arm.

**[MEDIUM]**
- Draft guard uses `continue` not `return` — verified by `test_draft_release_skipped_does_not_stop`.
- `ports.py` unchanged — `GitHubClient` Protocol frozen (ADR-002).
- No new error class — `AuthError`, `CollectorError`, `NetworkError`, `InvalidRepoError`, `RateLimitError` reused as-is.

---

## Tripwire Tests

| Tripwire | Test | What it catches |
|----------|------|-----------------|
| ADR-001 early-stop key | `test_risk002_regression_old_created_recent_published_is_missed` | Stop key reversed to `published_at` (Option-B bug) |
| R1 ordering | `test_release_fetch_failure_issues_survive_*` (mark_seen assertions) | `mark_seen` called with wrong list or wrong count |
| ADR-003 inner guard scope | `test_release_auth_error_not_swallowed_by_inner_guard` | `AuthError` caught and suppressed by inner guard |

---

## Known Gaps / QA Focus Areas

1. **created_at ordering assumption** (ADR-001): relies on GitHub `/releases` endpoint sorting by `created_at` descending. This is confirmed behavior but not documented in GitHub's API spec. If GitHub ever changes sort order, `fetch_releases` will silently under-collect. No test can guard against this without a real API call.

2. **RISK-002 miss** (accepted): a release created before the window but published within it is missed. Documented, accepted, pinned by regression test 3.3.

3. **Inner guard `CollectorError` catch breadth**: the `isinstance(exc, (AuthError, RateLimitError)) → raise` pattern handles current subclasses. A future new subclass of `CollectorError` that should be fatal would require updating the isinstance check. Low risk given the stable error hierarchy.

---

## Recommended QA Reading Order

1. `dev-test-report.md` (this file) — change summary, deviations, AC coverage
2. `tests/github/test_fetch_releases.py` — dual-key loop tests + RISK-002 tripwire
3. `src/osspulse/github/client.py` — `_map_release` + `fetch_releases` (lines ~215–305)
4. `src/osspulse/pipeline.py` — `_collect_all` inner guard (lines ~159–175)
5. `tests/test_pipeline.py` — `test_issues_and_releases_concatenated_*`, `test_release_delta_*`, `test_release_fetch_failure_*`, `test_release_auth_error_*`
6. Skip: `ports.py` (unchanged), `renderer.py` (unchanged), any delivery adapter.
