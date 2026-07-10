# Test Cases — V2-003 v2-003-releases
Date: 2026-07-06 | Rigor: lite | Export: md

## Summary
- Total: 28 test cases (P1: 20, P2: 8)
- Techniques: UC (happy path), NEG (negative/error), BVA (boundary), EG (edge/guard), SEC (security)
- Automation: all verified via unit/integration test suite (pytest)

---

## Test Case Table

| Test ID | Technique | Priority | Objective | Requirement | Automation | Status |
|---------|-----------|----------|-----------|-------------|------------|--------|
| TC-001 | [UC] | P1 | Releases within the lookback window are returned as RawItems with item_type="release" | AC-V2-003-001 | Full Auto | ✅ Pass |
| TC-002 | [UC] | P1 | Releases older than the cutoff are excluded from results | AC-V2-003-002 | Full Auto | ✅ Pass |
| TC-003 | [EG] | P1 | Draft release (published_at=null) is skipped without triggering early-stop | AC-V2-003-003 | Full Auto | ✅ Pass |
| TC-004 | [UC] | P1 | Prerelease (prerelease=true) is included in results | AC-V2-003-004 | Full Auto | ✅ Pass |
| TC-005 | [EG] | P1 | Repo with no releases returns empty list without error | AC-V2-003-005 | Full Auto | ✅ Pass |
| TC-006 | [UC] | P1 | item_id equals tag_name | AC-V2-003-006 | Full Auto | ✅ Pass |
| TC-007 | [NEG] | P1 | title falls back to tag_name when name is null | AC-V2-003-007 | Full Auto | ✅ Pass |
| TC-008 | [NEG] | P1 | title falls back to tag_name when name is empty string | AC-V2-003-007 | Full Auto | ✅ Pass |
| TC-009 | [UC] | P2 | title uses name when name is non-empty | AC-V2-003-007 | Full Auto | ✅ Pass |
| TC-010 | [NEG] | P1 | Null body is coerced to empty string | AC-V2-003-008 | Full Auto | ✅ Pass |
| TC-011 | [NEG] | P1 | Null html_url is coerced to empty string | AC-V2-003-009 | Full Auto | ✅ Pass |
| TC-012 | [NEG] | P1 | Missing html_url key results in empty string | AC-V2-003-009 | Full Auto | ✅ Pass |
| TC-013 | [UC] | P1 | created_at stores published_at unchanged (not reformatted) | AC-V2-003-010 | Full Auto | ✅ Pass |
| TC-014 | [NEG] | P1 | Release missing both tag_name and id returns None (skipped) | AC-V2-003-011 | Full Auto | ✅ Pass |
| TC-015 | [EG] | P2 | Release with missing tag_name but present id uses str(id) as item_id | AC-V2-003-011 | Full Auto | ✅ Pass |
| TC-016 | [BVA] | P1 | per_page and max_items_per_repo come from config, not hardcoded | AC-V2-003-012 | Full Auto | ✅ Pass |
| TC-017 | [BVA] | P1 | Early-stop fires on created_at < cutoff mid-pagination, page3 never requested | AC-V2-003-013 | Full Auto | ✅ Pass |
| TC-018 | [EG] | P1 | RISK-002 tripwire: old-created/recent-published release is MISSED by early-stop | AC-V2-003-013 | Full Auto | ✅ Pass (miss confirmed) |
| TC-019 | [BVA] | P1 | Info log emitted when max_items_per_repo cap is reached | AC-V2-003-014 | Full Auto | ✅ Pass |
| TC-020 | [SEC] | P1 | Token value never appears in any log line during release fetch | AC-V2-003-015 | Full Auto | ✅ Pass |
| TC-021 | [SEC] | P1 | Token value never appears in AuthError message on 401 | AC-V2-003-015 | Full Auto | ✅ Pass |
| TC-022 | [NEG] | P1 | 429 rate limit is retried with backoff before succeeding | AC-V2-003-016 | Full Auto | ✅ Pass |
| TC-023 | [NEG] | P1 | Terminal RateLimitError raised when retry budget exhausted | AC-V2-003-016 | Full Auto | ✅ Pass |
| TC-024 | [NEG] | P1 | 404 on /releases returns empty list (repo skipped) | AC-V2-003-017 | Full Auto | ✅ Pass |
| TC-025 | [NEG] | P1 | 410 on /releases returns empty list (repo skipped) | AC-V2-003-017 | Full Auto | ✅ Pass |
| TC-026 | [NEG] | P1 | 401 on /releases raises AuthError (fail fast) | AC-V2-003-017 | Full Auto | ✅ Pass |
| TC-027 | [UC] | P1 | Pipeline concatenates issues + releases before delta partition (AC-019); mark_seen gets full list (R1) | AC-V2-003-019 | Full Auto | ✅ Pass |
| TC-028 | [UC] | P1 | Release rendered run 1, suppressed run 2 with delta; renderer GROUP_ORDER unchanged (AC-020, AC-021) | AC-V2-003-020 / AC-V2-003-021 | Full Auto | ✅ Pass |
| TC-029 | [EG] | P1 | Release fetch failure (CollectorError) → issues survive; other repos unaffected; mark_seen count-invariant (R1) | AC-V2-003-022 | Full Auto | ✅ Pass |
| TC-030 | [EG] | P1 | AuthError from fetch_releases propagates fatal (not swallowed by inner guard) | AC-V2-003-022 | Full Auto | ✅ Pass |
| TC-031 | [SEC] | P2 | ports.py GitHubClient Protocol has no fetch_releases method (ADR-002 frozen) | AC-V2-003-018 | Code Review | ✅ Pass |
| TC-032 | [EG] | P2 | Draft with created_at in-window: skipped via continue, not early-stopped | AC-V2-003-003 | Full Auto | ✅ Pass |
| TC-033 | [UC] | P2 | GROUP_ORDER in renderer.py still = ["issue","discussion","release"] (no renderer delta) | BR-V2-003-004 | Code Review | ✅ Pass |
| TC-034 | [SEC] | P2 | Token never in source code (grep src/) | BR-V2-003-005 | Static Scan | ✅ Pass |
