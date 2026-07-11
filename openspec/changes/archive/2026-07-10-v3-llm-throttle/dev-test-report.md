# Dev Test Report — v3-llm-throttle (V3-001)

**Phase**: S4  
**Agent**: developer  
**Date**: 2026-07-11  
**Scope**: tiny — `src/osspulse/summarizer/client.py` + `src/osspulse/summarizer/config.py`  
**Rigor**: lite  

---

## 1. Summary

Implemented LLM token throttle, Vietnamese summary prompt, and 429 retry-then-skip for the
`LiteLLMSummarizer` adapter. All 8 new ACs green, modified AC-4-010 (retries-then-skip) green,
and all pre-existing ACs still passing.

---

## 2. AC Coverage

| AC-ID | Description | Test | Status |
|-------|-------------|------|--------|
| AC-V3-001-001 | Near-budget triggers sleep | `test_token_window_sleep_when_budget_hit_AC_V3_001_001` | ✅ |
| AC-V3-001-002 | Under-budget: no sleep | `test_token_window_no_sleep_under_budget_AC_V3_001_002` | ✅ |
| AC-V3-001-003 | Missing usage → 0 tokens, no crash | `test_token_window_missing_usage_records_zero_AC_V3_001_003` | ✅ |
| AC-V3-001-004 | Cache hit / skip not counted | `test_token_window_cache_hit_not_counted_AC_V3_001_004`, `test_token_window_skip_item_not_counted_AC_V3_001_004` | ✅ |
| AC-V3-001-005 | Vietnamese instruction in prompt | `test_vietnamese_instruction_in_messages_AC_V3_001_005` | ✅ |
| AC-V3-001-006 | 429 retry succeeds → summary produced | `test_retry_succeeds_on_second_attempt_AC_V3_001_006` | ✅ |
| AC-V3-001-007 | Retry-After header honored | `test_retry_after_header_honored_AC_V3_001_007` | ✅ |
| AC-V3-001-008 | Retries exhausted → skip-log-continue | `test_retries_exhausted_item_skipped_AC_V3_001_008` | ✅ |
| AC-4-010 (MOD) | 429 retries-then-skips (updated) | `test_llm_rate_limit_item_skipped_AC_4_010` | ✅ |
| AC-4-012 | Log never contains key/prompt | `test_failure_log_no_api_key_or_prompt_AC_4_012`, `test_failure_log_no_api_key_on_retry_exhaust_AC_4_012` | ✅ |

All pre-existing ACs (AC-4-003..022) verified: 31 tests total, all pass.

---

## 3. Test Results

```
tests/test_summarizer_client.py    31 passed
tests/test_summarizer_normalize.py 19 passed
Total: 50 passed
```

**Coverage** (module scope `osspulse.summarizer`):

```
Name                                   Stmts   Miss  Cover
----------------------------------------------------------
src/osspulse/summarizer/client.py        118      2    98%
src/osspulse/summarizer/config.py         12      0   100%
src/osspulse/summarizer/errors.py          2      0   100%
src/osspulse/summarizer/keys.py            7      0   100%
src/osspulse/summarizer/normalize.py      25      0   100%
TOTAL                                    167      2    99%
```

Missing (lines 212-213): the `except Exception: retry_after = None` defensive path in
`_call_with_retry` — triggered only when `Retry-After` header parsing raises. Acceptable gap
at 98.8%.

**Lint**: `ruff check src/osspulse/summarizer/` → All checks passed.

---

## 4. Design Deviations

None. Implementation follows design.md and all 5 ADRs exactly.

---

## 5. QA Focus Areas

- **AC-V3-001-004** (no double-count): the `sleep_if_needed()` / `record()` placement is the
  most critical invariant — they run ONLY after the cache-hit return and after the `_SkipItem`
  guard. Any change to `summarize()` call order would break this silently.
- **AC-4-010 regression**: the updated `test_llm_rate_limit_item_skipped_AC_4_010` verifies
  `call_count == max_retries + 1` (4 total calls) before skip. If `max_retries` changes in
  config the test value auto-follows via `_CFG.max_retries`.
- **Retry-After extraction** is intentionally defensively written — any attribute absence
  falls back to exp-backoff silently. The uncovered lines 212-213 are this path.
- **No pipeline.py changes**: `LLMClient` Protocol signature and `summarize_items` interface
  are unchanged. S7/pipeline can be verified by running the full suite.
