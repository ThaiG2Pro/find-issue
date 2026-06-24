# S5 QA Report — 1-project-foundation
Date: 2026-06-21
QA Mode: Smart (dev-test-report.md present)

---

## Gate Checklist

- [x] dev-test-report.md exists
- [x] Coverage ≥ 80% (actual: 100%)
- [x] Self-review log present (4 entries)
- [x] All required tasks [x] in tasks.md

---

## Step 4A — Independent Test Execution

QA re-ran full suite independently:

```
30 passed, 0 failed | coverage 100% | matches Dev report exactly
```

Test count matches Dev report (30). ✅

---

## Step 4C — Integration Smoke Test

This is a CLI tool (no HTTP server). Smoke tests run via installed entry point `osspulse`:

| Scenario | Command | Result |
|----------|---------|--------|
| --help exits 0, shows `run` | `osspulse --help` | ✅ exit 0, `run` listed |
| Valid config → stub message | `GITHUB_TOKEN=x osspulse run --config config.example.toml` | ✅ exit 0, "pipeline not yet implemented" |
| Missing token → Error: to stderr | `osspulse run --config config.example.toml` (no token) | ✅ exit 1, `Error: GITHUB_TOKEN is required` to stderr |
| Missing config file → **TRACEBACK** | `osspulse run --config /nonexistent.toml` | ❌ **FileNotFoundError traceback** printed to terminal |

---

## Test Scenarios — Uncovered ACs / Gaps

From qa-analysis Phase 2 gap review:

| AC-ID | Scenario | Expected | Priority | Result |
|-------|----------|----------|----------|--------|
| AC-1-016 | `[watchlist]` present but `repos` key absent (not `repos=[]`) | `ConfigError("watchlist.repos must not be empty")` | Medium | ❌ No test |
| AC-1-031 | Missing config *file* → stderr + no traceback | `Error: cannot read …` + exit 1, no Traceback | High | ❌ Raw traceback |
| AC-1-020 | `lookback_days = false` (bool False) | ConfigError "must be an integer" | Medium | ❌ No test |

---

## Bug List

| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| 1 | FileNotFoundError not caught — raw traceback at CLI | AC-1-031 | High | [AI-DETECTABLE] | S4 |
| 2 | `test_run_missing_token_exits_nonzero` is hollow — passes when `GITHUB_TOKEN` in real env | AC-1-032 | High | [AI-DETECTABLE] | S4 |
| 3 | `test_watched_repo_frozen` uses bare try/except — masks unrelated exceptions | AC-1-011 | Low | [AI-DETECTABLE] | S4 |
| 4 | `repos` key absent from present `[watchlist]` not explicitly tested (AC-1-016 message gap) | AC-1-016 | Low | [EDGE-CASE] | S4 |
| 5 | `lookback_days = false` not tested (bool False path of bool trap) | AC-1-020 | Low | [EDGE-CASE] | S4 |

---

## Bug Detail

### Bug #1: FileNotFoundError not caught — raw traceback at CLI
**AC-ID**: AC-1-031
**Severity**: High
**Classification**: [AI-DETECTABLE]
**RCA Phase**: S4 (code) — `open(config_path, "rb")` only catches `PermissionError`, not `FileNotFoundError`; BR-1-007 boundary broken

**Steps to reproduce**:
1. `uv run osspulse run --config /nonexistent.toml`

**Expected** (BR-1-007): `Error: cannot read /nonexistent.toml: file not found` → stderr, exit 1, no traceback
**Actual**: Rich-formatted `FileNotFoundError` traceback printed to stdout, exit 1
**File**: `src/osspulse/config.py` line 76 — add `except FileNotFoundError` alongside `PermissionError`

---

### Bug #2: `test_run_missing_token_exits_nonzero` is hollow
**AC-ID**: AC-1-032
**Severity**: High
**Classification**: [AI-DETECTABLE]
**RCA Phase**: S4 (code) — cli.py calls `load_config(config)` with no `env` arg, so it reads `os.environ` directly; `runner.invoke(env={})` does NOT override `os.environ`

**Steps to reproduce**:
```python
import os
os.environ["GITHUB_TOKEN"] = "real_token"
result = runner.invoke(app, ["run", "--config", path], env={})
# result.exit_code == 0 — test would FAIL (asserts != 0)
# But test passes when run in CI where GITHUB_TOKEN is absent
```

**Expected**: test reliably fails when GITHUB_TOKEN is present in env
**Actual**: test is environment-dependent — passes in CI (no token), fails locally if token is set
**File**: `tests/test_cli.py` — fix: use `monkeypatch.delenv("GITHUB_TOKEN", raising=False)` (already done for the env dict, but not correctly isolated from real `os.environ`)

**Fix approach**: In `cli.py`, pass `os.environ` explicitly: `load_config(config, dict(os.environ))` — or in the test use `monkeypatch.delenv` without `env={}`.

---

### Bug #3: `test_watched_repo_frozen` hollow assertion
**AC-ID**: AC-1-011
**Severity**: Low
**Classification**: [AI-DETECTABLE]
**RCA Phase**: S4 (code)

`except Exception: pass` swallows all exceptions. The `assert False` line only fires if no exception is raised — which is the wrong behavior check. It would also pass if a random `RuntimeError` were raised. Should use `pytest.raises(FrozenInstanceError)` or `dataclasses.FrozenInstanceError`.

**File**: `tests/test_models.py`

---

### Bug #4: `repos` key absent from present `[watchlist]` — no dedicated test
**AC-ID**: AC-1-016
**Severity**: Low
**Classification**: [EDGE-CASE]
**RCA Phase**: S4 (code)

`[watchlist]` present but `repos` key entirely absent → `watchlist.get("repos")` returns `None` → `if not repos_raw` → raises `ConfigError("watchlist.repos must not be empty")`. This message is misleading for the "key absent" case (AC-1-016 expects "must not be empty" for *empty*, but the spec's distinct case is the missing key). Not a code bug — the message fires correctly — but no test asserts this distinct path.

---

### Bug #5: `lookback_days = false` not tested
**AC-ID**: AC-1-020
**Severity**: Low
**Classification**: [EDGE-CASE]
**RCA Phase**: S4 (code)

`false` in TOML parses to Python `False` (a bool). `type(False) is not int` → raises correctly. But only `true` (True) is tested. `false` is the symmetric case and should be covered.

---

## AC Coverage Summary

- Total ACs: 33
- Covered by Dev (unit tests + checkpoints): 33
- Independently verified by QA (code review + smoke): 33
- QA-identified gaps not covered by Dev tests: 3 (AC-1-031 real behavior, AC-1-016 edge path, AC-1-020 false branch)
- Hollow tests found: 2 (Bug #2 critical, Bug #3 low)

---

## Security Audit Results (mandatory)

| Check | Result |
|-------|--------|
| No hardcoded secrets in source | ✅ |
| GITHUB_TOKEN never echoed in error messages | ✅ |
| `.env` in `.gitignore` | ✅ |
| TOML parse wrapped — no raw parse errors to user | ✅ |
| `FileNotFoundError` leaks traceback (path info) | ❌ Bug #1 |
| No SQL / HTTP / PII logging | ✅ N/A |
| Input validation present on all config fields | ✅ |

---

## CMS UI Visual QA

N/A — CLI tool, no Figma URL.

---

## Decision: **NO-GO**

2 High bugs open (Bug #1 + Bug #2). Both are [AI-DETECTABLE] S4 fixes.

### Blockers

1. **Bug #1 — FileNotFoundError traceback (High)**: `config.py` must catch `FileNotFoundError` alongside `PermissionError` and convert to `ConfigError`. 1-line fix. BR-1-007 violated.
2. **Bug #2 — Hollow CLI token test (High)**: `test_run_missing_token_exits_nonzero` is environment-dependent. Test passes in CI only because `GITHUB_TOKEN` happens to be absent. Must be fixed to be deterministic. AC-1-032 has no reliable coverage.

Recommended action: `Developer → /s4-fix 1 project-foundation`

Fix approach:
- Bug #1: in `config.py`, add `except FileNotFoundError` to the `open()` try block → `raise ConfigError(f"cannot read {config_path}: file not found")`
- Bug #2: in `cli.py`, change `load_config(config)` → `load_config(config, dict(os.environ))` so tests can inject env cleanly; update test to use `monkeypatch.delenv` only (drop `env={}`)
- Bug #3 (Low, non-blocking): replace `try/except Exception` with `pytest.raises(dataclasses.FrozenInstanceError)`
- Bugs #4, #5 (Low): add 2 test cases

---

## S5 Retest — 2026-06-21

### Bug Fix Verification

| Bug # | Fix verified | Method |
|-------|-------------|--------|
| BUG-1 | ✅ `osspulse run --config /nonexistent.toml` → `Error: cannot read … file not found`, exit 1, no traceback | Smoke test |
| BUG-2 | ✅ `test_run_missing_token_exits_nonzero` passes even when `GITHUB_TOKEN` set in real env | Run with `GITHUB_TOKEN=ghp_local` |
| BUG-3 | ✅ `pytest.raises(dataclasses.FrozenInstanceError)` present in test_models.py | Code review |
| BUG-4 | ✅ `test_repos_key_absent` asserts `ConfigError("watchlist.repos must not be empty")` | Code review |
| BUG-5 | ✅ `test_lookback_days_false_rejected` asserts `ConfigError("lookback_days must be an integer")` | Code review |

### Regression Check

33 passed, 0 failed — no regressions introduced.
Coverage: 98% (lines 70-72 = `if env is None` safety fallback, intentionally kept).

### Smoke Tests

| Scenario | Result |
|----------|--------|
| Missing file → `Error: cannot read … file not found`, exit 1 | ✅ |
| Valid config → `pipeline not yet implemented`, exit 0 | ✅ |
| Missing token → `Error: GITHUB_TOKEN is required`, exit 1 | ✅ |

### Decision: **GO** ✅

0 Critical/High bugs open. All ACs verified. Regression clean.
