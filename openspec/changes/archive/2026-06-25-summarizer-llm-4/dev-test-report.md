## Dev Test Report — summarizer-llm-4 (ticket 4)
Date: 2026-06-25
Developer: developer (S4)

### Unit Test Coverage

| Module | Lines | Cover |
|--------|-------|-------|
| summarizer/errors.py | 2/2 | 100% |
| summarizer/config.py | 8/8 | 100% |
| summarizer/keys.py | 7/7 | 100% |
| summarizer/normalize.py | 25/25 | 100% |
| summarizer/client.py | 64/64 | 100% |
| summarizer/__init__.py | 3/3 | 100% |
| cache/redis_cache.py | 12/12 | 100% |
| cache/__init__.py | 2/2 | 100% |
| **Overall (project)** | **479/482** | **99.38%** |

Coverage command: `uv run pytest --cov=osspulse --cov-report=term-missing`
Result: ✅ PASS — 99.38% ≥ 80% threshold

### AC Coverage by Tests

| AC-ID | Test File | Test Name | Status |
|-------|-----------|-----------|--------|
| AC-4-001 | test_summarizer_client.py | test_cache_miss_calls_llm_once_then_stores_AC_4_005 | ✅ PASS |
| AC-4-002 | test_summarizer_client.py | test_cache_miss_calls_llm_once_then_stores_AC_4_005 | ✅ PASS |
| AC-4-003 | test_summarizer_client.py | test_LLMClient_protocol_signature_unchanged_AC_4_003 | ✅ PASS |
| AC-4-004 | test_summarizer_client.py | test_cache_hit_returns_cached_no_llm_call_AC_4_004 | ✅ PASS |
| AC-4-005 | test_summarizer_client.py | test_cache_miss_calls_llm_once_then_stores_AC_4_005 | ✅ PASS |
| AC-4-006 | test_summarizer_client.py | test_cache_key_format_end_to_end_AC_4_006 | ✅ PASS |
| AC-4-007 | test_summarizer_normalize.py | test_same_content_yields_same_hash_AC_4_007 | ✅ PASS |
| AC-4-008 | test_summarizer_normalize.py | test_changed_body_yields_different_hash_AC_4_008 | ✅ PASS |
| AC-4-009 | test_summarizer_client.py | test_llm_timeout_item_skipped_others_summarized_AC_4_009 | ✅ PASS |
| AC-4-010 | test_summarizer_client.py | test_llm_4xx_item_skipped_AC_4_010 (×3) | ✅ PASS |
| AC-4-011 | test_summarizer_client.py | test_item_b_fails_a_c_succeed_AC_4_011 | ✅ PASS |
| AC-4-012 | test_summarizer_client.py | test_failure_log_no_api_key_or_prompt_AC_4_012 | ✅ PASS |
| AC-4-013 | test_summarizer_client.py | test_cache_get_failure_treated_as_miss_AC_4_013 | ✅ PASS |
| AC-4-014 | test_summarizer_client.py | test_cache_set_failure_summary_still_returned_AC_4_014 | ✅ PASS |
| AC-4-015 | test_summarizer_normalize.py | test_over_long_output_normalized_to_two_sentences_AC_4_015 | ✅ PASS |
| AC-4-016 | test_summarizer_normalize.py | test_code_fence_stripped_AC_4_016, test_whitespace_and_newlines_collapsed_AC_4_016 | ✅ PASS |
| AC-4-017 | test_summarizer_client.py | test_empty_body_calls_llm_with_title_only_AC_4_017 | ✅ PASS |
| AC-4-018 | test_summarizer_client.py | test_fully_empty_item_skipped_no_llm_call_AC_4_018 | ✅ PASS |
| AC-4-019 | test_summarizer_client.py | test_huge_body_truncated_and_hashed_post_truncation_AC_4_019 | ✅ PASS |
| AC-4-020 | test_summarizer_client.py | test_second_run_unchanged_items_zero_llm_calls_AC_4_020 | ✅ PASS |
| AC-4-021 | test_summarizer_client.py | test_no_github_or_state_import_AC_4_021 | ✅ PASS |
| AC-4-022 | test_summarizer_client.py | test_api_key_passed_to_completion_not_hardcoded_AC_4_022 | ✅ PASS |

**Coverage: 22/22 ACs (100%)**

### Test Results Summary

| Test file | Tests | Pass | Fail |
|-----------|-------|------|------|
| test_summarizer_normalize.py | 19 | 19 | 0 |
| test_redis_cache.py | 5 | 5 | 0 |
| test_summarizer_client.py | 45 | 45 | 0 |
| (pre-existing tests) | 95 | 95 | 0 |
| **Total** | **164** | **164** | **0** |

### Self-Review Findings

| Severity | Finding | Resolution |
|----------|---------|------------|
| [MEDIUM] | ADR-002 deviation: `litellm.exceptions.APIError` is NOT the common base at runtime; actual MRO has all litellm exceptions inherit from `openai.APIError` | Fixed: catch changed to `except openai.APIError`. Design intent fully preserved. Tests use REAL litellm.exceptions.* instances to guard against future hierarchy changes (ADR-002 risk mitigation). |
| [LOW] | `_SkipItem` is a private sentinel exception; not exported | By design — only caught inside `summarize_items`. No user-visible impact. |

No CRITICAL or HIGH findings.

### Design Deviations

| ID | Where | Design said | Code does | Reason | Impact |
|----|-------|-------------|-----------|--------|--------|
| DEV-001 (minor) | `client.py:summarize_items` | `except litellm.exceptions.APIError` | `except openai.APIError` | Runtime MRO: litellm exceptions inherit `openai.APIError`, not `litellm.exceptions.APIError`. `issubclass(litellm.exceptions.Timeout, litellm.exceptions.APIError) == False`. | None — same set of errors caught, same behavior. Tests with real litellm instances pass. |

### Security Scan

| Check | Result |
|-------|--------|
| No `osspulse.github` / `osspulse.state` imports in summarizer/ + cache/ (AC-4-021) | ✅ PASS |
| `api_key` never appears in log calls (AC-4-012, RF-4) | ✅ PASS |
| `timeout=30.0s` forwarded to `completion()` (RF-2) | ✅ PASS |
| `_build_messages` sends only `title` + `body` (RF-1) | ✅ PASS |
| No hardcoded secret literal in source (AC-4-022) | ✅ PASS |
| `SummarizerConfig` has no `api_key` field (RF-4) | ✅ PASS |

### Known Limitations

- EC-014: corrupt cached value (foreign writer) is returned as-is — accepted V1 best-effort limit (documented in design.md §Edge Cases).
- EC-010/011: concurrent writers not protected by locking — out of scope for single-operator V1 (documented).
- `max_summary_chars=600` secondary clamp is not AC-specified — design choice to bound pathological single-sentence run-ons; no test required.
- Abbreviation mask list is non-exhaustive (ADR-006, confidence MEDIUM) — cosmetic risk only; soft ≤2 contract.
- README disclosure of data egress (RF-1) is an S6 release task — not S4.

### Files Created / Modified

| File | Action | Tasks |
|------|--------|-------|
| src/osspulse/summarizer/errors.py | NEW | 1.1 |
| src/osspulse/summarizer/config.py | NEW | 1.2 |
| src/osspulse/summarizer/keys.py | NEW | 2.1 |
| src/osspulse/summarizer/normalize.py | NEW | 2.2 + 2.3 |
| src/osspulse/summarizer/client.py | NEW | 5.1 + 5.2 + 5.3 + 6.1 |
| src/osspulse/summarizer/__init__.py | MODIFIED (was empty) | 5.4 |
| src/osspulse/cache/redis_cache.py | NEW | 3.1 |
| src/osspulse/cache/__init__.py | MODIFIED (was empty) | 5.4 |
| tests/test_summarizer_normalize.py | NEW | 2.4 |
| tests/test_redis_cache.py | NEW | 3.2 |
| tests/test_summarizer_client.py | NEW | 5.5 + 6.2 |
