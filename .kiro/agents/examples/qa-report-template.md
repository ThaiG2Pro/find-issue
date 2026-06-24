---
name: qa-report-template
description: >
  Template for {CHANGE_DIR}/qa-report.md — the standalone S5 gate artifact (S5->S6). QA writes
  this BEFORE updating CPP. Contains: gate checklist, test scenarios, bug list (classification +
  RCA phase), AC coverage, visual QA, dependency audit, GO/NO-GO decision + blockers.
---

# S5 QA Report — {ticket_id} ({change-name})
Date: {ISO date}
QA Mode: {Smart | Full | Retest}

## Gate Checklist
| Item | Result |
|------|--------|
| dev-test-report.md present | {✅ / ✗} |
| Coverage ≥ threshold | {✅ {X}% / ✗} |
| All required tasks `[x]` | {✅ / ✗} |
| Self-review log present | {✅ / ✗} |
| Integration smoke test (real run, not deferred) | {✅ / ✗} |
| `.env.example` ≥ 10 lines · README ≥ 10 lines · structured logging wired | {✅ / ✗} |

## Test Scenarios (generated for uncovered ACs)
| AC-ID | Scenario | How to verify | Expected | Priority | Result |
|-------|----------|---------------|----------|----------|--------|
| AC-{ticket}-001 | {scenario} | {request → check} | {expected} | High | {✅ / ❌} |
| AC-{ticket}-010 | SQL injection in search | search=' OR 1=1 → rejected | not 5xx | Critical | {✅ / ❌} |

## Bug List
| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| 1 | {title} | AC-{ticket}-{NNN} | {Critical/High/Medium/Low} | {[AI-DETECTABLE]/[LOGIC-BUG]/[EDGE-CASE]/[SPEC-UNCLEAR]} | {S4/S3/S2} |

<!-- For each Critical/High bug, expand with: Steps to reproduce, Expected (from AC), Actual, File:line. -->

## AC Coverage Summary
- Total ACs: {N}
- Covered by Dev (unit tests): {X}
- Independently verified by QA this session: {Y}
- Not covered: {Z} — {reasons}

## CMS UI Visual QA
{PASS / PARTIAL / FAIL — deviations vs Figma, or "N/A — no Figma URL"}

## Dependency Vulnerability Audit
{0 HIGH/CRITICAL — clean | list HIGH/CRITICAL findings (block GO) | MODERATE noted as risk}

## Decision: {GO | NO-GO}
{1-line reason}

## Blockers (if NO-GO)
- {blocker} — recommended action: {S4 fix / S3 redesign / S2 re-spec}
