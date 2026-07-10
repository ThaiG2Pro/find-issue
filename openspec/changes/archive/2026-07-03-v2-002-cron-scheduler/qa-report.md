# S5 QA Report — V2-002 (v2-002-cron-scheduler)
Date: 2026-07-03 (re-verify: 2026-07-03T18:00+07:00)
QA Mode: Smart (dev-test-report.md present; 24/24 ACs covered by Dev)
Rigor: lite

> **Re-verify note**: Developer fixed B-001, B-002, B-003 (all Low). QA re-ran full suite
> after fixes. All 3 bugs confirmed RESOLVED. See §Bug List for updated status.

---

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% (threshold) | ✅ 96.22% (QA independent run confirmed) |
| All required tasks `[x]` | ✅ 19/19 tasks checked |
| Self-review log present | ✅ 3 items (HIGH/MEDIUM/LOW) in dev-test-report.md |
| `.env.example` present | ✅ (pre-existing, not modified by this change) |
| `README.md` ≥ 10 lines + §Scheduling added | ✅ §Scheduling added (lines 173–235+) |
| Structured logging wired | ✅ `logger.warning(...)` in `cli.run` for LockHeldError arm |
| Integration smoke test | ⚠️ PARTIAL — see Step C below |
| Dependency audit | ✅ 0 HIGH/CRITICAL (uv audit clean) |
| Ruff lint + format | ✅ 0 errors, 61 files formatted |

**Gate result: PASS** (smoke test limitation is documented and classified — does not block GO at lite rigor).

---

## QA-Independent Test Run

```
uv run pytest --cov=src/osspulse --cov-report=term-missing

# Initial run (S5 first pass — pre bug-fix):
# 423 passed, 0 failed, 96.22%

# Re-verify run (post bug-fix — 2026-07-03T18:00+07:00):
429 passed, 0 failed, 3 warnings (DeprecationWarning: is_flag — cosmetic, known)
Coverage: 96.47%  (gate ≥ 80% ✅)
```

Post-fix run: +6 tests (4 for B-003 `_handle_broken_pipe` branches + 2 for B-002 `NO_COLOR` wiring).
Coverage improved +0.25 pp — previously-uncovered cli.py:85-87 (BrokenPipeError handler body) now covered.
All targeted fix tests pass independently (7/7 via `-v` targeted run).

---

## Test Scenarios

### qa-analysis Phase 2 — Spec-TC Gap Map

All 24 ACs have Dev test coverage. Gap analysis result:

| AC | Dev Coverage | Gap Type | QA Action |
|----|-------------|----------|-----------|
| AC-V2-002-001 | test_cli_schedule + test_schedule_cron | SHALLOW_TC (see B1-H1a) | Code review + verify |
| AC-V2-002-002 | test_cli_schedule + test_schedule_cron | OK | Verify |
| AC-V2-002-003 | parametrized preset tests | OK | Verify |
| AC-V2-002-004 | test_schedule_output_contains_absolute_binary/config | OK | Verify |
| AC-V2-002-005 | test_schedule_no_secret + secrets tests | OK — real-env integration test present | Verify |
| AC-V2-002-006 | test_validate_* (10 cases) | OK | Verify |
| AC-V2-002-007 | test_schedule_mutual_exclusion | OK | Verify |
| AC-V2-002-008 | test_schedule_default_prints_daily_line | OK | Verify |
| AC-V2-002-009 | test_schedule_install_writes_to_crontab | OK | Verify |
| AC-V2-002-010 | test_schedule_install_idempotent + test_upsert_block_reinstall | OK | Verify |
| AC-V2-002-011 | test_*_preserves_unrelated_lines | OK | Verify |
| AC-V2-002-012 | test_schedule_uninstall_no_block_is_noop | OK | Verify |
| AC-V2-002-013 | test_crontab_client_raises_schedule_error_when_binary_missing | OK | Verify |
| AC-V2-002-014 | test_schedule_github_actions_prints_yaml | OK | Verify |
| AC-V2-002-015 | test_*_contains_secrets_refs + no_secret tests | OK — real-env integration test present | Verify |
| AC-V2-002-016 | test_*_unwritable_parent_exits_1 + no_partial | OK | Verify |
| AC-V2-002-017 | test_*_contains_utc_comment | OK | Verify |
| AC-V2-002-018 | test_run_completes_without_tty + static source check | SHALLOW_TC (see B1-H1b) | Code review |
| AC-V2-002-019 | test_run_exits_{0,1}_on_* (7 cases) | OK | Verify |
| AC-V2-002-020 | test_run_no_ansi_in_output + static isatty check | SHALLOW_TC (see B1-H1c) | Code review |
| AC-V2-002-021 | test_run_acquires_lock_before_pipeline | OK — ordering verified | Verify |
| AC-V2-002-022 | test_run_lock_held_exits_0_not_1 + caplog warning | OK — both exit code AND log asserted | Verify |
| AC-V2-002-023 | test_lock_auto_releases_on_fd_close (real fcntl) | OK — real fd, no mock | Verify |
| AC-V2-002-024 | test_schedule_output_contains_absolute_binary_path + resolve_binary tests | OK | Verify |

**Scenario table (QA-generated, focused on gaps and high-risk areas):**

| AC-ID | Scenario | How to verify | Priority | Result |
|-------|----------|---------------|----------|--------|
| AC-V2-002-005 | GITHUB_TOKEN in env does not appear in generated crontab line | monkeypatch + assert_no_secret | Critical | ✅ PASS (test_generate_line_does_not_leak_env_token + CLI test) |
| AC-V2-002-015 | LLM_API_KEY in env does not appear in Actions workflow YAML | monkeypatch + assert_no_secret | Critical | ✅ PASS (test_generate_workflow_does_not_leak_llm_key) |
| AC-V2-002-015 | GITHUB_TOKEN in env does not appear in Actions workflow YAML | monkeypatch + assert_no_secret | Critical | ✅ PASS (test_generate_workflow_does_not_leak_env_token) |
| AC-V2-002-009 | install → reinstall → uninstall round-trip is byte-identical | 8 parametrized cases + double-reinstall | High | ✅ PASS (test_round_trip_byte_identical × 8 + test_round_trip_double_reinstall) |
| AC-V2-002-010 | Re-install replaces block in place, exactly one block | upsert twice, count markers | High | ✅ PASS |
| AC-V2-002-011 | Unrelated crontab lines preserved byte-for-byte | install + inspect prefix/suffix | High | ✅ PASS |
| AC-V2-002-012 | Uninstall with no block is no-op exit 0, no write | fake client write_calls == [] | High | ✅ PASS |
| AC-V2-002-021 | Lock acquired BEFORE pipeline, released AFTER | call_order assertion lock_enter→pipeline→lock_exit | High | ✅ PASS |
| AC-V2-002-022 | Lock held → exit 0, pipeline NOT invoked | mock LockHeldError, pipeline_calls == [] | Critical | ✅ PASS |
| AC-V2-002-022 | Lock held → WARN log emitted (not Error:) | caplog assertion + "Error:" not in output | High | ✅ PASS |
| AC-V2-002-023 | Crash (fd close without LOCK_UN) → next run acquires lock | real fcntl, os.close without LOCK_UN | High | ✅ PASS |
| AC-V2-002-018 | cli.run source has no typer.prompt / click.prompt / input() | static source inspection | High | ✅ PASS |
| AC-V2-002-020 | No ANSI escape in non-TTY stdout+stderr | regex _ANSI_RE scan on CliRunner output | High | ✅ PASS |
| AC-V2-002-006 | Invalid cron expr (99 * * * *) → Error: stderr, exit 1, no write | CLI invoke, exit_code==1, "Error:" in stderr, write_calls==[] | High | ✅ PASS |
| AC-V2-002-007 | --cron + --preset → mutually exclusive error, exit 1 | CLI invoke | High | ✅ PASS |
| AC-V2-002-013 | crontab binary missing → Error: exit 1, no traceback | monkeypatch shutil.which → None | High | ✅ PASS |
| AC-V2-002-016 | --output with non-existent parent → Error: exit 1, no partial file | invoke with `doesnotexist/osspulse.yml` | High | ✅ PASS |
| AC-V2-002-016 | --output with chmod 555 parent → no partial file left | chmod 555 + check file not exists | High | ✅ PASS |
| AC-V2-002-017 | Generated workflow has UTC comment near schedule block | index distance check | Medium | ✅ PASS |
| AC-V2-002-024 | resolve_binary returns shutil.which result when found | mock which → assert result | Medium | ✅ PASS |
| AC-V2-002-024 | resolve_binary falls back to abspath(sys.argv[0]) when which=None | mock which → None, mock argv | Medium | ✅ PASS |
| AC-V2-002-004 | resolve_binary always returns absolute path (isabs check) | assert os.path.isabs(result) | Medium | ✅ PASS |
| SECURITY | LockHeldError is NOT a subclass of ScheduleError (exit-code isolation) | issubclass assertion | Critical | ✅ PASS |
| SECURITY | assert_no_secret raises on empty string in values (no vacuous match) | assert_no_secret("any text", [""]) | Medium | ✅ PASS |

---

## Step 4A — Independent Test Run

**Command**: `uv run pytest --cov=src/osspulse --cov-report=term-missing`
**Result**: 423 passed / 0 failed ✅
**Coverage**: 96.22% total ✅

Uncovered lines confirmed as intentional (all documented in dev-test-report.md):
- `cli.py` 85-87: `BrokenPipeError` handler — no real SIGPIPE via CliRunner (documented EDGE-CASE, per scheduler-cli-7 memory)
- `cli.py` 261-264: `os.fsync` in `_write_output_atomic` — filesystem-level call, reuses proven state-store-3 pattern
- `schedule/cron.py` 58, 61, 66-68, 82: `_valid_field` step/range sub-branches and `_valid_range` short-circuit — defensive validator internals; primary rejection paths covered by 10+ test cases
- `schedule/crontab.py` 157-181: `CrontabClient.read()` / `write()` real subprocess calls — intentionally behind mock seam (ADR-008); real invocation would mutate operator crontab

---

## Step 4B — Code Review + Security Audit

### RISK-001 — Secret leakage (AC-V2-002-005 / AC-V2-002-015)

**Findings**: PASS

- `schedule/cron.py::generate_line` — does NOT read `os.environ`; only uses `cron_expr`, `binary`, `config_path` (all non-secret). Produces `"{expr} {binary} run --config {abs_config}"`. No mechanism to inline a secret. `assert_no_secret` called by `cli._schedule_impl` after `collect_secret_values(os.environ)` — confirmed in `cli.py` lines 218 and 228.
- `schedule/workflow.py::generate_workflow` — uses `_WORKFLOW_TEMPLATE.format(cron_expr=...)`. Template hardcodes `${{ secrets.GITHUB_TOKEN }}` and `${{ secrets.LLM_API_KEY }}` — Python's `.format()` with named placeholder `{cron_expr}` only; no secret value is injected. `assert_no_secret` called after generation in `cli.py` line 222.
- `schedule/secrets.py::collect_secret_values` — reads `GITHUB_TOKEN` + 4 LLM key vars; strips whitespace; skips empty values. Confirmed empty-string guard prevents vacuous match.
- `schedule/secrets.py::assert_no_secret` — raises `ScheduleError` if any non-empty secret is a substring. Called on the full upserted block in `--install` path (line 229 of cli.py) — the hardest surface. ✅

**Conclusion**: RISK-001 mitigations are defense-in-depth and correctly wired. No secret leakage path found.

### RISK-002 — Crontab tampering (AC-V2-002-009..012)

**Findings**: PASS

- `crontab.py::upsert_block` — pure string function. Correctly handles: empty original, non-empty with/without trailing `\n`, existing block (replace in place). The `prefix = "\n" if current else ""` line ensures the separator is added for non-empty originals. Block end tracking (`block_end_line_end += 1` for trailing `\n`) is correct.
- `crontab.py::remove_block` — symmetric: `strip_start = start_idx - 1 if start_idx > 0 else start_idx` strips the separator `\n` added by upsert. The 8 parametrized round-trip tests cover the critical cases: empty, `"\n"`, content with/without trailing newline, multi-line.
- **Potential shallow gap** (SHALLOW_TC, not a code bug): `test_upsert_block_no_double_newline_when_existing_ends_with_newline` has an assertion `assert f"\n{BLOCK_START}" in result` which is an existence check (H1 pattern). The comment explains the double-`\n` is intentional. Code review confirms the round-trip test covers the actual correctness criterion. Classified Low / SHALLOW_TC — the round-trip parametrized tests are the real coverage here.
- `CrontabClient.write` called only when `new != current` in uninstall path (`cli._schedule_impl` line 208) — no spurious writes. ✅

### RISK-003 / RISK-004 — Lock correctness (AC-V2-002-021..023)

**Findings**: PASS

- `lock.py::single_instance_lock` — correctly uses `fcntl.LOCK_EX | fcntl.LOCK_NB`. `LOCK_NB` is essential and present. `BlockingIOError` → `LockHeldError` with message "another osspulse run is already active; skipping this overlapping run".
- `LockHeldError` is a plain `Exception`, NOT a subclass of `ScheduleError` — confirmed by `test_lock_held_error_is_not_schedule_error`. This is critical: if it were a `ScheduleError` subclass, it would be caught by the exit-1 arm instead of the exit-0 arm. ✅
- `cli.py::run` — `LockHeldError` handler is the **first** `except` clause after the `try:` block (lines 72-75), before `BrokenPipeError`, `AuthError`, `StateError`, `DeliveryError`, `ConfigError`. Order is correct per ADR-005. ✅
- `finally` block in `lock.py` — `fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)` — releases even on exception. `test_run_releases_lock_even_on_fatal_error` verifies this. ✅
- Lock file mode `0o600` — confirmed in `test_lock_file_mode_600`. ✅
- Crash auto-release — `test_lock_released_after_fd_close` (in both `test_lock.py` and `test_cli_run_cronsafe.py`) exercises real `os.close(fd)` without `LOCK_UN`; next `single_instance_lock` succeeds. ✅

### AC-V2-002-018..020 — Cron-safe run

**Findings**: PASS

- `test_run_does_not_call_interactive_prompts` — static `inspect.getsource` check: no `typer.prompt`, `click.prompt`, or `input(` in `cli.run` source. ✅
- `test_isatty_guard_present_in_run_source` — `isatty` is present in `cli.run` source (line `_is_tty = sys.stdout.isatty()`). The `# noqa: F841 — kept for documentation` comment is honest about the current usage; the flag documents the ADR-010 intent. This is not a bug — the pipeline/logging already emit no ANSI (reaffirmation design). ✅
- ANSI regex scan on CliRunner non-TTY output — no ANSI sequences found. ✅
- Exit code contract: 0 for success + no-new-items, 1 for ConfigError/AuthError/StateError/DeliveryError — all covered by 7 test cases. ✅

### Security Audit Checklist (OWASP-relevant for CLI+file-write surface)

| Check | Result |
|-------|--------|
| No hardcoded secrets in source | ✅ All secrets from env only |
| Subprocess calls use list args (no shell=True) | ✅ `["crontab", "-l"]` / `["crontab", "-"]` — no shell injection |
| No `shell=True` in any subprocess.run | ✅ confirmed (`# noqa: S603/S607` suppress bandit, not shell=True) |
| `tempfile.mkstemp` used for atomic write (no predictable name) | ✅ |
| Lock file created with `0o600` (not world-readable) | ✅ |
| No PII logged | ✅ logger.warning message: "osspulse run skipped: another run is already active (lock held)" — no tokens, paths, or user data |
| Error messages use `Error: {e}` without raw exception chains | ✅ `typer.echo(f"Error: {e}", err=True)` — no traceback exposed |
| `assert_no_secret` raises before any write on secret leak | ✅ |
| `crontab` binary checked via `shutil.which` before subprocess | ✅ |
| No `sudo` or elevated privilege in crontab operations | ✅ confirmed — only `crontab` (user-owned) |

---

## Step 4B1 — Test Quality Review (Hollow TC Detection)

Reviewed all 7 new test files (138 new tests total).

### Hollow TC findings:

**[H1a] SHALLOW_TC — `test_schedule_default_no_write`** (test_cli_schedule.py)
- AC-V2-002-001. Asserts `fake.write_calls == []` (existence: no write). Does not assert what was printed.
- Mitigation: `test_schedule_default_prints_daily_line` and `test_schedule_default_contains_osspulse_run` in the same file cover the output content. Together they adequately cover the AC.
- Severity: **Low** — complementary tests fill the gap. Not a standalone hollow test.

**[H1b] SHALLOW_TC — `test_run_completes_without_tty`** (test_cli_run_cronsafe.py)
- AC-V2-002-018. Asserts `exit_code == 0` only. Does not verify that no TTY-dependent behavior fired.
- Mitigation: `test_run_does_not_call_interactive_prompts` (static source check) and `test_run_no_ansi_in_output_when_not_tty` complement this. CliRunner is inherently non-TTY. Adequate together.
- Severity: **Low** — complementary tests fill the gap.

**[H1c] SHALLOW_TC — `test_isatty_guard_present_in_run_source`** (test_cli_run_cronsafe.py)
- AC-V2-002-020. Asserts `"isatty" in src` — existence only. Does not verify the guard actually suppresses color.
- Mitigation: `test_run_no_ansi_in_output_when_not_tty` verifies the behavioral outcome (no ANSI in CliRunner output). Together adequate.
- Severity: **Low** — behavior test covers what the static test cannot.

**[H1d] SHALLOW_TC — `test_upsert_block_no_double_newline_when_existing_ends_with_newline`** (test_schedule_crontab.py)
- The test name says "no double newline" but the assertion `assert f"\n{BLOCK_START}" in result` actually confirms the separator IS added (the comment explains this is intentional by design). Test name is misleading.
- Code review confirms the actual behavior (double `\n` when appending to content ending with `\n`) is correct for the round-trip guarantee.
- Classification: **[SPEC-UNCLEAR]** — test name vs behavior mismatch; not a code bug.
- Severity: **Low / no-block** — round-trip parametrized tests validate actual correctness.

**[H1e] Note — `test_run_exits_0_on_no_new_items`** (test_cli_run_cronsafe.py)
- Patches `run_pipeline` to return `None`. Comments explain both success and no-new-items return `None`. This is correct and mirrors the actual pipeline contract. Not hollow — the test accurately models the real behavior.
- No bug.

**Overall hollow TC assessment**: 3 low-severity shallow tests (H1a/b/c), all complemented by behavioral tests in the same file. 1 misleading test name (H1d, SPEC-UNCLEAR). No blocking findings.

---

## Bug List

| # | Title | AC-ID | Severity | Classification | RCA Phase | Status |
|---|-------|-------|----------|----------------|-----------|--------|
| B-001 | Misleading test name: `test_upsert_block_no_double_newline_when_existing_ends_with_newline` contradicts actual behavior | AC-V2-002-010 | Low | [SPEC-UNCLEAR] | S4 | ✅ RESOLVED |
| B-002 | `_is_tty` guard is documentation-only; no-color enforcement not wired to any output path | AC-V2-002-020 | Low | [LOGIC-BUG] | S4 | ✅ RESOLVED |
| B-003 | BrokenPipeError handler (cli.py:85-87) not exercisable via CliRunner — 0% coverage on 3 lines | AC-V2-002-018 (related) | Low | [EDGE-CASE] | S4 | ✅ RESOLVED |

### Bug Detail — B-001 ✅ RESOLVED
```
Bug #1: Misleading test name — no_double_newline contradicts double-\n design
AC-ID: AC-V2-002-010
Severity: Low
Classification: [SPEC-UNCLEAR]
RCA Phase: S4 (test authoring)
Status: RESOLVED

Fix: Renamed to test_upsert_block_adds_newline_separator_when_existing_ends_with_newline
Verification: old name absent (grep confirms), new test passes ✅
```

### Bug Detail — B-002 ✅ RESOLVED
```
Bug #2: _is_tty guard in cli.run was documentation-only — no-color not actively enforced
AC-ID: AC-V2-002-020
Severity: Low
Classification: [LOGIC-BUG]
RCA Phase: S4 (implementation)
Status: RESOLVED

Fix: cli.py line 86-87 — if not _is_tty: os.environ["NO_COLOR"] = "1"
  _is_tty now wired to actual enforcement before pipeline invocation.
  F841 noqa suppression removed (variable is no longer unused).
New tests:
  - test_run_sets_no_color_env_when_not_tty: verifies NO_COLOR="1" set when non-TTY ✅
  - test_run_no_color_not_set_when_tty: verifies NO_COLOR NOT forced when TTY ✅
Verification: both tests pass; cli.py line 86-87 now covered ✅
```

### Bug Detail — B-003 ✅ RESOLVED
```
Bug #3: BrokenPipeError handler — 0% coverage on 3 lines; not testable via CliRunner
AC-ID: AC-V2-002-018 (adjacent)
Severity: Low
Classification: [EDGE-CASE]
RCA Phase: S4 (inherent limitation)
Status: RESOLVED

Fix: Extracted _handle_broken_pipe() helper with two guards:
  1. if not hasattr(sys.stdout, "fileno"): return  — no-op in CliRunner (BytesIO)
  2. except io.UnsupportedOperation: pass  — catches BytesIO.fileno() in edge cases
  BrokenPipeError handler in run() now calls _handle_broken_pipe().
New tests (all 4 pass ✅):
  - test_handle_broken_pipe_with_real_fd: real fd redirect works without exception
  - test_handle_broken_pipe_without_fileno: hasattr guard fires, no-op, no raise
  - test_handle_broken_pipe_unsupported_operation: UnsupportedOperation silenced
  - test_run_broken_pipe_exits_zero: BrokenPipeError → exit 0 via CliRunner
Previously uncovered cli.py:85-87 now covered. Coverage: 96.22% → 96.47% ✅
Note: Live pipe smoke test (osspulse run | head -1) remains on S6 operator checklist.
```

---

## AC Coverage Summary

- Total ACs: 24
- Covered by Dev (unit + integration tests): 24/24 (100%)
- Independently verified by QA (code review + test review): 24/24
- Not covered: 0
- ACs with shallow TCs (complementary tests fill gap): AC-V2-002-001, AC-V2-002-018, AC-V2-002-020 — all Low, all adequately covered by companion tests

**High-risk ACs verification status:**
- AC-V2-002-005 (no secret in crontab): ✅ — both by-construction (generator never reads env) AND runtime backstop (`assert_no_secret`) AND integration tests with real monkeypatched token
- AC-V2-002-015 (no secret in workflow): ✅ — same two-layer defense; hardest surface confirmed clean
- AC-V2-002-009/010/011/012 (managed-block idempotency): ✅ — 8 parametrized round-trip tests + 24 crontab unit tests; byte-identity confirmed
- AC-V2-002-021/022/023 (single-instance lock): ✅ — real-fd kernel semantics tested (no mock of flock); exit-0 contract and WARN log both asserted
- AC-V2-002-018/019/020 (cron-safe run): ✅ — static source check + behavioral ANSI scan + exit-code table coverage

---

## Step 4C — Integration Smoke Test

**Status**: ⚠️ PARTIAL — environment limitation

The CI/test environment does not have a live GitHub token, Redis instance, or LLM provider configured. A full `osspulse run` would exit 1 on `ConfigError` / `AuthError` before reaching the pipeline.

**What was verified** (without real external services):
- `uv run pytest` completes cleanly (423/0) — confirms all in-process paths work
- Typer CLI registration: `uv run osspulse --help` and `uv run osspulse schedule --help` available (verified via CliRunner in test_cli_schedule.py)
- `schedule` command print-only mode: confirmed via CliRunner (no real crontab touched)
- Lock semantics: real `fcntl.flock` exercised in tmp dir — kernel behavior confirmed

**What could not be verified** (requires live environment):
- Real `crontab -l` / `crontab -` subprocess round-trip
- `osspulse run` end-to-end with real GitHub/LLM
- BrokenPipeError via `osspulse run | head -1` (live pipe)

**Classification**: [EDGE-CASE] Medium — environment constraint, not a code defect.
**Recommendation**: Add to S6 operator checklist: (1) `osspulse schedule --install` + verify `crontab -l` shows managed block, (2) `osspulse schedule --uninstall` + verify block removed, (3) `osspulse run | head -1` exits 0.

---

## CMS UI Visual QA

N/A — CLI tool, no Figma URL, no HTTP/UI surface.

---

## Dependency Vulnerability Audit

```
uv audit (experimental)
Resolved 64 packages in 1ms
Found no known vulnerabilities and no adverse project statuses in 63 packages
```

Result: **0 HIGH / 0 CRITICAL / 0 MODERATE** ✅ Clean. Does not block GO.

---

## Decision: ✅ GO

**Reasoning**: 24/24 ACs independently verified. 0 Critical/High bugs. **All 3 Low bugs RESOLVED** (B-001 test rename, B-002 `_is_tty` wired to `NO_COLOR`, B-003 `_handle_broken_pipe()` extracted with guards + 4 new tests). Re-verify run: 429 passed / 0 failed / 96.47% coverage. Ruff clean. Dependency audit clean. All tasks [x]. Secret-leakage mitigations (RISK-001) still verified. Lock correctness (RISK-003/004) unchanged — still verified via real-fd kernel tests.

**Re-verify date**: 2026-07-03T18:00+07:00 | Tests: 429 (+6) | Coverage: 96.47% (+0.25 pp)

## Blockers

None. GO.

---

## Appendix: Deviations from Design (confirmed non-blocking)

| ID | Item | Verdict |
|----|------|---------|
| D-001 | `Preset(StrEnum)` instead of `(str, Enum)` | ✅ Semantically equivalent, Python 3.11+ canonical |
| D-002 | `X \| None` typing instead of `Optional[X]` | ✅ Python 3.13 style, ruff UP045 |
| D-003 | `Generator` from `collections.abc` | ✅ ruff UP035, equivalent |
| D-004 | `CliRunner(mix_stderr=False)` removed | ✅ Typer 0.26.7 compatibility; result.stderr still works |
| D-005 | `_is_tty` variable unused (F841) | ⚠️ B-002 Low — documented as technical debt, non-blocking at lite rigor |
