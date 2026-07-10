# Progress — v2-003-releases (ticket V2-003)

## Status
| Phase | Owner | State | Notes |
|-------|-------|-------|-------|
| S1 Req Intake | analyst | ✅ DONE | proposal.md + 2 spec deltas + CPP artifacts; openspec validate --strict PASS |
| S2 Func Spec | analyst | ✅ DONE | 22/22 ACs CONFIRMED; spec-auditor PASS; openspec validate PASS; SPEC LOCK ✅ 2026-07-06 |
| S3 Design | architect | ✅ DONE | design.md (4 ADRs) + tasks.md (13 tasks, 2 checkpoints); no openapi (CLI, ADR-004); cross-artifact-audit 0 CRITICAL; openspec validate PASS; DESIGN REVIEW ✅ 2026-07-06 |
| S4 Build | developer | ✅ DONE | 459 tests pass, coverage 96% (client 99%, pipeline 96%), 13/13 tasks [x], dev-test-report.md created, 2 minor deviations documented. BUILD GATE ✅ 2026-07-06 |
| S5 QA | qa | ✅ DONE | GO — 0 bugs, 22/22 ACs, 459 tests pass, coverage 96%, testcases.md generated. RISK-002/R1/inner-guard tripwires all confirmed. |
| S6 Release | developer | ✅ DONE | release.md created. No migrations. Archive ran: specs updated (github-collector +4, scheduler-cli ~1). README updated with Releases note. Change archived as 2026-07-06-v2-003-releases. |

## S1 Summary
- **Scope**: add Releases as a pipeline source. Collapsed to Collector (`fetch_releases`) + one
  `pipeline._collect_all` wiring line. Downstream (state, delta, summarizer, renderer) reused unchanged.
- **Deliberate deviation**: NO digest-renderer delta — the renderer already handles `"release"`
  (living AC-5-006/AC-5-011). Documented as Non-Goal + BR-V2-003-004.
- **STRIDE**: SKIPPED — no new attack surface (reuses github-collector-2's authed GET-only client).

## S2 Summary
- **Sign-off**: all 7 previously-[ASSUMED] ACs CONFIRMED by user (draft-exclusion, prerelease-inclusion,
  `item_id = tag_name`, `title` fallback, `created_at = published_at`, newest-first early-stop,
  per-repo release-fetch isolation). No AC text changed — only tags flipped.
- **Counts**: 22 ACs (22 [CONFIRMED], 0 [ASSUMED]), 7 BRs, 4 INTs, 16 edge cases.
- **spec-auditor**: PASS (C1–C6, 0 blockers, 0 warnings).
- **Structural gate**: `openspec change validate v2-003-releases --strict` → PASS.
- **RISK-002 left open**: AC-013 (early-stop) is CONFIRMED; the accept-risk-vs-per-page-filter
  ordering strategy is intentionally deferred to the architect at S3 (a design choice, not a spec gap).

## S4 Summary
- **Coverage**: client.py 99%, pipeline.py 96%, overall 96% (threshold ≥80% ✅)
- **Tests**: 459 passed / 0 failed (26 new tests in tests/github/ + 4 new pipeline tests)
- **Files changed**: `src/osspulse/github/client.py`, `src/osspulse/pipeline.py`
- **Files created**: `tests/github/test_map_release.py`, `tests/github/test_fetch_releases.py`
- **Deviations**: 2 (inner guard catch tuple refinement; test compatibility stubs — both documented in _decisions.jsonl and _handoff.md)
- **Tripwires**: ADR-001 RISK-002 regression ✅, R1 count-invariant ✅, AuthError propagation ✅
- **Secret scan**: 0 token leaks in source ✅

## Next Action
S4 gate PASSED ✅ 2026-07-06. Routed to QA.
Use the **qa** agent → `/s5 V2-003 v2-003-releases`

## S5 Summary
- **Decision**: GO — 0 Critical, 0 High, 0 Medium bugs
- **Coverage**: 22/22 ACs independently verified by code review + test execution
- **Tests**: 459 passed / 0 failed (independent QA run matches Dev report exactly)
- **Tripwires confirmed**:
  - ADR-001 stop key: `test_risk002_regression_*` PASSES → v1.9.9 NOT returned → created_at stop key intact ✅
  - R1 ordering: `mark_seen.assert_any_call([issue_a])` + `assert_any_call([issue_b, rel_b])` ✅
  - Inner guard: `test_release_auth_error_not_swallowed_*` PASSES → AuthError propagates fatal ✅
- **Inner guard deviation**: Two-arm catch pattern confirmed correct (ADR-003); would swallow AuthError if reverted
- **Renderer**: GROUP_ORDER=["issue","discussion","release"] — no delta confirmed ✅
- **Protocol**: ports.py has no fetch_releases — frozen ✅
- **Observation (non-blocking)**: README lacks a note about Releases (proposal mentioned it; not in formal ACs)
- **Coverage tool**: 96% overall, client.py 99%, pipeline.py 96% (threshold 80% ✅)

## Next Action
S5 QA GATE PASSED ✅ 2026-07-06. Routed to developer for S6 archive.
Use the **developer** agent → `/s6 V2-003 v2-003-releases`

## S6 Summary
- **Migration**: None (pure Python change; JSON state store schema is item-type-agnostic)
- **Release artifacts**: `release.md` created (direct deploy strategy, no migrations)
- **README**: Updated — one-liner, Privacy Disclosure, Usage, and Key Technical Decisions now mention Releases (proposal note, non-AC)
- **Archive**: `openspec archive "v2-003-releases"` → PASS
  - `openspec/specs/github-collector/spec.md`: +4 (fetch_releases ACs added)
  - `openspec/specs/scheduler-cli/spec.md`: ~1 (pipeline wiring note updated)
  - Change folder moved to `openspec/changes/archive/2026-07-06-v2-003-releases/`
- **Deploy status**: dev=pending, master=pending (update out-of-band as promotions complete)

## Final State
**CHANGE COMPLETE ✅** — V2-003 (v2-003-releases) fully shipped.
S1→S2→S3→S4→S5→S6 all DONE. 22/22 ACs delivered. 459 tests. 96% coverage. Living spec updated.