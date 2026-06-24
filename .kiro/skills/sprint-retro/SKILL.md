---
name: sprint-retro
description: >
  Sprint/Feature retrospective: đánh giá SDLC execution, SDLC cost violations,
  AI detection rate, loop-backs, và action items cụ thể cho lần sau.
  Dùng sau khi hoàn thành một feature (S6) hoặc cuối sprint.
---

# Sprint Retro — My Project AI-Augmented SDLC

Retrospective tool cho AI-Augmented SDLC, aligned với `.kiro/steering/sdlc-workflow.md`.

## When to Activate

- Sau S6 Release Prep của mỗi feature
- Cuối sprint (weekly/bi-weekly)
- Sau incident hoặc major bug từ production

## How to Use

```
Dùng skill sprint-retro để review feature: cms-product-management
Dùng skill sprint-retro để review sprint: Sprint 2026-W14
```

Cung cấp context nếu có:
- Link đến `specs/` của feature
- Git log range: `git log --oneline origin/main..HEAD`
- Test coverage report
- Số bugs/issues được tạo trong sprint

## Retro Framework: SDLC-Aware 4Ls + Gate Audit

### 1. Gate Compliance Check

Kiểm tra từng SDLC gate đã được respect:

| Gate | Expected Output | Actual | Notes |
|------|-----------------|--------|-------|
| S1 → S2 | Requirement Pack với ACs | ✅/❌ | |
| S2 → S3-sketch | Functional Spec approved | ✅/❌ | |
| S3-sketch → S3 | Design Sketch approved | ✅/❌ | |
| S3 → S4 | Spec Lock (no changes after this) | ✅/❌ | |
| S4 → S5 | Tests pass + coverage ≥80% | ✅/❌ | |
| S5 → S6 | QA GO + 0 Critical bugs | ✅/❌ | |

**Gate violations** = Late-stage changes = Cost multiplier applied.

### 2. Cost Escalation Audit

Dựa trên SDLC cost model (from `sdlc-workflow.md`):

```
S4 change in spec → 5× cost
S5 change in design → 5-8× cost
S6 change in S4 code → 2-3× cost
```

Liệt kê:
- Số lần loop-back (S4→S2, S5→S3...)
- Nguyên nhân: Requirement unclear? Design gap? Dev mistake?
- Estimated waste cost multiplier

### 3. AI Performance Metrics

```markdown
| Metric | Target | Actual | Trend |
|--------|--------|--------|-------|
| AI-detectable bugs caught by AI | ≥ 90% | ? | |
| Logic bugs missed by AI | 0 | ? | |
| Spec adherence (no unauthorized deviation) | 100% | ? | |
| Test coverage on new code | ≥ 80% | ? | |
| Hooks fired correctly (architect + qa) | ✅ | ? | |
```

### 4. Standard 4Ls

**What went WELL (Liked)**
- [ ] AI-generated drafts quality
- [ ] Gate process efficiency
- [ ] Test coverage achieved
- [ ] Deployment smoothness

**What we LEARNED (Learned)**
- Requirements ambiguities discovered late
- Design decisions that changed in S4
- New patterns found

**What we LACKED (Lacked)**
- Missing skills/patterns in `.kiro/skills/`
- Gaps in agents prompts
- Hooks not triggered as expected

**What we LONGED FOR (Longed For)**
- Process improvements needed
- New tools/skills to add
- Workflow automation opportunities

### 5. Action Items Template

```markdown
## Retro Action Items — {Feature/Sprint}

### Process (SDLC)
- [ ] [Owner] Add AC template to analyst.md for edge case coverage by {date}
- [ ] [Owner] Update architect review hook to catch {specific pattern}

### Skills/Knowledge Base
- [ ] [Owner] Add pattern X to backend-patterns/SKILL.md
- [ ] [Owner] Create new skill for Y

### Team/AI
- [ ] [Owner] Clarify scope definition in S1 intake checklist
- [ ] [Owner] Add missing test templates to test-generator/SKILL.md
```

## Output Format

```markdown
## Sprint Retro: {Feature/Sprint Name}

### Gate Compliance: X/6 gates passed (Y violations)
**Violations:**
- S3→S4 Spec Lock broken: 2 requirement changes after S4 started
  → Cost impact: estimated 2×5× = 10× wasted effort on 2 tasks

### AI Performance
- AI-detectable bugs caught: 8/10 (80%) — target 90%
  → Missed: null check in order.service.ts, missing auth guard on /admin endpoint
- Test coverage: 83% (target 80%) ✅
- Unauthorized spec deviations: 1 (payment endpoint URL changed without update)

### 4Ls Summary
- Liked: AI-generated DTO boilerplate saved ~2h
- Learned: Scope ambiguity in "archive" vs "delete" requirements
- Lacked: No skill for pagination response validation
- Longed For: Automated spec lock enforcement in hooks

### Action Items (3 max per retro)
1. [ ] Add "archive vs delete" disambiguation to S1 intake template [Analyst] [+1wk]
2. [ ] Create pagination-response skill [Developer] [+1wk]
3. [ ] Add spec lock warning to feature-orchestrator hook [DevOps] [+2wk]

### Trend: Sprint Health Score: 72/100 (prev: 65) ↑
```
