---
name: verification-loop
description: >
  A comprehensive verification system for Kiro sessions.
  Align với SDLC S4 Build gate và S5 QA gate.
---

# Verification Loop — My Project

Verification system gắn vào SDLC gates. Chạy trước khi tạo PR (S4) hoặc khi QA review (S5).

## When to Use

- After completing a feature (S4 Build → before PR)
- Before QA handoff (S4 → S5 transition)
- After refactoring
- Periodic check during long sessions (every 15 min)

## Verification Phases

### Phase 1: Build
```bash
# Backend
npm run build 2>&1 | tail -20
# Frontend
npm run build 2>&1 | tail -20
```
If fail → STOP and fix.

### Phase 2: Type Check
```bash
npx tsc --noEmit 2>&1 | head -30
```

### Phase 3: Lint
```bash
# Backend
npm run lint 2>&1 | head -30

# Frontend
npm run lint 2>&1 | head -30
```

### Phase 4: Tests + Coverage
```bash
# Backend
npx vitest run --coverage 2>&1 | tail -50
# Target: ≥80% (P1 standard)
```

### Phase 5: Security Scan
```bash
# Hardcoded secrets
grep -rn "sk_\|api_key\|password\s*=" --include="*.ts" src/ 2>/dev/null | head -10

# Console.log in production code
grep -rn "console.log" --include="*.ts" src/ 2>/dev/null | head -10
```

### Phase 6: Diff Review
```bash
git diff --stat
git diff HEAD~1 --name-only
```

Review for: unintended changes, missing error handling, edge cases.

## Output Format

```
VERIFICATION REPORT
==================
Build:     [PASS/FAIL]
Types:     [PASS/FAIL] (X errors)
Lint:      [PASS/FAIL] (X warnings)
Tests:     [PASS/FAIL] (X/Y passed, Z% coverage)
Security:  [PASS/FAIL] (X issues)
Diff:      [X files changed]

Overall:   [READY/NOT READY] for PR

S4 Gate:   [PASS/FAIL] — CI green + coverage ≥80% + no security issues
```
