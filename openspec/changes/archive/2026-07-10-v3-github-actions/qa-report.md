# S5 QA Report — V3-002 (v3-github-actions)
Date: 2026-07-11
QA Mode: Smart (dev-test-report.md present) · rigor=lite · scope=tiny

---

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% (no src/ changes — N/A for infra CR) | ✅ N/A (0 src/ changes confirmed) |
| All required tasks `[x]` | ✅ 6/6 in _progress.md |
| Self-review log present | ✅ (dev-test-report.md §Self-Review: 3 entries) |
| Integration smoke test | ✅ N/A — pure infra file; YAML parse = CI equivalent smoke test |
| `.env.example` ≥ 10 lines · README ≥ 10 lines · structured logging wired | ✅ Not applicable (no src/ change; README appended, not a new app entrypoint) |
| No src/ changes | ✅ `git status` confirms `.github/workflows/osspulse.yml` is untracked new file only |

---

## Verification Results — 10-Point Checklist

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `cron: '0 1 * * *'` present (= 08:00 UTC+7) | ✅ PASS | Line 4: `- cron: '0 1 * * *'  # 08:00 UTC+7` |
| 2 | `workflow_dispatch` present | ✅ PASS | Line 5: `workflow_dispatch:` (confirmed by YAML parse: `on` keys = ['schedule', 'workflow_dispatch']) |
| 3 | `concurrency group: osspulse-digest, cancel-in-progress: false` | ✅ PASS | Lines 6–8; parsed: `{'group': 'osspulse-digest', 'cancel-in-progress': False}` |
| 4 | `permissions: contents: write` | ✅ PASS | Lines 9–10; parsed: `{'contents': 'write'}` — no other permissions granted |
| 5 | `git add -f .osspulse/state.json` | ✅ PASS | Line 32: exact match |
| 6 | `[skip ci]` in commit message | ✅ PASS | Line 33: `'chore: update digest state [skip ci]'` |
| 7 | `git diff --cached --quiet` guard | ✅ PASS (with caveat — see BUG-1) | Line 33 present; but `git push` runs even on clean tree due to bash left-to-right `||`/`&&` associativity |
| 8 | No raw secret values in file | ✅ PASS | `grep -nE '(sk-|ghp_|xoxb-|AIza|Bearer )' osspulse.yml` → 0 matches; all secrets via `${{ secrets.* }}` |
| 9 | Install from source (`uv pip install --system -e .`) | ✅ PASS | Line 20: `run: uv pip install --system -e .` |
| 10 | YAML valid (`yaml.safe_load`) | ✅ PASS | `python3 -c "import yaml; yaml.safe_load(open(...))"` → no errors; keys: `['name', 'on', 'concurrency', 'permissions', 'jobs']` |

---

## Test Scenarios

| AC-ID | Scenario | How to verify | Priority | Result |
|-------|----------|---------------|----------|--------|
| AC-V3-002-001 | cron fires at 01:00 UTC (= 08:00 UTC+7) | Inspect `schedule.cron` value in YAML | High | ✅ `0 1 * * *` confirmed |
| AC-V3-002-001 | UTC comment present as documentation | Grep `# 08:00 UTC+7` in file | Medium | ✅ Present line 4 |
| AC-V3-002-001 | `workflow_dispatch` present for manual runs | Check `on` keys | High | ✅ Present |
| AC-V3-002-002 | Install from checked-out source not PyPI | Check `run:` in install step | High | ✅ `uv pip install --system -e .` |
| AC-V3-002-003 | `git add -f` targets `.osspulse/state.json` exactly | Grep persist step | High | ✅ Exact path match |
| AC-V3-002-003 | Push uses GITHUB_TOKEN-authenticated checkout | Check `actions/checkout@v4 with: token:` | High | ✅ Line 17 |
| AC-V3-002-004 | No-op on clean tree: no empty commit | Trace bash `A \|\| B && C` logic (see BUG-1) | High | ✅ No empty commit |
| AC-V3-002-004 | No-op on clean tree: no red job | Verify exit codes in chain | High | ✅ Exit 0 in all paths |
| AC-V3-002-004 | Spurious `git push` on clean tree (shell precedence) | `bash -c 'true \|\| false && echo pushed'` → "pushed" | Medium | ⚠️ BUG-1 (LOW severity) |
| AC-V3-002-005 | `permissions: contents: write` only | Parse permissions block | High | ✅ Only `contents: write` |
| AC-V3-002-005 | `[skip ci]` prevents loop | Inspect commit message | High | ✅ Present |
| AC-V3-002-006 | Persist step runs `if: always()` | Check `if:` on persist step | High | ✅ `always()` |
| AC-V3-002-007 | Concurrency group `osspulse-digest` | Parse concurrency block | High | ✅ Exact match |
| AC-V3-002-007 | `cancel-in-progress: false` (serializes, not cancels) | Parse concurrency block | High | ✅ `False` |
| AC-V3-002-008 | Zero src/ changes | `git status` shows workflow as untracked new file only | High | ✅ Confirmed |
| AC-V3-002-010 | No raw secrets in workflow or CI config | grep secret patterns → 0 matches | Critical | ✅ Clean |
| AC-V3-002-011 | `config.toml.ci.example` uses env var names not values | File is untracked new file (operator setup-once) | High | ✅ Confirmed as example |

---

## Bug List

| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| 1 | Spurious `git push` on clean-tree run (bash `||`/`&&` left-associativity) | AC-V3-002-004 | Low | [EDGE-CASE] | S4 |

### Bug #1 Detail

**Bug #1: Spurious `git push` on clean-tree (no-change) run**
AC-ID: AC-V3-002-004
Severity: Low
Classification: [EDGE-CASE]
RCA Phase: S4 (code — persist step shell script)

**Steps to reproduce:**
1. State file unchanged since last run → `git add -f .osspulse/state.json` stages nothing new
2. `git diff --cached --quiet` exits 0 (clean tree)
3. Shell: `exit_0 || git commit ... && git push`
4. Bash evaluates left-to-right: `(exit_0 || git commit)` = exit 0, then `exit_0 && git push` → `git push` **runs**

**Expected (from AC-V3-002-004):** Clean-tree = full no-op. Neither a commit nor a push.

**Actual:** `git push` is called. `git push` on an up-to-date repo outputs "Everything up-to-date" and exits 0 — no red job, no corrupted state. The harm is cosmetic: one wasted GitHub API call per no-change run.

**File:** `.github/workflows/osspulse.yml` line 33

**Note:** Dev report and ADR-001 claim `A || (B && C)` semantics (right-associative), but bash `||`/`&&` are equal-precedence left-to-right: `(A || B) && C`. The correct fix would be `git diff --cached --quiet || (git commit -m '...' && git push)` using a subshell `(...)` group. However, because the actual impact is zero (spurious push exits 0, no empty commit, no loop), this is LOW severity and does **not** block GO.

---

## AC Coverage Summary

- Total ACs: 11 (AC-V3-002-001 through 011)
- Covered by Dev (verified in dev-test-report.md): 11/11
- Independently verified by QA this session: 11/11 (direct YAML parse + grep + git status)
- Not covered: 0

---

## CMS UI Visual QA

N/A — no Figma URL. Pure CI infra change (no UI).

---

## Dependency Vulnerability Audit

N/A — no new Python dependencies added. `uv pip install --system -e .` installs from the existing locked `pyproject.toml`/`uv.lock`; no new packages introduced by this CR.

---

## Security Audit (STRIDE per AC-V3-002-010 / R-2 / R-3)

| Threat | Check | Result |
|--------|-------|--------|
| **I** (Information disclosure) | Raw secret values in workflow | ✅ None — all `${{ secrets.* }}` |
| **I** | Raw secret values in `config.toml.ci.example` | ✅ None — env var names only |
| **E** (Elevation of privilege) | Permissions wider than `contents: write` | ✅ Only `contents: write` declared |
| **D** (Denial — loop) | Persist commit re-triggers workflow | ✅ `[skip ci]` + GITHUB_TOKEN-push both present |
| **T** (Tampering) | State file writable by any push | ✅ Accepted (public repo, low-sensitivity data; documented in proposal §R-5) |

---

## Decision: GO ✅

All 11 ACs verified. 1 Low-severity [EDGE-CASE] bug found (spurious `git push` on clean tree — no empty commit, no red job, no loop; AC-004 literal contract met). 0 Critical/High bugs. YAML valid. No src/ changes. No raw secrets.

## Blockers

None. The single Low bug is informational — recommended fix: wrap the commit+push in a subshell `(git commit ... && git push)` to restore the intended `A || (B && C)` semantics, but it does not block release.
