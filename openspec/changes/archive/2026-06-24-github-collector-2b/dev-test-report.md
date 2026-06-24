# Dev Test Report — github-collector-2b (bugfix)
Date: 2026-06-24
Phase: S4-fix

## Summary
Fixed 3 Low bugs left by QA in github-collector-2. 76/76 tests passing, 98.89% coverage.

## Bug Fixes

| Bug # | AC-ID | Fix | File | Status |
|-------|-------|-----|------|--------|
| BUG-1 | AC-2-010 | Added `if not isinstance(created, str): continue` before `_parse_created(created)` in `fetch_items` | `src/osspulse/github/client.py` | ✅ Fixed |
| BUG-2 | AC-2-009 | Extended `test_auth_failures_fail_fast` to assert `TOKEN not in str(exc_info.value)` for 403 path | `tests/test_github_client.py` | ✅ Fixed |
| BUG-3 | AC-2-013 | Replaced thin header-check test with `patch.object(httpx.Client, "__init__", ...)` to capture `verify` kwarg; asserts `verify=True` was passed | `tests/test_github_client.py` | ✅ Fixed |

## Verification Results

| Check | Result |
|-------|--------|
| ruff lint | ✅ 0 errors |
| ruff format | ✅ formatted |
| pytest (76 tests) | ✅ 76/76 passed |
| Coverage total | ✅ 98.89% (≥80% threshold) |
| client.py coverage | ✅ 99% (1 miss: line 246 = unreachable pragma) |

## Test Mutation Verification — BUG-3
Verified: changing `verify=True` to `verify=False` in `client.py` now causes
`test_default_client_enables_tls_verification` to FAIL (assertion `captured["verify"] is True`
→ `False`). Mutation is killed.

## Self-Review Log
- [LOW] BUG-1 guard placed before `_parse_created()` call, after `None` guard — correct order
- [LOW] BUG-2 uses same `exc_info` capture already present in `with pytest.raises(AuthError) as exc_info` block — minimal change
- [LOW] BUG-3 calls `real_init` to keep client valid; calls `close()` to prevent resource leak
- No design deviations. No new dependencies. Source code for BUG-2/3 was already correct.

## Design Deviations
None.
