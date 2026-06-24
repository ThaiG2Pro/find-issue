# Release — 2 (github-collector-2)
Date: 2026-06-24
Deploy strategy: direct (CLI tool — no server, no blue-green needed)

## Release Notes

**Features**
- GitHub Collector V1: fetch newly-opened issues for a repo via GitHub REST API and return
  `RawItem`s (AC-2-001..004, AC-2-016, AC-2-017) — pure I/O, no State Store / LLM access
  (AC-2-015)
- Bounded pagination via `Link: rel="next"` with per-item lookback cutoff and
  `max_items_per_repo` cap + truncation log (AC-2-005, AC-2-006, AC-2-007)
- Config-driven tunables: `CollectorConfig` + `RetryPolicy` frozen dataclasses — no
  hardcoded literals in the fetch loop (AC-2-024..027, BR-2-013/014)
- Pull-request exclusion (AC-2-018); dirty-data tolerance on all optional fields (AC-2-010,
  AC-2-012)
- Token isolation: `Authorization: Bearer <token>` set on httpx client at construction only,
  never logged/echoed/returned (AC-2-009, ADR-004)
- Per-repo error isolation: 404/410 → warn + skip; 401/non-rate-limit 403 → fail-fast
  (AC-2-008, AC-2-011)
- Bounded retry with exponential backoff + jitter + `Retry-After` precedence, capped by
  ceiling (AC-2-019..023, AC-2-026)
- Secondary rate-limit (403 + `X-RateLimit-Remaining: 0`) → RETRY not AuthError (AC-2-020)
- Repo validation: `REPO_PATTERN` (promoted from `_REPO_RE`) + defense-in-depth `.`/`..`
  traversal guard (AC-2-014, ADR-006, T-T2)
- TLS verification always on; GET-only; `base_url` from config never from untrusted input
  (AC-2-013, AC-2-025, ADR-008)

**Bug fixes**
- None (greenfield feature)

**Breaking changes**
- `osspulse.config._REPO_RE` renamed to `REPO_PATTERN` (public). Any code importing
  `_REPO_RE` directly will get an `AttributeError`. Internal only — no external callers
  in V1. `_validate_repos` updated in-place.

## Migration Checklist
| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | N/A — pure I/O, no DB tables, no migrations | — | — | no | n/a |

## Rollback Plan
1. `git revert` the merge commit (or `git checkout <prev-sha> -- src/osspulse/github/ tests/test_github_client.py src/osspulse/config.py`)
2. No migrations to roll back (no DB changes)
3. Confirm: `uv run pytest` passes on the reverted tree; `from osspulse.github import GitHubCollector` fails (as expected on rollback)

## Post-Deploy Smoke Test
- [ ] `uv run python -c "from osspulse.github import GitHubCollector, CollectorConfig, RetryPolicy; print('import OK')"` → `import OK`
- [ ] `uv run pytest tests/test_github_client.py -q` → 43 passed, 0 failed
- [ ] `uv run pytest --cov=osspulse -q` → ≥99% coverage, 76 passed
- [ ] `uv run ruff check src tests` → `All checks passed!`
- [ ] `CollectorConfig()` repr does not contain token literal

## Known Post-Release Follow-ups (Low, non-blocking)
- BUG-1: Add `isinstance(created, str)` guard in `fetch_items` before `_parse_created(created)`
- BUG-2: Add `TOKEN not in str(exc_info.value)` assertion to `test_auth_failures_fail_fast(403)`
- BUG-3: Harden TLS-verify test (httpx constructor patching approach)
- Consider hardening shared `REPO_PATTERN` to reject `..` segments (architect decision)
- Add `README.md` + expand `.env.example` with collector tunable documentation

## Archive
- [ ] `openspec archive "github-collector-2"` run — spec deltas merged into the living spec, change moved to openspec/changes/archive/
