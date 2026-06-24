---
name: clarification-generator
description: >
  Generate targeted clarification questions from spec gaps. Max 5 questions,
  sequential (1 at a time), each with recommended option. Prioritized by
  impact: scope > data integrity > business rules > UX > technical.
  Use during S1/S2 when requirements have [UNCLEAR] or [MISSING] tags.
---

# Clarification Generator

## When to Use
- S1 after assumption-detector finds [RISKY] items
- S2 when writing ACs and encountering ambiguity
- When user input is vague on critical decisions

## Process

1. Collect all gaps: [RISKY] assumptions + [UNCLEAR] ACs + [MISSING] info
2. Prioritize by impact: scope > data integrity > business rules > UX > technical
3. Generate max 5 questions (budget from analyst R9/R10)
4. For each question: provide 2-3 options with recommended choice

## Question Format

Present ONE question at a time:

```markdown
**Question 1/5**: {topic}

Context: {why this matters — what breaks if wrong}

| Option | Description | Impact |
|--------|-------------|--------|
| A (recommended) | {option} | {consequence} |
| B | {option} | {consequence} |
| C | {option} | {consequence} |

Your choice? (A/B/C or custom answer)
```

## Rules
- EXACTLY 1 question at a time — wait for answer before next
- Never reveal remaining questions
- Stop early if user says "done" or all critical gaps resolved
- After each answer: record in working memory, update relevant AC tag from [UNCLEAR] → [ASSUMED] or [CONFIRMED]
- Make informed guesses for non-critical gaps — document as [ASSUMED]
