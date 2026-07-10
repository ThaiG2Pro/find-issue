# Sprint Retro — scheduler-cli-7

Date: 2026-07-01
Change: scheduler-cli-7 | Type: feature | Ticket: 7
Pipeline: S1→S6 | Rigor: full | Branch: feature/7-scheduler-cli-7

---

## Gate Compliance: 5/5 passed — 0 violations

| Gate | Expected | Actual | Notes |
|------|----------|--------|-------|
| S1→S2 | Requirement Pack + ACs | ✅ | 22 ACs, 12 BRs, 6 INTs, 20 edge cases, STRIDE PASS |
| 🔒 S2 SPEC LOCK | spec-auditor PASS + openspec validate | ✅ | 6/6 checks, convergence stable=3/3 (4 rounds) |
| 🔍 S3 DESIGN REVIEW | cross-artifact-audit 0 CRITICAL | ✅ | 0 CRITICAL/HIGH/MEDIUM, 22/22 ACs in design+tasks |
| S4→S5 | Tests pass + coverage ≥ 80% | ✅ | 271 pass, 98.51% coverage, 0 lint errors |
| S5→S6 | QA GO + 0 Critical bugs | ✅ | GO, 0 Critical/High, 22/22 ACs verified |

**Loop-backs:** 0
**Cost escalations:** 0

One mid-cycle spec change (D-1 no-LLM placeholder → AC-7-022) arrived mid-S2, before S3 started.
Re-validated and re-audited at SPEC LOCK. The extra convergence round (round 4) was caused by this.
No S2→S3 loop-back — the change was absorbed within the S2 gate.

---

## AI Performance

| Metric | Target | Actual |
|--------|--------|--------|
| AI-detectable bugs caught | ≥ 90% | 100% — 0 production logic bugs |
| Logic bugs missed | 0 | 0 |
| Spec adherence | 100% | 100% — 2 deviations, both justified + documented |
| Test coverage new code | ≥ 80% | 98.51% |
| Hooks fired correctly | ✅ | ✅ — spec-auditor, cross-artifact-audit, pipeline-guard all fired |

Gap: H1-b and H1-c are AI-detectable hollow assertions (Low severity, accepted via code review).

---

## 4Ls

**Liked**
- Perfect gate compliance: 0 loop-backs, 0 cost escalations on a 22-AC feature.
- 98.51% coverage including complex error-ladder and edge-case paths.
- S3 resolved 2 spec gaps (GAP-001, GAP-003) at design level without S2 return.
- No-LLM and Redis degradation paths clean and well-tested.

**Learned**
- `CliRunner` cannot simulate `BrokenPipeError` — mock stdout has no `fileno()`. Live pipe
  smoke test (`osspulse run | head -1`) is the only reliable verification for this AC class.
- Stub→real transition breaks CLI tests that don't mock at the module boundary (`run_pipeline`).
  The mock boundary must move when a stub becomes a real implementation.
- Convergence needed 4 rounds (stable at 3) because a D-1 spec change arrived mid-S2. Scope
  freezes before S2 convergence starts would prevent extra rounds.

**Lacked**
- No `caplog` assertion helper/pattern — caused H1-b hollow log assertion.
- No structural "assert delivered items = expected subset" pattern — caused H1-c hollow deliver assertion.
- `memory/qa.md` didn't exist before this retro — QA lessons had no home.

**Longed For**
- A test utility for `caplog` assertions to prevent H1-b class of hollowness.
- Stub-retirement task template in `tasks.md` that reminds developer to shift mock boundaries.

---

## Action Items

1. [ ] [QA] Improve `test_run_summary_log_emitted_on_success` (H1-b): add `caplog` assertion. [+next cycle]
2. [ ] [QA] Improve `test_summarizer_returns_fewer_items` (H1-c): assert `deliver` arg = survivor items only. [+next cycle]
3. [ ] [Developer] Add `caplog` assertion helper to reduce hollow log-assertion TCs across suite. [+next cycle]

---

## Sprint Health Score: 91/100

Strong: 0 bugs, 0 loop-backs, 98.51% coverage, clean security audit, perfect gate compliance.
Minor deductions: 3 hollow TCs (Low, accepted) and 1 deferred live smoke test (no token in env).

---

## Memory Harvest

- `memory/qa.md` created — 2 lessons: CliRunner/BrokenPipe limitation + H1-b/H1-c hollow TC patterns.
- `memory/developer.md` appended — 1 lesson: stub→real transition breaks CLI tests at wrong mock boundary.
