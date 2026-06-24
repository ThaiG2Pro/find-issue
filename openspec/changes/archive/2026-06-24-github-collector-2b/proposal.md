# Proposal — github-collector-2b (bugfix)

## Summary
Fix 3 Low-severity bugs left by QA in github-collector-2 (ticket 2b). All bugs are in
`src/osspulse/github/client.py` or `tests/test_github_client.py`. Source code is correct
for BUG-2 and BUG-3; only BUG-1 requires a production code change.

## Bugs

### BUG-1 — `_parse_created` unguarded against non-string `created_at` (AC-2-010)
File: `src/osspulse/github/client.py` — `fetch_items()` before `_parse_created()` call
Fix: add `if not isinstance(created, str): continue` guard in `fetch_items` before calling
`_parse_created(created)`. Defensive guard against extreme API misbehavior.

### BUG-2 — 403 FAIL_FAST path missing token-absence assertion (AC-2-009)
File: `tests/test_github_client.py` — `test_auth_failures_fail_fast`
Fix: extend the existing parametrized test to assert `TOKEN not in str(exc_info.value)`
for the 403 non-rate-limit path (mirrors existing 401 assertion).

### BUG-3 — TLS verify test cannot kill `verify=False` mutation (AC-2-013)
File: `tests/test_github_client.py` — `test_default_client_enables_tls_verification`
Fix: patch `httpx.Client.__init__` (via `unittest.mock.patch`) to capture the `verify`
argument passed during `GitHubCollector.__init__`, assert `verify=True` was passed.

## Scope
- No design change, no API change, no new dependencies.
- No spec delta needed (behavior unchanged — BUG-1 fix is dirty-data guard already implied
  by AC-2-010 "guard against null/missing"; BUG-2/3 are test-only).
- Regression scope (S5): retest the 3 affected test cases + run full suite.
