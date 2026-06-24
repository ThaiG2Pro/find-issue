# Release — 2b (github-collector-2b)
Date: 2026-06-24
Deploy strategy: direct

## Release Notes
**Bug fixes**
- `fetch_items`: guard against non-string `created_at` (e.g. integer) — skip item instead of crashing with `AttributeError` (AC-2-010)
- `test_auth_failures_fail_fast`: extended 403 path to assert token absent from `AuthError` message (AC-2-009)
- `test_default_client_enables_tls_verification`: hardened to kill `verify=False` mutation via `patch.object` (AC-2-013)

**Breaking changes**
- None

## Migration Checklist
No migrations — this change touches only `client.py` (1-line guard) and `test_github_client.py` (2 test updates). No schema changes.

## Rollback Plan
1. Revert `src/osspulse/github/client.py` — remove the `isinstance(created, str)` guard line
2. Revert `tests/test_github_client.py` — restore original `test_auth_failures_fail_fast` and `test_default_client_enables_tls_verification`
3. Run `uv run pytest` to confirm 76/76 pass on reverted state

Impact of rollback: BUG-1 non-string guard lost (Low risk — GitHub API never returns non-string). BUG-2/3 test quality regressed (test-only, no production impact).

## Post-Deploy Smoke Test
- [ ] `uv run pytest` → 76/76 pass
- [ ] `uv run pytest --cov` → coverage ≥ 80%
- [ ] `from osspulse.github import GitHubCollector` imports cleanly

## Archive
- [ ] `openspec archive "github-collector-2b"` run — spec deltas merged into the living spec, change moved to openspec/changes/archive/
