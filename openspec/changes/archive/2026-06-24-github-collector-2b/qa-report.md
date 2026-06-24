# S5 QA Report — 2b (github-collector-2b)
Date: 2026-06-24
QA Mode: Retest (bugfix — regression-only gate override)

## Gate Checklist
| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ threshold (80% lines) | ✅ 98.89% total · client.py 99% |
| All required tasks `[x]` | ✅ (3/3 bug fixes done per dev-test-report) |
| Self-review log present | ✅ 4 entries in dev-test-report.md |
| Integration smoke test | ✅ `from osspulse.github import GitHubCollector` → OK (import chain clean, no new deps) |
| Structured logging wired | ✅ unchanged from github-collector-2 — `logging.getLogger(__name__)` |

## Retest Scenarios — Watch Items

| Bug # | AC-ID | Scenario | How verified | Result |
|-------|-------|----------|--------------|--------|
| BUG-1 | AC-2-010 | Integer `created_at` (e.g. 12345) skipped, no `AttributeError` | Code review: `isinstance(created, str)` guard fires before `_parse_created()`; `None` guard already present before it. Integer path → two `continue`s, `_parse_created` never called. | ✅ |
| BUG-2 | AC-2-009 | 403 FAIL_FAST path: TOKEN absent from AuthError message | Code review: `test_auth_failures_fail_fast[403]` now has `assert TOKEN not in str(exc_info.value)` — same assertion as 401 path. Test run: PASSED. | ✅ |
| BUG-3 | AC-2-013 | `verify=True` assertion kills `verify=False` mutation | Code review: `patch.object(httpx.Client, "__init__", capturing_init)` wraps real init, captures `verify` kwarg, asserts `True`. Context manager tears down cleanly — no leakage to adjacent tests. Test run: PASSED. | ✅ |
| Teardown | — | BUG-3 patch torn down between tests (no leakage) | `with patch.object(...)` CM restores original `__init__` on exit. `close()` called inside `with`. 76 tests run in sequence — all pass, no interference. | ✅ |

## Regression Results

Full suite run independently by QA:

```
76 passed in 0.40s
Coverage: 98.89% (≥80% ✅)
client.py: 99% — 1 miss: line 246 (unreachable `# pragma: no cover`)
```

No regressions. Dev reported 76/76; QA independently confirmed 76/76.

## Code Review — Targeted

**BUG-1 fix** (`client.py` lines ~244-246):
- Guard placed correctly: `None` check → `isinstance` check → `_parse_created()`. Order matters — both guards must precede the parse call. ✅
- `_map_item` is NOT affected: it stores `created_at` verbatim without calling `_parse_created`. No regression risk. ✅
- `_parse_created` itself unchanged — only call sites are guarded. ✅

**BUG-2 fix** (`test_github_client.py` — `test_auth_failures_fail_fast`):
- `pytest.raises(AuthError) as exc_info:` capture was already there for both parametrize values. Only the `assert TOKEN not in str(exc_info.value)` line was added. ✅
- 401 path: `AuthError(f"GitHub auth failed for '{repo}' (status 401)")` — no token. ✅
- 403 path: same f-string, same result. Production code was correct; test was the gap. ✅

**BUG-3 fix** (`test_github_client.py` — `test_default_client_enables_tls_verification`):
- `real_init = httpx.Client.__init__` captured before patch. `capturing_init` delegates to `real_init` → fully functional client. ✅
- `collector._client.close()` called inside `with` block → no resource leak. ✅
- `with patch.object(...)` → CM guarantees restore even if test raises. ✅
- Mutation test: `verify=False` → `captured["verify"] is True` → `AssertionError`. Mutation killed. ✅

## AC Coverage Summary
- Total ACs in scope: 3 (AC-2-010, AC-2-009, AC-2-013) — bugfix targets only
- Retested by QA: 3/3
- New regressions: 0
- Full AC coverage from github-collector-2 (27/27) unchanged — no ACs were modified

## CMS UI Visual QA
N/A — CLI tool, no Figma URL.

## Dependency Vulnerability Audit
No new dependencies introduced. Assessment unchanged from github-collector-2: LOW RISK.

## Decision: **GO**

All 3 bugs verified fixed. 76/76 tests passing. 0 new regressions. 0 Critical/High bugs.
Watch items confirmed: teardown clean, integer guard correct, 403 token assertion present.

## Blockers
None.
