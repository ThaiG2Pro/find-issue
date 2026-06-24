---
title: AI-Augmented SDLC Workflow
version: 2.2.0
scope: all-projects
---

# AI-Augmented SDLC Workflow

🤖 AI owns the draft · 👤 Human owns the decision · 🔒 Spec locked before code · 🔴 Gate fail = STOP

## Input Sources (before S1)

S1 analyst needs raw requirements to produce `proposal.md`. Three sources, combinable:

| Source | Convention | When to use |
|--------|-----------|-------------|
| **docs folder** | `docs/<ticket-id>-<slug>/` (e.g., `docs/1234-feature-voucher-redeem/`) | BA has attachments (Word, PDF, Figma exports, screenshots). No sub-structure required — drop any file in. |
| **Redmine ticket** | `sdlc feature <module> --ticket=1234` | Ticket exists in Redmine; AI fetches subject, description, attachments, comments automatically. Requires Redmine MCP/config. |
| **Direct chat** | No ticket, no docs | Smallest changes; analyst asks user directly. |

**Combinable**: `--ticket=1234` + a matching `docs/1234-feature-xxx/` folder → AI reads both.

Folder naming rules:
- Prefix with ticket ID when one exists — makes reverse lookup trivial.
- Use kebab-case slug that matches the eventual OpenSpec change name (`add-voucher-redeem`, `update-merchant-flow`).
- One folder per feature. Do NOT dump multiple features into one folder.
- Folder is INPUT only — S1 output (`proposal.md`) lives in `openspec/changes/<change>/`, never in `docs/`.

## Git Branch Policy (R-SDLC-003)

**Mỗi feature PHẢI có nhánh riêng. KHÔNG code trên nhánh của feature cũ.**

Khi orchestrator nhận lệnh `sdlc feature {ticket} {slug}`:

```
1. Xác định base branch: nhánh hiện tại (feature trước đã hoàn thành)
2. Tạo và switch sang nhánh mới TRƯỚC KHI bắt đầu S1:
   git checkout -b {ticket}-SPEC-{N}
   Ví dụ: 71194-SPEC-03
3. Thông báo cho user: "✅ Đã tạo và switch sang nhánh {branch}"
```

Naming: `{ticket-id}-SPEC-{N}` (e.g., `71194-SPEC-03`). Hotfix: `hotfix/{ticket-id}-{slug}`.

---

## Lifecycle Phases

| Phase | Role | Gate Owner |
|-------|------|------------|
| S1 — Req Intake | Analyst | BA + Dev + QC |
| S2 — Func Spec | Analyst | BA + QC |
| 🔒 SPEC LOCK | Human | BA + Dev + QC |
| S3 — Design (sketch → full) | Architect | Dev + QC |
| S4 — Build | Developer | CI + Dev reviewer |
| S5 — QA | QA | QC Lead |
| S6 — Release | Developer | Dev + QC |

## Fast-Track (hotfix / small changes)

Not every change needs full S1→S6. Use fast-track when:
- Bug fix with clear root cause
- Config/copy change
- Dependency update
- Small refactor (no behavior change)

Fast-track flow: **S4 → S5 (lite) → docs sync → merge**
- Skip S1-S3 for implementation
- Developer writes fix + tests (coverage ≥ 80%)
- QA lite: retest + regression only
- Docs sync (MANDATORY): update affected specs/design to match fix
  - If fix changes API behavior → update `openapi.yaml`
  - If fix changes business logic → update `specs/` AC
  - If fix changes DB schema → update `design.md`
  - Commit docs update separately: `docs(<scope>): <ticket-id> sync spec after fix`
- Commit fix: `fix(<scope>): <ticket-id> <subject>`

⚠ If scope grows during fix → escalate to full SDLC.

## Spec Zone Rules (S1 ↔ S2)

- Loop freely — cost = 1×, iterate until spec is 100% clear
- Do NOT open S3 without SPEC LOCK
- SPEC LOCK = BA + Dev + QC sign-off, no "TBD"
- S3 runs sketch first → if gap found → return to S2/S1

### QA Early Review (after S2, before SPEC LOCK)

Analyst runs lightweight risk scan after completing S2:
1. Scan AC list → find edge cases, missing error handling, security risks
2. Output: `### Early Risk Flags` section at end of specs
3. Critical risks → block SPEC LOCK until addressed
4. Purpose: detect risk at cost 1× instead of 25× at S5

## Source of Truth (R-SDLC-001)

**Immutable flow**: specs → design (+ openapi.yaml) → code

| Artifact | Owner | Rule |
|----------|-------|------|
| `proposal.md` + `specs/` | BA + S2 | Changes only via S1/S2 |
| `design.md` | Architect + S3 | Changes only via S3 |
| `openapi.yaml` | Architect + S3 | Do NOT update from code |
| Code | Developer + S4 | Must follow design |

AI agent rules:
- ❌ Do NOT update openapi.yaml when code changes
- ❌ Do NOT update design.md to "match" code
- ✅ Code diverges from design → flag gap (S4→S3, cost 5×)
- ✅ Requirements change → update specs first → design → code

Requirement change after SPEC LOCK:
1. Update `proposal.md` + `specs/`
2. Update `design.md`
3. Update `openapi.yaml` (if API affected)
4. Commit specs before writing code
5. Implement

## Cost Escalation

| Loop | Cost | Signal |
|------|------|--------|
| S1 ↔ S2 | 🟢 1× | Expected, iterate freely |
| S3 sketch → S2 (spec gap) | 🟡 3× | S3 sketch found gap |
| S4 → S3 (design gap) | 🟠 5× | Needs improvement |
| S4 → S2 (spec gap) | 🟠 5-8× | S2 was weak |
| S5 → S4 (code bug) | 🔴 15× | Normal but expensive |
| S5 → S3 (design gap) | 🔴 20× | S3 was weak |
| S5 → S2 (spec gap) | 💀 25× | S2 was very weak |
| S6 rollback | 💀 75× | S5 was weak |

## Gate Checklists

### SPEC LOCK Gate — R-SDLC-002 (before S3)
- [ ] 100% AC testable — no "TBD"
- [ ] Scope closed
- [ ] BA + Dev + QC sign-off
- [ ] Figma URL in specs (or `Figma: N/A`)
- [ ] Early Risk Flags reviewed — no unaddressed 🔴 Critical risks

### S3 Gate (before S4)
- [ ] `design.md` complete
- [ ] `openapi.yaml` committed (if API) — actual YAML, not pseudo-code
- [ ] DB migrations documented
- [ ] `tasks.md` with dependencies

### S4 Gate (before merge)
- [ ] CI green
- [ ] PR approved
- [ ] R-COV-001: Test coverage ≥ 80%
- [ ] R-SEC-001: Security scan PASS
- [ ] R-SEC-003: Input validation on new DTOs

### S5 Gate (before release)
- [ ] 0 Critical/High bugs open
- [ ] All AC verified

### S6 Gate (before deploy)
- [ ] Migration reviewed
- [ ] Rollback plan documented
- [ ] Stable 30 min post-deploy

## S5 QA Role
- ✅ QA: test, report bugs, classify severity, RCA, GO/NO-GO
- ❌ QA does NOT fix bugs or modify code

Bug Flow: S5 finds bug → Report → NO-GO → S4 fix → S5 retest → GO/NO-GO
