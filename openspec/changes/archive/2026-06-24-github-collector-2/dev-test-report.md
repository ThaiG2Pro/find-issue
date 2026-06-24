## Dev Test Report — github-collector-2
Date: 2026-06-24

### Scope
S2 GitHub Collector (V1, issues only) — `GitHubCollector` adapter implementing
`osspulse.ports.GitHubClient`. Pure I/O: fetches newly-opened issues for one repo via the
GitHub REST API and maps them to `RawItem`s. No State Store, no LLM, no DB (AC-2-015).

### Unit Test Coverage
| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| github/client.py | 127 | 0 | 100% |
| github/config.py | 14 | 0 | 100% |
| github/errors.py | 5 | 0 | 100% |
| github/__init__.py | 4 | 0 | 100% |
| **Overall (project)** | **268** | **2** | **99.25%** |

- Command: `uv run pytest --cov=osspulse` → ✅ PASS (76 passed)
- Thresholds (`.kiro/sdlc.config.json`): lines ≥ 80, branches ≥ 80, diff ≥ 90 — all met.
- The 2 uncovered statements (`config.py` 73-75) are a pre-existing `FileNotFoundError`
  branch outside this change's scope.

### AC Coverage by Tests
All 27 ACs are exercised; every test name/docstring carries its AC-ID (R3).

| AC-ID | Test(s) | Status |
|-------|---------|--------|
| AC-2-001 | test_in_window_issues_returned, test_empty_result_returns_empty_list | ✅ |
| AC-2-002 | test_in_window_issues_returned, test_opened_then_closed_issue_kept | ✅ |
| AC-2-003 | test_old_issues_excluded | ✅ |
| AC-2-004 | test_in_window_issues_returned | ✅ |
| AC-2-005 | test_old_issues_excluded, test_cutoff_early_stop_at_page_two_boundary | ✅ |
| AC-2-006 | test_cap_reached_truncates_with_info_log | ✅ |
| AC-2-007 | test_missing_link_header_means_single_page, test_next_link_returns_none_for_malformed_headers | ✅ |
| AC-2-008 | test_auth_failures_fail_fast, test_other_4xx_fails_fast | ✅ |
| AC-2-009 | test_token_absent_from_success_path, test_token_absent_from_auth_error, test_config_repr_has_no_token | ✅ |
| AC-2-010 | test_null_body_becomes_empty_string, test_missing_mandatory_field_skips_item_without_crash, test_missing_created_at_skipped_in_fetch_loop | ✅ |
| AC-2-011 | test_not_found_warns_and_returns_empty | ✅ |
| AC-2-012 | test_missing_user_and_html_url_use_safe_defaults | ✅ |
| AC-2-013 | test_only_get_issued_and_base_url_from_config, test_default_client_enables_tls_verification | ✅ |
| AC-2-014 | test_malformed_repo_rejected_before_any_request (incl. `../x` traversal) | ✅ |
| AC-2-015 | test_collector_is_pure_io_no_state_or_llm | ✅ |
| AC-2-016 | test_item_id_is_str_number_and_created_at_unchanged | ✅ |
| AC-2-017 | test_item_id_is_str_number_and_created_at_unchanged | ✅ |
| AC-2-018 | test_pull_requests_dropped | ✅ |
| AC-2-019 | test_retry_after_header_honored_on_429, test_non_numeric_retry_after_falls_back_to_computed_backoff | ✅ |
| AC-2-020 | test_secondary_rate_limit_is_retried_not_auth_error | ✅ |
| AC-2-021 | test_5xx_retried_then_succeeds | ✅ |
| AC-2-022 | test_exhausted_retries_raise_bounded | ✅ |
| AC-2-023 | test_transport_error_retried_then_network_error | ✅ |
| AC-2-024 | test_per_page_and_max_items_honor_injected_config | ✅ |
| AC-2-025 | test_only_get_issued_and_base_url_from_config | ✅ |
| AC-2-026 | test_injected_retry_policy_changes_attempt_count, test_injected_sleep_means_no_real_wait | ✅ |
| AC-2-027 | test_injected_retry_policy_changes_attempt_count | ✅ |

### Integration Test Results
N/A — no inbound HTTP API (ADR-007). The outbound GitHub call is exercised end-to-end via
`httpx.MockTransport` (ADR-005): real client + transport, mocked network. No real API call,
no new dependency (`respx` avoided).

### Self-Review Findings
| Severity | Finding | Resolution |
|----------|---------|------------|
| [CRITICAL] | SSRF-shaped repo `../x` matched the shared `REPO_PATTERN` (it permits `.`); httpx normalizes `/repos/../x/issues` → `/x/issues`, escaping the intended path prefix (T-T2, AC-2-014). | Added a defense-in-depth `.`/`..` path-segment guard in `_validate_repo` **without** changing the architect-owned shared regex. Test 7.7 (`../x`) now passes. Logged as a deviation in `_decisions.jsonl`. |
| [HIGH] | Token-leak (T-I1, AC-2-009) — #1 risk. | No `raise`/`log` in `client.py` interpolates the request, headers, or token; messages = status + repo + static reason only. Two dedicated assertions (success path + 401 path) confirm the token is absent from `caplog`, the exception text, and every returned `RawItem`. |
| [HIGH] | Retry boundedness (AC-2-022) — risk of an infinite loop. | `range(max_retries + 1)` bounds total attempts; final attempt raises instead of sleeping. `test_exhausted_retries_raise_bounded` asserts exactly 3 sleeps for the default policy. |
| [MEDIUM] | Non-numeric `Retry-After` could crash the backoff. | Wrapped `float()` parse in `try/except ValueError` → falls through to computed backoff; covered by `test_non_numeric_retry_after_falls_back_to_computed_backoff`. |
| [MEDIUM] | Per-item vs page-level cutoff (AC-2-005). | Cutoff compared per item (not per page); `test_cutoff_early_stop_at_page_two_boundary` asserts the stop happens mid-page-2. |

### Design Deviations
1. **[Minor] `CollectorConfig.retry` uses `field(default_factory=RetryPolicy)`** instead of
   the design's literal `retry: RetryPolicy = RetryPolicy()`. Idiomatic dataclass form;
   identical locked defaults (RetryPolicy is frozen). No behavioral change.
2. **[Minor, security] SSRF traversal guard added to `_validate_repo`** (see Self-Review
   [CRITICAL]). The shared `REPO_PATTERN` (ADR-006) is unchanged and still the primary check;
   the collector adds a `.`/`..` segment rejection as defense-in-depth, exactly where AC-2-014
   requires pre-request rejection. This does not alter `config.py` validation behavior.
   → Flagged for QA/architect awareness: the shared regex still technically accepts `..`
   segments for the S1 config path; only the collector hardens against it. If the team wants
   a single hardened regex, that is an architect (S3) change.

### Known Limitations
- TLS-verification assertion is indirect (`test_default_client_enables_tls_verification`
  checks the default client is built without `verify=False` via header presence) — httpx
  does not expose the verify flag cleanly post-construction. The construction code passes
  `verify=True` explicitly.
- TOML wiring of tunables is deferred (V1 runs on `CollectorConfig` defaults) — out of scope
  per decision `SCOPE-tunables-toml`.

### Coverage Verification
- Command: `uv run pytest --cov=osspulse`
- Result: ✅ PASS — 99.25% lines overall; `github/client.py` 100%.
- Lint: `uv run ruff check src tests` → ✅ All checks passed.
- Format: `uv run ruff format --check` → ✅ all files formatted.
- S4 gate: `openspec change validate "github-collector-2"` → ✅ valid.
- Purity (AC-2-015): no `osspulse.state` / `osspulse.summarizer` / `osspulse.cache` /
  `litellm` / `redis` references in the collector package.
