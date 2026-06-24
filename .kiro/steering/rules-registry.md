---
title: Rules Registry
version: 1.2.0
scope: all-projects
last_reconciled: 2026-05-07
---

# Rules Registry

Canonical rule IDs referenced across all agents and skills.
For full details, read the corresponding rule file.

> **Conflict resolution**: When rules conflict with parity port requirements, see `governance-priority.md` (R-GOV-001). Rules below have `Scope:` annotations where they don't apply universally.

| ID | Rule | Detail File | Scope |
|----|------|-------------|-------|
| R-GOV-001 | Governance priority chain: parity > security > API > DDD > style. Doc status taxonomy: authoritative / descriptive / aspirational / stale. | `governance-priority.md` | All projects |
| R-COV-001 | Test coverage ≥ 80% (lines, branches, functions). CI hard fail below threshold. | — | All projects |
| R-SEC-001 | No hardcoded secrets. Zero tolerance. | `security.md` | All projects |
| R-SEC-002 | No PII in logs. Mask email, phone, tokens. | `security.md` | All projects |
| R-SEC-003 | Input validation on all DTOs/Requests. Parameterized queries only. | `security.md` | All projects |
| R-API-001 | Response format: `{ data, meta }` success, `{ errors, meta }` error. | `api-standards.md` | **Greenfield only** — `/v6.0/*` follows PHP parity contract |
| R-API-002 | URL: plural nouns, kebab-case, max 2 nested levels, versioned. | `api-standards.md` | All endpoints |
| R-API-003 | OpenAPI documentation mandatory. openapi.yaml is S3 output. | `api-standards.md` | All endpoints |
| R-DB-001 | All schema changes via migration. Must have rollback. Immutable after deploy. | stack conventions | **Greenfield tables only** — legacy schema is frozen, use `prisma db pull` |
| R-GIT-001 | Commit: `<type>(<scope>): <ticket-id> <subject>`. | `commit-policy.md` | All projects |
| R-SDLC-001 | Source of truth: specs → design → code. Never update specs from code. | `sdlc-workflow.md` | All projects |
| R-SDLC-002 | SPEC LOCK required before S3. BA + Dev + QC sign-off, no TBD. | `sdlc-workflow.md` | All projects |
