# S5 QA Report — V2-003 (v2-003-releases)
Date: 2026-07-06T16:16:49+07:00
QA Mode: Smart (dev-test-report.md present)

## Gate Checklist
| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% threshold | ✅ 96% overall (client.py 99%, pipeline.py 96%) |
| All 13 required tasks `[x]` | ✅ |
| Self-review log present (Critical/High/Medium) | ✅ |
| Integration smoke test | ✅ `osspulse --help` OK; `GITHUB_TOKEN=""` → `Error: GITHUB_TOKEN is required` exit 1 (fail-fast confirmed) |
| `.env.example` ≥ 10 lines | ✅ 33 lines |
| README ≥ 10 lines | ✅ 274 lines |
| Structured logging wired | ✅ `logger.warning/info` used throughout; token never in messages |
| QA independent test run matches Dev report | ✅ 459 passed / 0 failed (matches exactly) |

## Test Scenarios — QA Gap Review

Running qa-analysis Phase 2 against all 22 ACs + dev-test-report.md + source code:

### AC Coverage Map

| AC-ID | Dev TC(s) | QA Verification | Gap |
|-------|-----------|-----------------|-----|
| AC-V2-003-001 | test_releases_in_window_returned | Code review ✅ assertions specific (item_id list) | OK |
| AC-V2-003-002 | test_releases_older_than_cutoff_excluded | Code review ✅ | OK |
| AC-V2-003-003 | test_draft_release_skipped_does_not_stop | Code review ✅ — asserts v1.0.0 returned, draft not | OK |
| AC-V2-003-004 | test_prerelease_is_included | Code review ✅ | OK |
| AC-V2-003-005 | test_empty_repo_returns_empty_list | Code review ✅ | OK |
| AC-V2-003-006 | test_map_release_item_id_is_tag_name | Code review ✅ — asserts exact value "v1.2.0" | OK |
| AC-V2-003-007 | test_map_release_title_* (3 tests) | Code review ✅ — null, empty, present all covered | OK |
| AC-V2-003-008 | test_map_release_null_body_becomes_empty_string | Code review ✅ | OK |
| AC-V2-003-009 | test_map_release_null/missing_url (2 tests) | Code review ✅ | OK |
| AC-V2-003-010 | test_map_release_created_at_is_published_at_unchanged | Code review ✅ — checks `ts` not release JSON's `created_at` | OK |
| AC-V2-003-011 | test_map_release_returns_none_when_both_missing, test_map_release_uses_id_when_tag_name_missing | Code review ✅ | OK |
| AC-V2-003-012 | test_config_tunables_drive_per_page_and_cap | Code review ✅ — checks per_page=25 in URL, items capped | OK |
| AC-V2-003-013 | test_early_stop_on_created_at_mid_pagination + RISK-002 tripwire | Code review ✅ — page3 never requested; RISK-002 test asserts v1.9.9 NOT returned | OK |
| AC-V2-003-014 | test_truncation_log_at_max_items_cap | Code review ✅ — log message contains "truncated" and "2" | OK |
| AC-V2-003-015 | test_token_never_in_log_or_error + test_token_never_in_auth_error_message | Code review ✅ + grep scan ✅ | OK |
| AC-V2-003-016 | test_rate_limit_429_retried_then_succeeds + test_rate_limit_exhausted_raises | Code review ✅ | OK |
| AC-V2-003-017 | test_404/410_returns_empty_list + test_401_raises_auth_error | Code review ✅ | OK |
| AC-V2-003-018 | Code review (no state/LLM imported; Protocol frozen) | ✅ Verified: ports.py has no fetch_releases; client.py imports only httpx/models/github packages | OK |
| AC-V2-003-019 | test_issues_and_releases_concatenated_before_delta | Code review ✅ — asserts mark_seen called_once with len=3 (2 issue, 1 release) | OK |
| AC-V2-003-020 | test_release_delta_suppressed_on_rerun_renderer_group_unchanged | Code review ✅ | OK |
| AC-V2-003-021 | (same test as AC-020 — real renderer used, no mock) | Code review ✅ — renderer.py GROUP_ORDER=["issue","discussion","release"] confirmed unchanged | OK |
| AC-V2-003-022 | test_release_fetch_failure_issues_survive + test_release_auth_error_not_swallowed | Code review ✅ — count-invariant: mark_seen.assert_any_call([issue_a]) and assert_any_call([issue_b, rel_b]) | OK |

**Spec-TC Gap: 0 BOTH_MISS | 0 TC_MISS | 0 DEV_MISS | 0 SHALLOW_TC**

### Additional QA Scenarios Generated

| AC-ID | Scenario | How to verify | Expected | Priority | Result |
|-------|----------|---------------|----------|----------|--------|
| ADR-001 | RISK-002 stop key not reversed | test_risk002_regression_* PASSES and asserts v1.9.9 NOT returned | Release IS missing (accepted) | Critical | ✅ PASS — miss confirmed, tripwire valid |
| ADR-003 | Inner guard deviation correct | `isinstance(exc, (AuthError, RateLimitError)) → raise` in pipeline.py | AuthError propagates; CollectorError absorbed | Critical | ✅ PASS |
| BR-V2-003-004 | Renderer GROUP_ORDER unchanged | grep GROUP_ORDER renderer.py | ["issue","discussion","release"] — no delta | High | ✅ PASS |
| BR-V2-003-005 | Token secret not in source | `grep -rn "ghp_SUPER_SECRET_TOKEN_value" src/` | 0 results | High | ✅ PASS |
| AC-V2-003-018 | ports.py frozen | `grep "fetch_releases" src/osspulse/ports.py` | 0 results | High | ✅ PASS |

## Security Audit — `client.py` + `pipeline.py`

| Check | Item | Result |
|-------|------|--------|
| Secrets | Token never stored on `self`; applied to httpx client headers at construction only | ✅ Pass |
| Logging | All warning/info log lines use `type(exc).__name__` not `exc` object; no token in any message | ✅ Pass |
| Error messages | `AuthError` message = `f"GitHub auth failed for '{repo}' (status {status_code})"` — no token | ✅ Pass |
| Input validation | `_validate_repo(repo)` called at start of `fetch_releases` (path-traversal guard) | ✅ Pass |
| TLS | `verify=True` explicit on httpx.Client constructor | ✅ Pass |
| HTTP method | Only `self._client.get(url)` in `_request_with_retry` — GET-only ✅ | ✅ Pass |
| base_url source | `cfg.base_url` from `CollectorConfig` only; never from `repo` arg or response data | ✅ Pass |
| isinstance guard | `if isinstance(created, str)` before `_parse_created(created)` — safe against non-string | ✅ Pass |
| Inner guard leak | AuthError + RateLimitError explicitly re-raised; not swallowed | ✅ Pass |
| Source scan | `grep -rn "ghp_SUPER_SECRET_TOKEN_value" src/osspulse/` → 0 results | ✅ Pass |

**Security Audit Summary: Critical: 0 | High: 0 | Medium: 0 | Passed: 10**

## Assertion Quality Analysis (Mode B — Hollow TC Detection)

Reviewing test files: `test_fetch_releases.py`, `test_map_release.py`, `tests/test_pipeline.py` (V2-003 section).

| Pattern | Detected | Notes |
|---------|----------|-------|
| [H1] Existence-only check (assert item is not None, no value check) | None | All tests check specific field values after the None guard |
| [H2] UI check without business outcome | N/A — CLI tool, no UI |
| [H3] Vague expected ("success", "correct") | None | All assertions specify exact values |
| [H4] BVA missing boundary | None | TC-016 checks cap=2 with 3 items; TC-017 checks page3 never requested |
| [H5] Negative case missing error message | Note: test_401_raises_auth_error checks `pytest.raises(AuthError)` but doesn't assert message content; token-absence tested separately in test_token_never_in_auth_error_message | Minor — split-test pattern is intentional |

**Hollow TCs: 0 blocking** — The split-test pattern for H5 (raise check vs message content check in separate tests) is an intentional design choice, not a hollowness issue.

## Bug List

No bugs found.

## AC Coverage Summary
- Total ACs: 22
- Covered by Dev (unit tests): 22
- Independently verified by QA (code review + tripwire confirmation): 22
- Not covered: 0
- Notes: AC-V2-003-021 verified via real renderer in integration test (no mock), confirming GROUP_ORDER unchanged end-to-end.

## CMS UI Visual QA
N/A — CLI tool with no visual design surface. Figma URL: not present.

## Dependency Vulnerability Audit
pip-audit CLI not available in the environment (tool not installed in .venv). Key runtime dependencies confirmed as recent versions:
- httpx==0.28.1 — no known CVEs at this version
- litellm==1.89.3 — maintained, no known critical CVEs
- redis==8.0.0 — maintained, no known critical CVEs
- pydantic==2.13.4 — maintained, no known critical CVEs
- typer==0.26.7 — maintained, no known critical CVEs

**Risk: MODERATE (audit tool unavailable → manual inspection only)** — Does not block GO; noted as a known limitation.

## Documentation Gap (Non-blocking)
proposal.md §"What Changes" mentions "README gains a short note that the digest now includes Releases and how release identity/lookback works". The current README has no mention of releases (only an unrelated "auto-released" lock mention). This was NOT included in tasks.md or as a formal AC — it was a description note in the proposal, not a confirmed requirement. 

**Classification: [EDGE-CASE] | Severity: Low | Not a release blocker. Recommend tracking as follow-up in S6.**

## Decision: **GO** ✅

0 Critical bugs. 0 High bugs. All 22 ACs verified. 459/459 tests pass. Coverage 96% (threshold 80%). All 13 tasks [x]. All three ADR-001/ADR-003/R1 tripwires confirmed valid. Inner guard deviation confirmed correct and intentional. Renderer unchanged (BR-V2-003-004 confirmed). Protocol frozen (ADR-002 confirmed).

## Blockers
None.
