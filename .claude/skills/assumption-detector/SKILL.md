---
name: assumption-detector
description: >
  Scan requirements/user input for hidden assumptions that could cause spec gaps.
  Outputs tagged list: [RISKY] assumptions needing validation, [SAFE] documented assumptions.
  Use during S1 after gathering knowledge, before writing proposal.md + spec deltas.
---

# Assumption Detector

## When to Use
- S1 Step 4a (after gathering knowledge in Step 2, before clarification)
- When user provides vague or incomplete requirements

## Input
- User's feature description
- Knowledge files (if any)
- Existing domain specs (if cross-referencing)

## Process

Scan input for these assumption categories:

1. **Data assumptions** — "users already exist", "products have SKUs", "inventory is tracked"
   - Check: does the entity exist in codebase? Is the relationship defined?

2. **Flow assumptions** — "user will always provide X", "system will respond within Y"
   - Check: what if X is missing? What if timeout?

3. **Permission assumptions** — "only admin can do this", "all CMS users have access"
   - Check: is RBAC defined? Which roles?

4. **Integration assumptions** — "API X is available", "webhook will be called"
   - Check: is the integration documented? What if it fails?

5. **Business rule assumptions** — "price is always positive", "campaign has start/end date"
   - Check: is this validated? What about edge cases?

## Output Format

```markdown
## Assumptions Detected

### [RISKY] — Need validation before S2
- A1: {assumption} — Impact: {what breaks if wrong} — Question: {what to ask}
- A2: ...

### [SAFE] — Documented, low risk
- A3: {assumption} — Source: {where confirmed}
```

## Rules
- Maximum 10 assumptions (prioritize by risk)
- Every [RISKY] must have a concrete question to resolve it
- [SAFE] must cite source (existing spec, codebase, domain knowledge)
