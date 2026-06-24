---
name: edge-case-enumerator
description: >
  Systematically enumerate edge cases for a feature by category.
  Minimum 10 edge cases. Categories: input boundary, state transition,
  concurrency, data integrity, permission, integration failure, UI/UX, business rule.
  Use during S1 Step 4 when writing requirement pack.
---

# Edge Case Enumerator

## When to Use
- S1 Step 4 (writing requirement pack — edge cases section)
- When analyst needs to meet R8 minimum 10 edge cases

## Process

For each category, generate edge cases specific to the feature:

1. **Input boundary** — empty, null, max length, special chars, unicode, SQL injection attempts
2. **State transition** — invalid state change, concurrent state change, already deleted
3. **Concurrency** — two users edit same record, race condition on unique constraint
4. **Data integrity** — orphan records, cascade delete, circular reference
5. **Permission** — unauthorized access, expired token, wrong role
6. **Integration failure** — external API timeout, webhook delivery failure, queue full
7. **UI/UX** — pagination edge (page 0, page beyond max), empty list, search no results
8. **Business rule** — boundary values (min/max price, date range overlap, inventory = 0)

## Output Format

```markdown
## Edge Cases

### Input Boundary
- EC-001: {description} → Expected: {behavior}
- EC-002: ...

### State Transition
- EC-003: ...

### Concurrency
- EC-004: ...

[...continue per category]
```

## Rules
- Minimum 10 edge cases total (R8 requirement)
- Each edge case: description + expected behavior
- Prioritize by likelihood × impact
- Reference existing patterns from cross-spec reuse if available
