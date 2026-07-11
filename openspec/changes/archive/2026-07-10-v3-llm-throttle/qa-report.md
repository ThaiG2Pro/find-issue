# S5 QA Report — V3-001 (v3-llm-throttle)

Date: 2026-07-11
QA Mode: Smart (dev-test-report.md present; rigor=lite; scope=tiny)

---

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% threshold | ✅ 98.8% (module scope) |
| All required tasks `[x]` | ✅ 9/9 |
| Self-review log present | ✅ (dev-test-report.md §QA Focus Areas) |
| Integration smoke test | ✅ 619 tests pass — full test run green (scope=module confirmed) |
| `.env.example` ≥ 10 lines | ✅ 38 lines |
| `README.md` ≥ 10 lines | ✅ |
| Structured logging wired | ✅ `logger = logging.getLogger(__name__)` in client.py |

---

## Test Scenarios — 5 Targeted Checks (Smart Mode)

Dev covered all 10 ACs. QA ran the following targeted verification passes, tracing
implementation in source and assertions in tests directly.

| AC-ID | Check | How Verified | Expected | Result |
|-------|-------|--------------|----------|--------|
| AC-V3-001-005 | `'Trả lời bằng tiếng Việt.'` in `_build_messages` system content | Code trace: `client.py` `_build_messages()`; test `test_vietnamese_instruction_in_messages_AC_V3_001_005` | Exact string present in `role=system` message | ✅ |
| AC-V3-001-001 / AC-V3-001-002 | `TokenWindow.sleep_if_needed()` sleeps when at/over budget; no sleep when under | Code trace: `sleep_if_needed()` prune+while loop; tests `test_token_window_sleep_when_budget_hit_AC_V3_001_001` and `test_token_window_no_sleep_under_budget_AC_V3_001_002` | sleep called ≥ 1× when budget hit; `slept == []` when under | ✅ |
| AC-V3-001-006 / AC-V3-001-007 / AC-V3-001-008 / AC-4-010 | Retry max 3×, Retry-After honored, skip after exhaustion | Code trace: `_call_with_retry` attempt counter + `Retry-After` extraction; tests `test_retry_succeeds_on_second_attempt_AC_V3_001_006`, `test_retry_after_header_honored_AC_V3_001_007`, `test_retries_exhausted_item_skipped_AC_V3_001_008`, `test_llm_rate_limit_item_skipped_AC_4_010` | 4 total calls on exhaustion; sleep ≥ 5s when Retry-After=5; item skipped after max | ✅ |
| AC-V3-001-003 | `usage=None` records 0 tokens, no crash | Code trace: `total_tokens = ... if usage is not None else 0`; test `test_token_window_missing_usage_records_zero_AC_V3_001_003` | `_entries[0][1] == 0`, no exception | ✅ |
| AC-V3-001-004 | Throttle only on real LLM call (not cache hit, not skip) | Code trace: `sleep_if_needed()` + `record()` placed AFTER cache-hit `return` and `_SkipItem` raise in `summarize()`; tests `test_token_window_cache_hit_not_counted_AC_V3_001_004` + `test_token_window_skip_item_not_counted_AC_V3_001_004` | `_window._entries == []` for both cache hit and empty-item skip | ✅ |

---

## B1 — Test Quality Review (Assertion Depth)

Reviewed all test functions in `tests/test_summarizer_client.py` (31 tests).

- No [H1] existence-only assertions found — all critical tests assert on specific values (`call_count`, `slept[0]`, `_entries[0][1]`, `ids` list membership).
- No [H2] / [H3] / [H5] patterns found.
- [H4] boundary note: `test_token_window_sleep_when_budget_hit_AC_V3_001_001` verifies the window at exactly 100/100 budget. This is the correct BVA boundary. ✅
- `test_llm_rate_limit_item_skipped_AC_4_010` uses `_CFG.max_retries + 1` (not a hardcoded `4`) so the assertion tracks config changes automatically. ✅
- AC-ID labels match what the tests actually assert throughout. ✅

No hollow or fake assertion patterns found.

---

## Security Audit (scope=tiny; module-scoped)

Checked `client.py` for OWASP-relevant patterns:

| Check | Result |
|-------|--------|
| API key never logged or repr'd | ✅ `self.__api_key` (name-mangled); log lines use `_identity()` only; `test_failure_log_no_api_key_or_prompt_AC_4_012` + `test_failure_log_no_api_key_on_retry_exhaust_AC_4_012` green |
| Prompt body never in logs | ✅ `_identity()` returns `repo/type/id` only |
| No hardcoded secrets | ✅ `test_api_key_passed_to_completion_not_hardcoded_AC_4_022` scans module source |
| BLE001 broad-catch annotated | ✅ `# noqa: BLE001` present on both intentional broad catches |
| Input not reflected into error messages | ✅ no f-string with item body/title in error paths |

No security findings.

---

## Dependency Vulnerability Audit

```
uv audit: Found no known vulnerabilities and no adverse project statuses in 63 packages
```

0 HIGH/CRITICAL findings. ✅ Clean.

---

## AC Coverage Summary

- Total ACs this change: 10 (AC-V3-001-001..008 new; AC-4-010 modified; AC-4-012 touched)
- Covered by Dev unit tests: 10/10
- Independently verified by QA (code trace + assertion review): 10/10
- Not covered: 0

One known acceptable gap: lines 212-213 (`except Exception: retry_after = None` in
`_call_with_retry`) — defensive fallback for malformed `Retry-After` float parse.
Not reachable by any realistic real-world input; 98.8% coverage is above threshold.
Non-blocking.

---

## CMS UI Visual QA

N/A — no Figma URL; CLI tool with no UI.

---

## Dependency Vulnerability Audit

0 HIGH/CRITICAL — clean (`uv audit`; 63 packages checked).

---

## Decision: **GO**

619 tests pass, 0 bugs found, all 10 ACs independently verified, coverage 98.8% ≥ 80%,
dependency audit clean, tasks 9/9 `[x]`, no security findings.

## Blockers

None.
