# Dev Test Report — V2-007 ETag Conditional-Request Caching
Generated: 2026-07-10 | Agent: developer | Change: v2-cache-etag

## Summary

All 15 tasks complete. 609 tests passing (0 failures). Coverage 97% across the four touched
modules. Ruff lint clean. Secret-scan pass. openspec validate pass.

## Coverage

| Module | Statements | Covered | % |
|--------|-----------|---------|---|
| `cache/etag_store.py` | 66 | 61 | 92% |
| `github/client.py` | 251 | 249 | 99% |
| `pipeline.py` | 122 | 114 | 93% |
| `config.py` | 114 | 112 | 98% |
| **Total (touched)** | **553** | **536** | **97%** |

All modules ≥80% lines threshold (configured: 80%).

## Tests Written

| File | Tests | ACs Covered |
|------|-------|-------------|
| `tests/cache/test_etag_store.py` | 25 | AC-V2-007-001..008 |
| `tests/github/test_conditional_requests.py` | 19 | AC-V2-007-009..018 |
| `tests/test_config.py` (appended) | 6 | AC-V2-007-020..021 |
| `tests/test_pipeline.py` (appended) | 10 | AC-V2-007-019..028 |

**Total new tests: 60** (609 total suite, all green)

## Design Deviations

### DEVIATION-001: `_NullConditionalCache` location
**Design said**: Task 1.3 placed `_NullConditionalCache` in `cache/etag_store.py`
**Actual**: Moved to `osspulse/ports.py`; `etag_store.py` re-exports it for convenience
**Why**: Existing test `test_collector_is_pure_io_no_state_or_llm` in `test_github_client.py`
forbids `osspulse.cache` imports in the collector (AC-2-015 boundary enforcement). Moving
`_NullConditionalCache` to `ports.py` keeps the collector depending on the port layer only,
which is architecturally correct per the design's own principle ("depend on the port only").
**Impact**: None — `_NullConditionalCache` is still importable from `cache/etag_store` via
re-export. The null object still satisfies the `ConditionalCache` Protocol.

## RISK-001 Tripwire Test

`test_commit_not_called_on_auth_error_mid_loop` in `tests/test_pipeline.py`:
- Asserts `commit()` is NOT called when `AuthError` fires mid-loop (crash-safety invariant)
- `test_commit_called_exactly_once_after_collect_loop` asserts commit is called exactly once after the loop

## Self-Review Log

**[CRITICAL]**: None

**[HIGH]**: None

**[MEDIUM]**:
- `commit()` placement is crash-safety-critical — guarded by code comment in `pipeline.py` and
  the tripwire test. Future edit wrapping it in try/except or moving it earlier would break
  AC-V2-007-025. QA should verify the comment + test remain intact.
- `_classify(304)→OK` combined with `branch on raw status_code==304` in fetch methods is subtle
  — both 200 and 304 return `_Action.OK`; the fetch methods must distinguish on `status_code`
  not on the action. Tested explicitly in `test_first_page_304_returns_empty_no_page2_issues`.

## AC Coverage Matrix

| AC | Test(s) | Status |
|----|---------|--------|
| AC-V2-007-001 | test_miss_returns_none, test_set_commit_get_round_trip | ✅ |
| AC-V2-007-002 | test_set_commit_get_round_trip, test_multiple_repos_and_endpoints_round_trip | ✅ |
| AC-V2-007-003 | test_commit_uses_temp_file_in_same_dir, test_commit_atomic_result_correct | ✅ |
| AC-V2-007-004 | test_corrupt_json_returns_empty_and_warns, test_missing_file_returns_empty, test_unreadable_file_returns_empty_and_warns | ✅ |
| AC-V2-007-005 | test_set_without_commit_is_not_durable, test_set_is_visible_in_same_instance_before_commit | ✅ |
| AC-V2-007-006 | test_token_sentinel_never_in_etags_json, test_persisted_file_contains_only_keys_and_validators | ✅ |
| AC-V2-007-007 | test_null_cache_get_returns_none, test_null_cache_set_is_noop, test_null_cache_commit_is_noop | ✅ |
| AC-V2-007-008 | test_store_never_touches_state_json, test_store_does_not_import_json_store | ✅ |
| AC-V2-007-009 | test_null_cache_collector_unconditional_fetch_issues, test_no_cache_arg_uses_null_cache, test_no_cached_etag_no_if_none_match_header | ✅ |
| AC-V2-007-010 | test_first_page_sends_if_none_match_strong_etag_issues, test_first_page_sends_if_none_match_releases | ✅ |
| AC-V2-007-011 | test_first_page_304_returns_empty_no_page2_issues, test_first_page_304_returns_empty_no_page2_releases | ✅ |
| AC-V2-007-012 | test_first_page_200_records_etag_and_paginates_issues, test_first_page_200_records_etag_releases | ✅ |
| AC-V2-007-013 | test_page2_carries_no_if_none_match_issues | ✅ |
| AC-V2-007-014 | test_200_no_etag_header_no_set_no_crash_issues, test_200_no_etag_no_crash_null_cache | ✅ |
| AC-V2-007-015 | test_first_page_sends_if_none_match_weak_etag_issues | ✅ |
| AC-V2-007-016 | test_429_on_conditional_request_retries_issues, test_401_on_conditional_request_fails_fast_issues, test_5xx_on_conditional_request_retries_then_raises | ✅ |
| AC-V2-007-017 | test_fetch_discussions_sends_no_conditional_header, test_fetch_discussions_cache_set_never_called | ✅ |
| AC-V2-007-018 | test_token_not_in_conditional_path_error_message | ✅ |
| AC-V2-007-019 | test_build_etag_cache_failure_returns_null_and_run_completes | ✅ |
| AC-V2-007-020 | test_etag_cache_section_absent_defaults_enabled_and_default_path, test_etag_cache_enabled_false, test_etag_cache_custom_path | ✅ |
| AC-V2-007-021 | test_etag_cache_enabled_non_bool_string_raises, test_etag_cache_enabled_int_raises, test_etag_cache_config_error_before_pipeline | ✅ |
| AC-V2-007-022 | test_both_flags_true_etag_cache_injected_into_collector | ✅ |
| AC-V2-007-023 | test_delta_disabled_null_cache_injected, test_etag_cache_disabled_null_cache_injected | ✅ |
| AC-V2-007-024 | test_commit_called_exactly_once_after_collect_loop | ✅ |
| AC-V2-007-025 | test_commit_not_called_on_auth_error_mid_loop | ✅ |
| AC-V2-007-026 | test_e2e_run1_records_items_and_etag_run2_304_no_new_items | ✅ |
| AC-V2-007-027 | test_e2e_run2_new_issue_only_new_item_rendered | ✅ |
| AC-V2-007-028 | test_e2e_corrupt_etags_json_warns_unconditional_fetch_exit0 | ✅ |

All 28 ACs covered. ✅
