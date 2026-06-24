---
name: verification-loop
description: >
  A comprehensive verification system for Kiro sessions.
  Align với SDLC S4 Build gate và S5 QA gate.
---

# Verification Loop — issues-sum

Verification system gắn vào SDLC gates. Chạy trước khi tạo PR (S4) hoặc khi QA review (S5).

## When to Use

- After completing a feature (S4 Build → before PR)
- Before QA handoff (S4 → S5 transition)
- After refactoring
- Periodic check during long sessions (every 15 min)

## Verification Phases

> Dùng ĐÚNG commands của project (`context/stack.md`) — các lệnh dưới chỉ là placeholder. Coverage threshold lấy từ `.kiro/sdlc.config.json`.

### Phase 1: Build
```bash
<build-command> 2>&1 | tail -20
```
If fail → STOP and fix.

### Phase 2: Type Check
```bash
<type-check-command> 2>&1 | head -30
```

### Phase 3: Lint
```bash
<lint-command> 2>&1 | head -30
```

### Phase 4: Tests + Coverage
```bash
<test-with-coverage-command> 2>&1 | tail -50
# Target: ≥ configured threshold (fallback ≥80% lines, ≥90% diff)
```

### Phase 5: Security Scan
```bash
# Hardcoded secrets (adjust glob to the project's source extension)
grep -rnE "sk_|api_key|password\s*=" --include="*.<ext>" <src-dir> 2>/dev/null | head -10

# Debug logging left in production code
grep -rnE "console\.log|print\(|dump\(" --include="*.<ext>" <src-dir> 2>/dev/null | head -10
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

S4 Gate:   [PASS/FAIL] — CI green + coverage ≥ threshold + no security issues
```
