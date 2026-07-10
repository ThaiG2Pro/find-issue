# S5 QA Report — V2-006 (v2-006-discussions)
Date: 2026-07-09T17:32:31+07:00
QA Mode: Smart (dev-test-report.md present)
Rigor: lite | test_scope: module | testcase_export: none

---

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% (actual: 96.25% total; client.py 99%, pipeline.py 93%) | ✅ |
| All required tasks `[x]` (18/18) | ✅ |
| Self-review log present (Critical: 0, High: 0) | ✅ |
| `.env.example` ≥ 10 lines (actual: 39 lines) | ✅ |
| `README.md` ≥ 10 lines (actual: 284 lines) | ✅ |
| Structured logging wired (`logging.getLogger` in pipeline.py + client.py) | ✅ |
| Lint: ruff clean on touched modules | ✅ |
| Integration Smoke Test | ⚠️ See note below |
| Dependency vulnerability audit: 0 HIGH/CRITICAL | ✅ (uv audit: 0 known vulnerabilities in 63 packages) |

**Integration Smoke Test note**: This is a CLI tool with no health endpoint. The tool requires
real `GITHUB_TOKEN` + optional LLM key + Redis. A live smoke test hitting the real GitHub GraphQL
API is out of scope for a unit-level QA session (no credentials in CI). However, the collector is
fully exercised by 50 httpx.MockTransport tests — every control-flow path (POST/retry/skip/error)
is covered. The integration between `pipeline._collect_all` and `fetch_discussions` is covered by
5 pipeline tests with mocked collector. This is classified as an accepted limitation, not a blocker.
`[EDGE-CASE] Medium` — documented here; does not block GO per the gate rule (no daemon/no credentials).

---

## Spec-TC Gap Analysis (qa-analysis Phase 2)

All 22 ACs are covered by developer unit/integration tests. QA gap review by AC category:

| AC-ID | Dev coverage | Gap type | QA action |
|-------|-------------|----------|-----------|
| AC-V2-006-001 | test_discussions_in_window_returned | — | Code review ✅ |
| AC-V2-006-002 | test_older_discussion_excluded_early_stop | SHALLOW_TC: only checks 1 in-window, 1 out-of-window | See scenario below |
| AC-V2-006-003 | test_disabled_null_discussions_skips_repo, test_disabled_null_repository_skips_repo | — | ADR-003 tripwire verified ✅ |
| AC-V2-006-004 | test_enabled_empty_repo_returns_empty_list | — | Code review ✅ |
| AC-V2-006-005 | test_item_id_is_stringified_number | — | ✅ |
| AC-V2-006-006..009 | test_title_mapped, test_body_*, test_url_*, test_created_at_* | — | ✅ |
| AC-V2-006-010 | test_missing_number_returns_none, test_number_none_returns_none | — | ✅ |
| AC-V2-006-011 | test_cursor_pagination_follows_pages, test_config_tunables_* | — | ✅ |
| AC-V2-006-012 | test_early_stop_mid_pagination_requests_no_further_pages | — | ADR-001 + tripwire ✅ |
| AC-V2-006-013 | test_truncation_info_log_at_cap | — | ✅ |
| AC-V2-006-014 | test_graphql_non_disabled_errors_raises_collector_error, test_graphql_rate_limited_error_raises_rate_limit_error | — | ✅ |
| AC-V2-006-015 | test_transport_429_retried_then_succeeds, test_transport_401_raises_auth_error | — | ✅ |
| AC-V2-006-016 | test_fetch_discussions_issues_exactly_one_post_per_page + ADR-002 regression tests | — | GET regression verified ✅ |
| AC-V2-006-017 | 4 token-leak tests | — | All 4 independently run and PASS ✅ |
| AC-V2-006-018 | Structural (no Protocol change) | Verified by absence of ports.py change | Code review ✅ |
| AC-V2-006-019 | test_issues_releases_discussions_concatenated_before_delta | — | R1 invariant verified ✅ |
| AC-V2-006-020 | test_discussion_delta_suppressed_on_rerun_renderer_group_unchanged | — | ✅ |
| AC-V2-006-021 | Same as AC-020 | Renderer group asserted ("Discussion" in digest) | ✅ |
| AC-V2-006-022 | test_discussion_fetch_failure_issues_releases_survive + inner-guard tests | — | All 3 tripwire tests PASS ✅ |

**Gap found (non-blocking)**: AC-V2-006-002 shallow on the boundary — no test for a discussion
created exactly at the cutoff boundary (`days_ago == lookback_days` exactly). However, the
implementation uses `<` (not `<=`), meaning a discussion at exactly the cutoff is included.
The spec says "at or after the cutoff" which confirms `<` is correct. No bug — SHALLOW_TC only.

---

## Test Scenarios (independent verification of risky areas)

| AC-ID | Scenario | How to verify | Expected | Priority | Result |
|-------|----------|---------------|----------|----------|--------|
| ADR-003 | `test_disabled_null_shape_detected_BEFORE_errors_raise`: payload with null discussions AND SOME_OTHER_ERROR → SKIP, not raise | Run test verbosely | Returns [] without raising | Critical | ✅ PASS |
| ADR-002 | `test_fetch_items_still_issues_get_adr002_regression`: fetch_items uses GET | Run test verbosely | request.method == "GET", no body | Critical | ✅ PASS |
| ADR-002 | `test_fetch_releases_still_issues_get_adr002_regression`: fetch_releases uses GET | Run test verbosely | request.method == "GET", no body | Critical | ✅ PASS |
| AC-V2-006-017 | `test_token_not_in_graphql_request_body`: raw POST bytes do not contain TOKEN sentinel | Run test verbosely | TOKEN not in body bytes | Critical | ✅ PASS |
| AC-V2-006-022 | `test_discussion_auth_error_not_swallowed_by_inner_guard`: AuthError propagates | Run test verbosely | pytest.raises(AuthError) | Critical | ✅ PASS |
| AC-V2-006-022 | `test_discussion_rate_limit_error_not_swallowed_by_inner_guard`: RateLimitError breaks loop, partial deliver | Run test verbosely | deliver.assert_called_once() + no raise | High | ✅ PASS |
| AC-V2-006-019 | `test_discussion_fetch_failure_issues_releases_survive`: mark_seen([issue_a, rel_a]), mark_seen([issue_b, disc_b]) | Run test verbosely; check call args | Exact args match — R1 invariant | High | ✅ PASS |
| AC-V2-006-003 | `_classify_graphql` fixture shape: discussions_null=True + errors=[{type:NOT_FOUND,...}] | Code review of graphql_response helper vs GitHub docs pattern | Matches expected disabled-Discussions payload shape | High | ✅ (see note) |
| AC-V2-006-014 | `test_graphql_rate_limited_error_raises_rate_limit_error`: RATE_LIMITED type → RateLimitError | Run test | raises RateLimitError | High | ✅ PASS |

**ADR-003 fixture note (active concern from _state.json)**:
The `graphql_response(discussions_null=True, errors=[...])` fixture sets
`data.repository.discussions = null` plus a top-level `errors` array. This matches the documented
GitHub Discussions-disabled behavior pattern (null connection + errors). The `_classify_graphql`
implementation keys on the null shape, not the error type string, which is specifically robust to
any GitHub error wording. Fixture is well-structured for the purpose; the shape-first ordering is
load-bearing and is pinned by the dedicated tripwire test. Verdict: fixture is adequate for the
testing goal. A live API fixture is not available in this environment but is not required given the
shape-first detection strategy.

---

## Code Review Findings (Step 4B)

### Security Audit Results

Reviewed against OWASP checklist for the discussion path:

| Check | Finding |
|-------|---------|
| Token in GraphQL POST body | ✅ PASS — body contains only `query` (fixed constant) + `variables` (owner/name/first/after). Token is in httpx client Authorization header only, not in `json_body` dict |
| Token in error messages | ✅ PASS — AuthError/RateLimitError/CollectorError messages use static strings + `repo` + status code; token never interpolated |
| Token stored on `self` | ✅ PASS — constructor applies token to `self._client.headers` only; no `self._token` attribute |
| TLS verification disabled | ✅ PASS — `verify=True` hardcoded; discussion path reuses same client |
| GraphQL URL from untrusted input | ✅ PASS — `url = f"{cfg.base_url}/graphql"`; `repo` fills only `variables.owner`/`variables.name` |
| Mutation in GraphQL query | ✅ PASS — `_DISCUSSIONS_QUERY` starts with `query(`, never `mutation`; confirmed by `test_fetch_discussions_issues_exactly_one_post_per_page` |
| Query built from untrusted input | ✅ PASS — `_DISCUSSIONS_QUERY` is a module-level constant; `json_body["query"]` always uses it unchanged |
| SSRF via repo in URL | ✅ PASS — `_validate_repo` rejects non-owner/name formats and `.`/`..` path traversal; owner/name fill variables, not URL |
| State/LLM access in fetch_discussions | ✅ PASS — method is pure I/O; no imports of state or summarizer |

### Correctness Review

**ADR-003 check order** (primary risk): `_classify_graphql` lines 323–346 confirm:
1. `if repo_node is None or repo_node.get("discussions") is None` → return SKIP_REPO (line 325–330)
2. `errors = payload.get("errors"); if errors:` → raise (lines 333–344)
3. `return repo_node["discussions"]` (line 347)

Order is correct and load-bearing. Comment explicitly documents "This check MUST precede...".

**Inner guard `isinstance` exclusion**: Lines 195–197 in pipeline.py:
```python
except CollectorError as exc:
    if isinstance(exc, (AuthError, RateLimitError)):
        raise  # propagate fatal / terminal errors to outer arms (AC-V2-006-022)
```
Mirrors release guard at lines 178–183 exactly. Both use the two-arm catch pattern from v2-003
memory lesson. ✅

**R1 invariant**: Lines 204–211:
```python
items = issues + releases + discussions       # AC-V2-006-019: concatenate all 3
new, seen = _partition_new(items, state)      # BEFORE mark_seen — snapshot pre-write
state.mark_seen(items)                        # full list, not just new
```
Order is correct. `_partition_new` is read-only (asserted by existing test). ✅

**`_classify_graphql` return type deviation**: Returns `discussions` connection dict (not nodes list).
Outer loop calls `conn.get("nodes") or []` safely. The deviation is benign — connection dict
contains `nodes + pageInfo` and avoids a second `.get()` call in the classifier. ✅

**Hollow assertion review** (qa-test-design Phase 3 Mode B static analysis):

Scanned all test files in `tests/github/test_fetch_discussions.py` and `tests/github/test_map_discussion.py`:

- No [H1] existence-only checks found — all tests assert field values or exception types, not just `is not None` alone
- No [H2] UI checks (CLI tool, no UI surface)
- No [H3] vague expected found — all assertions use exact equality or specific membership checks
- No [H4] BVA missing boundary: the AC-V2-006-002 boundary edge case (exactly at cutoff) is noted above as shallow but non-blocking
- No [H5] negative case missing error message: `test_token_never_in_auth_error_message` and `test_token_never_in_rate_limit_error_message` assert exact error message content (token absence)

Slight concern: `test_graphql_non_disabled_errors_raises_collector_error` does not assert the error message content — only that `CollectorError` is raised. Acceptable: the spec says "surfaces a clear error", not a specific message. Non-blocking.

One `test_token_never_in_log_lines_on_graphql_path` uses `record.getMessage()` which correctly captures the formatted log message. Assertion quality is correct.

**Pipeline test review**: The `test_discussion_fetch_failure_issues_releases_survive` test uses
`assert_any_call([issue_a, rel_a])` and `assert_any_call([issue_b, disc_b])`. This correctly
asserts the exact argument to each `mark_seen` call. The `call_count == 2` assertion ensures no
extra calls sneak in. ✅

---

## Bug List

No bugs found.

---

## AC Coverage Summary

- Total ACs: 22
- Covered by Dev (unit/integration tests): 22
- Independently verified by QA code review: 22
- Not covered: 0
- Shallow TC (non-blocking): 1 (AC-V2-006-002 — exact-boundary edge case; correct behavior confirmed by code review)

---

## CMS UI Visual QA

N/A — CLI tool, no Figma URL, no UI surface.

---

## Dependency Vulnerability Audit

`uv audit` (experimental): **0 known vulnerabilities and 0 adverse project statuses in 63 packages**.
Clean. No HIGH/CRITICAL findings. Passes the audit gate.

---

## Decision: GO ✅

**Reasoning**: All 22 ACs verified. 550/550 tests pass. Coverage 96.25% total (client.py 99%,
pipeline.py 93%) — well above the 80% threshold. All 10 critical tripwire tests pass:
ADR-003 null-shape-before-errors order ✅, ADR-002 GET-only regression ✅, token-not-in-body ✅,
inner-guard AuthError/RateLimitError not swallowed ✅, R1 partition-before-mark_seen invariant ✅.
Security audit: 0 findings. Dependency audit: 0 HIGH/CRITICAL. Lint: clean. Tasks: 18/18 [x].
No Critical or High bugs. The one shallow TC (AC-V2-006-002 boundary) is non-blocking and
confirmed-correct by code review.

## Blockers

None.
