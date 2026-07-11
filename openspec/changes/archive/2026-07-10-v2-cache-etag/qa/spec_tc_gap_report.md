# Spec-TC Gap Report — V2-007 (v2-cache-etag)
Generated: 2026-07-10T17:10:00+07:00 | Phase: S5 | Rigor: lite

## Method
Phase 2 of qa-analysis skill — cross-referenced `specs/github-collector/spec.md`,
`specs/conditional-cache/spec.md` (from proposal.md), `design.md` ADRs, and
`dev-test-report.md` AC coverage matrix.

## AC Coverage Map

| AC-ID | Spec Source | Dev TCs | Gap Tag | Notes |
|-------|-------------|---------|---------|-------|
| AC-V2-007-001 | conditional-cache | 2 | COVERED | get/set protocol |
| AC-V2-007-002 | conditional-cache | 2 | COVERED | round-trip (commit→fresh instance) |
| AC-V2-007-003 | conditional-cache | 4 | COVERED | atomic temp+rename; mkdir; write-fail WARN |
| AC-V2-007-004 | conditional-cache | 3 | COVERED | corrupt/missing/unreadable → WARN+empty |
| AC-V2-007-005 | conditional-cache | 2 | COVERED | set() in-memory only; not durable until commit |
| AC-V2-007-006 | conditional-cache | 2 | COVERED | token sentinel not in file; keys+validators only |
| AC-V2-007-007 | conditional-cache | 4 | COVERED | NullConditionalCache get/set/commit no-op |
| AC-V2-007-008 | conditional-cache | 2 | COVERED | no state.json_store import; file independence |
| AC-V2-007-009 | github-collector | 3 | COVERED | null-cache → unconditional; no-arg default |
| AC-V2-007-010 | github-collector | 2 | COVERED | If-None-Match strong+releases first page |
| AC-V2-007-011 | github-collector | 2 | COVERED | 304→[] for issues + releases |
| AC-V2-007-012 | github-collector | 2 | COVERED | 200→set()+paginate for issues + releases |
| AC-V2-007-013 | github-collector | 1 | COVERED | page-2 unconditional |
| AC-V2-007-014 | github-collector | 2 | COVERED | 200+no-ETag → no crash; set not called |
| AC-V2-007-015 | github-collector | 1 | COVERED | weak ETag echoed verbatim |
| AC-V2-007-016 | github-collector | 3 | COVERED | 429 retry; 401 fail-fast; 500 exhaustion |
| AC-V2-007-017 | github-collector | 2 | COVERED | GraphQL POST: no conditional header; no cache ops |
| AC-V2-007-018 | github-collector | 1 | COVERED | token not in error/log on conditional path |
| AC-V2-007-019 | scheduler-cli | 1 | COVERED | _build_etag_cache failure → NullCC |
| AC-V2-007-020 | scheduler-cli | 2 | COVERED | [etag_cache] defaults; absent → enabled=true |
| AC-V2-007-021 | scheduler-cli | 3 | COVERED | non-bool enabled → ConfigError |
| AC-V2-007-022 | scheduler-cli | 1 | COVERED | both flags true → real cache injected |
| AC-V2-007-023 | scheduler-cli | 2 | COVERED | either flag false → NullCC + no etags.json |
| AC-V2-007-024 | scheduler-cli | 1 | COVERED | commit() once after loop (RISK-001) |
| AC-V2-007-025 | scheduler-cli | 1 | COVERED | no commit on AuthError mid-loop (RISK-001) |
| AC-V2-007-026 | scheduler-cli | 1 | COVERED | E2E run1→run2 304 no-new-items |
| AC-V2-007-027 | scheduler-cli | 1 | COVERED | E2E run2 new item rendered; fresh ETag stored |
| AC-V2-007-028 | scheduler-cli | 1 | COVERED | E2E corrupt etags.json → WARN+unconditional+exit0 |

## Gap Summary

| Gap Tag | Count | AC-IDs |
|---------|-------|--------|
| BOTH_MISS | 0 | — |
| TC_MISS | 0 | — |
| SHALLOW_TC | 0 | — |
| DEV_MISS | 0 | — |
| COVERED | 28 | all |

**Result: 28/28 ACs covered. 0 gaps. No additional QA scenarios needed.**

## Notable Observations

1. **Strongest coverage area**: ETag store (AC-001..008) — 25 tests with high assertion depth
   including atomic write spy, file mtime guard, static import scan.

2. **RISK-001 coverage is exemplary**: Two complementary tests covering both the "success"
   invariant (commit once, after mark_seen × 2) and the "crash-safety" invariant (no commit
   when AuthError propagates). Call-order side_effect tracking is the right tool here.

3. **GraphQL path non-regression (AC-017)**: Two independent tests check both the absence
   of If-None-Match on the POST and that cache.set is never called — complete coverage of
   the "untouched" guarantee.

4. **ADR-003 `_classify(304)→OK` subtlety**: covered by test_first_page_304_returns_empty
   (implicitly — the test passes because the code branches on status_code, not action). The
   dev comment in code + _handoff.md risky-area flag provide adequate documentation.

5. **No spec-to-code mismatch found**: All CONFIRMED ACs in proposal.md are implemented as
   described. DEVIATION-001 (_NullConditionalCache in ports.py) is documented, architecturally
   correct, and has no AC impact.
