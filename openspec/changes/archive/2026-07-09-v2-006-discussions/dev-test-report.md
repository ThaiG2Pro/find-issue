# Dev Test Report — v2-006-discussions

**Change**: v2-006-discussions  
**Phase**: S4 → S5  
**Date**: 2026-07-09  
**Author**: developer  
**Scope**: GitHub Discussions collector + pipeline wiring  

---

## Summary

All 18 required tasks completed. 550 tests passing (68 new collector + mapping tests, 5 new pipeline tests). Coverage 96.25% overall; `client.py` 99%, `pipeline.py` 93% — both well above the 80% threshold.

---

## AC Coverage

| AC | Description | Test File | Test Function |
|----|-------------|-----------|---------------|
| AC-V2-006-001 | Fetch discussions via GraphQL POST, item_type=discussion | test_fetch_discussions.py | test_discussions_in_window_returned |
| AC-V2-006-002 | Inclusion by createdAt in window (Approach A); early-stop | test_fetch_discussions.py | test_older_discussion_excluded_early_stop |
| AC-V2-006-003 | Discussions disabled → WARN + [], run continues | test_fetch_discussions.py | test_discussions_disabled_null_discussions_skips_repo, test_discussions_disabled_null_repository_skips_repo |
| AC-V2-006-004 | Enabled but empty → [], no error | test_fetch_discussions.py | test_enabled_empty_repo_returns_empty_list |
| AC-V2-006-005 | item_id = str(number) | test_map_discussion.py | test_item_id_is_stringified_number |
| AC-V2-006-006 | title mapped; null → "" | test_map_discussion.py | test_title_mapped, test_title_null_becomes_empty_string |
| AC-V2-006-007 | body = markdown `body`; null → "" | test_map_discussion.py | test_body_maps_markdown_field, test_body_null_becomes_empty_string |
| AC-V2-006-008 | url mapped; null → "" | test_map_discussion.py | test_url_mapped, test_url_null_becomes_empty_string |
| AC-V2-006-009 | created_at = raw createdAt ISO, never reformatted | test_map_discussion.py | test_created_at_preserved_as_raw_iso |
| AC-V2-006-010 | Node missing number → None (skip) | test_map_discussion.py | test_missing_number_returns_none, test_number_none_returns_none |
| AC-V2-006-011 | Cursor pagination (hasNextPage/endCursor); bounded by config | test_fetch_discussions.py | test_cursor_pagination_follows_pages |
| AC-V2-006-012 | Early-stop when createdAt < cutoff (CREATED_AT DESC, no skew) | test_fetch_discussions.py | test_early_stop_mid_pagination_requests_no_further_pages |
| AC-V2-006-013 | Info-level truncation log at max_items_per_repo | test_fetch_discussions.py | test_truncation_info_log_at_cap |
| AC-V2-006-014 | Non-disabled 200+errors → raise (RateLimitError or CollectorError) | test_fetch_discussions.py | test_graphql_non_disabled_errors_raises_collector_error, test_graphql_rate_limited_error_raises_rate_limit_error |
| AC-V2-006-015 | Transport 429/5xx retried; 401/403 → AuthError | test_fetch_discussions.py | test_transport_429_retried_then_succeeds, test_transport_401_raises_auth_error |
| AC-V2-006-016 | Fixed non-mutating POST; REST callers still GET (ADR-002 regression) | test_fetch_discussions.py | test_fetch_discussions_issues_exactly_one_post_per_page, test_fetch_items_still_issues_get_adr002_regression, test_fetch_releases_still_issues_get_adr002_regression |
| AC-V2-006-017 | Token never in logs/errors; endpoint from config base_url | test_fetch_discussions.py | test_token_never_in_log_lines_on_graphql_path, test_token_not_in_graphql_request_body |
| AC-V2-006-018 | fetch_discussions adapter-only; GitHubClient Protocol unchanged | (structural — no Protocol test needed; verified by absence of Protocol change) | — |
| AC-V2-006-019 | issues + releases + discussions concatenated before delta | test_pipeline.py | test_issues_releases_discussions_concatenated_before_delta |
| AC-V2-006-020 | Discussions flow through delta filter, marked seen | test_pipeline.py | test_discussion_delta_suppressed_on_rerun_renderer_group_unchanged |
| AC-V2-006-021 | Render under existing ### Discussion (N) group; no renderer change | test_pipeline.py | test_discussion_delta_suppressed_on_rerun_renderer_group_unchanged |
| AC-V2-006-022 | Per-repo discussion-fetch failure isolated; issues/releases survive | test_pipeline.py | test_discussion_fetch_failure_issues_releases_survive, test_discussion_auth_error_not_swallowed_by_inner_guard |

---

## Test Results

```
550 passed, 3 warnings (deprecation warnings from Typer — pre-existing, not introduced by this change)

New tests: 73
  - tests/github/test_map_discussion.py:    18 tests (AC-V2-006-005..010 + item_type + full node)
  - tests/github/test_fetch_discussions.py: 50 tests (AC-V2-006-001..017 incl. ADR-002/003 tripwires)
  - tests/test_pipeline.py (new):            5 tests (AC-V2-006-019..022 pipeline integration)
```

---

## Coverage

| Module | Lines | Branches | Key uncovered |
|--------|-------|----------|---------------|
| `github/client.py` | 99% | — | pragma: no cover (unreachable retry exhaustion) |
| `pipeline.py` | 93% | — | Discord/file delivery paths (pre-existing); no-LLM path log line |
| **Total** | **96.25%** | — | All above 80% threshold |

---

## Design Deviations

| # | Where | Design says | What was done | Impact |
|---|-------|-------------|---------------|--------|
| 1 | `_classify_graphql` return type | Design shows `_GraphQLAction | list[dict]` | Returns `_GraphQLOutcome | dict` where dict is the connection (not raw nodes list); the outer loop calls `conn.get("nodes")` safely | None — same semantic; connection dict is more consistent with GraphQL structure |
| 2 | Log format string in `_collect_all` | Design shows `(seen=%d new=%d)` | Extended to `(issues=%d releases=%d discussions=%d seen=%d new=%d)` | Additive; pre-existing tests updated with `--any_call` style, not broken |

---

## Self-Review Log

**[CRITICAL]** None.

**[HIGH]** None. The load-bearing ADR-003 order (null-shape BEFORE errors-raise) is implemented correctly and pinned by `test_disabled_null_shape_detected_BEFORE_errors_raise`. The inner-guard `isinstance(exc, (AuthError, RateLimitError)): raise` exclusion mirrors the release guard exactly.

**[MEDIUM]**
- `_classify_graphql` re-reads `errors[].type` only for `RATE_LIMITED` routing, not for disabled-Discussions detection. This is intentional per ADR-003 — detection keys on null shape, not type string.
- Token-not-in-body is tested explicitly (`test_token_not_in_graphql_request_body`).
- R1 invariant: `_partition_new` BEFORE one `mark_seen(items)` on the full 3-source list — preserved and pinned by the count-invariant test (`test_discussion_fetch_failure_issues_releases_survive`).

---

## Security Scan

No token value (`ghp_SUPER_SECRET_TOKEN_value`) appears in any log/error/request body on the GraphQL path. Verified by:
- `test_token_never_in_log_lines_on_graphql_path`
- `test_token_never_in_auth_error_message`
- `test_token_never_in_rate_limit_error_message`
- `test_token_not_in_graphql_request_body`

GraphQL query is a fixed constant (`_DISCUSSIONS_QUERY`); only `owner`/`name`/`first`/`after` are variables. No mutation. Verified by `test_fetch_discussions_issues_exactly_one_post_per_page`.

---

## Files Changed

| File | Change |
|------|--------|
| `src/osspulse/github/client.py` | Added `_GraphQLOutcome`, `_DISCUSSIONS_QUERY`, `_map_discussion`, `_classify_graphql`, `fetch_discussions`; generalized `_request_with_retry` with `json_body` param; added `CollectorError` import |
| `src/osspulse/pipeline.py` | Added `fetch_discussions` inner guard + 3-source concatenation in `_collect_all`; updated log format |
| `tests/github/test_map_discussion.py` | NEW — 18 unit tests for `_map_discussion` |
| `tests/github/test_fetch_discussions.py` | NEW — 50 unit tests for `fetch_discussions` |
| `tests/test_pipeline.py` | Added 5 new v2-006 pipeline tests; added `fetch_discussions.return_value = []` stub to all existing mock_collector instances |
| `tests/test_cli_run.py` | Added `fetch_discussions.return_value = []` stub to affected test |

---

## QA Focus Areas

1. **ADR-003 check order** — `test_disabled_null_shape_detected_BEFORE_errors_raise` is the primary tripwire. QA should verify the fixture matches a real GitHub GraphQL disabled-Discussions response shape.
2. **Inner-guard fatal exclusion** — `test_discussion_auth_error_not_swallowed_by_inner_guard` and `test_discussion_rate_limit_error_not_swallowed_by_inner_guard` pin this.
3. **R1 count-invariant** — `test_discussion_fetch_failure_issues_releases_survive` asserts `mark_seen` call counts and arguments exactly.
4. **Token security** — four token-leak assertions across the GraphQL path.
5. **ADR-002 GET-only regression** — `test_fetch_items_still_issues_get_adr002_regression` and `test_fetch_releases_still_issues_get_adr002_regression` confirm REST paths still issue GET.
