---
name: cross-artifact-audit
description: >
  Cross-artifact consistency audit between proposal.md + spec deltas, design.md, openapi.yaml, and tasks.md.
  Inspired by SpecKit's speckit.analyze. Detects: coverage gaps (AC without task), orphan tasks
  (task without AC), terminology drift, API contract mismatches, DB schema gaps.
  Run between S3→S4 (before build) or S4→S5 (before QA). Read-only — produces report, no file edits.
---

# Cross-Artifact Audit

> **Convergence:** at `rigor=full` the orchestrator re-invokes this audit in a loop until the
> CRITICAL/gap set is empty and unchanged `gates.stable_rounds` times (sdlc-orchestration-core
> §Convergence loop). Keep findings **deterministic** — same artifacts → same gap set, stable
> AC-ID / gap keys — so the loop terminates. At `rigor=lite` it runs exactly once.

## When to Use
- After S3 (architect) completes design.md + tasks.md — before S4 build starts
- After S4 (developer) completes — before S5 QA starts
- When suspecting spec-code drift

## Execution

### Step 1: Load Artifacts
Read from CHANGE_DIR (`openspec/changes/<change>/`):
- `proposal.md` + spec deltas — extract all AC-IDs, BR-IDs, INT-IDs from the Structured Extract / scenarios
- `design.md` — extract API endpoints, DB tables, error mappings
- `openapi.yaml` — extract paths, methods, request/response schemas
- `tasks.md` — extract all task items with AC-ID references and file paths

### Step 2: Build Coverage Matrix

| AC-ID | In spec? | In design? | In openapi? | In tasks? | In code? | Status |
|-------|-----------------|------------|-------------|-----------|----------|--------|

For each AC-ID from the spec deltas:
- Check if design.md references it
- Check if tasks.md has at least 1 task referencing it
- Check if openapi.yaml covers the endpoint (for API-related ACs)

### Step 3: Detection Passes

**A. Coverage Gaps** (CRITICAL)
- AC with 0 tasks → requirement will not be implemented
- AC with 0 design reference → requirement not designed

**B. Orphan Tasks** (HIGH)
- Task referencing no AC-ID → untraceable work
- Task referencing non-existent AC-ID → typo or stale reference

**C. API Contract Mismatch** (HIGH)
- Endpoint in design.md but missing from openapi.yaml
- Endpoint in openapi.yaml but not in design.md
- Response format not matching `{ data, meta }` / `{ errors, meta }` convention

**D. Terminology Drift** (MEDIUM)
- Same entity named differently across files (e.g., "product" vs "item")
- Inconsistent field names between design.md DB schema and openapi.yaml

**E. Task Ordering Issues** (MEDIUM)
- Test task before code task it tests
- Controller task before service task it depends on
- Missing checkpoint tasks (< 2 checkpoints)

### Step 4: Severity Assignment
- CRITICAL: AC with zero coverage, API contract mismatch
- HIGH: Orphan tasks, missing design reference
- MEDIUM: Terminology drift, ordering issues
- LOW: Style inconsistencies

### Step 5: Output Report

```markdown
## Cross-Artifact Audit Report — {ticket_id}
Date: {date}

### Coverage Matrix
| AC-ID | spec | design | openapi | tasks | Status |
|-------|-------------|--------|---------|-------|--------|

### Findings
| # | Category | Severity | Location | Summary | Recommendation |
|---|----------|----------|----------|---------|----------------|

### Metrics
- Total ACs: {N}
- Covered (all artifacts): {X} ({X/N}%)
- Partial coverage: {Y}
- Zero coverage: {Z} ← BLOCKERS

### Recommendation
- {PROCEED / STOP — fix before continuing}
```

## Rules
- READ-ONLY — never modify artifacts
- Report findings, do not fix them
- If CRITICAL findings → recommend STOP before next phase
- Reference exact AC-IDs and file locations
