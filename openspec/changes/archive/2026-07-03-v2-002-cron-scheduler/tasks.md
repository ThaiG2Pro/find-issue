# Tasks — v2-002-cron-scheduler (ticket V2-002)

Implementation checklist for `/opsx:apply` (S4). Ordered by dependency per design.md
§Implementation Guide: foundational errors/lock → pure generators → OS-adapter seams → CLI wiring →
tests. Every subtask lists its file and the AC-IDs it satisfies.

## 1. Foundations — errors + single-instance lock

- [x] 1.1 Create `ScheduleError(Exception)` (one error class for the schedule module, mirrors `state/errors.py`).
  File: `src/osspulse/schedule/errors.py`
  _Requirements: AC-V2-002-006, AC-V2-002-013, AC-V2-002-016_
- [x] 1.2 Create the `schedule` package init exporting the public surface (`generate_line`, `generate_workflow`, `CrontabClient`, `upsert_block`, `remove_block`, `ScheduleError`).
  File: `src/osspulse/schedule/__init__.py`
  _Requirements: AC-V2-002-001, AC-V2-002-014_
- [x] 1.3 Implement `single_instance_lock(state_path)` context manager + `LockHeldError` using `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `Path(state_path).parent / "osspulse.lock"` (0o600); `BlockingIOError` → `LockHeldError`; release via `LOCK_UN`+`close` in `finally`; kernel auto-release on process death (ADR-004).
  File: `src/osspulse/lock.py`
  _Requirements: AC-V2-002-021, AC-V2-002-022, AC-V2-002-023_

## 2. Pure generators — cron line, secret guard, workflow

- [x] 2.1 Implement `PRESETS` map (`hourly`→`0 * * * *`, `daily`→`0 8 * * *`, `weekly`→`0 8 * * 1`) and `validate_cron_expr(expr)` (5-field, per-field range check; raises `ScheduleError`; runs before any write).
  File: `src/osspulse/schedule/cron.py`
  _Requirements: AC-V2-002-003, AC-V2-002-006, AC-V2-002-008_
- [x] 2.2 Implement `resolve_binary()` (`shutil.which("osspulse")` → fallback `os.path.abspath(sys.argv[0])`) and config-path resolution to absolute (ADR-002; no cron-PATH verification).
  File: `src/osspulse/schedule/cron.py`
  _Requirements: AC-V2-002-004, AC-V2-002-024_
- [x] 2.3 Implement `generate_line(cron_expr, binary, config_path)` producing the crontab line invoking `osspulse run --config <abs>` with absolute paths, referencing env/`.env` (no inlined secret).
  File: `src/osspulse/schedule/cron.py`
  _Requirements: AC-V2-002-001, AC-V2-002-002, AC-V2-002-005_
- [x] 2.4 Implement `collect_secret_values(env)` + `assert_no_secret(text, values)` (raises `ScheduleError` if any non-empty secret is a substring of `text`) — the shared RISK-001 backstop.
  File: `src/osspulse/schedule/secrets.py`
  _Requirements: AC-V2-002-005, AC-V2-002-015_
- [x] 2.5 Implement `generate_workflow(cron_expr)` emitting valid Actions YAML: `on.schedule.cron`, a job step running `osspulse run`, `${{ secrets.* }}` refs for GITHUB_TOKEN/LLM key, and a comment noting cron is evaluated in UTC.
  File: `src/osspulse/schedule/workflow.py`
  _Requirements: AC-V2-002-014, AC-V2-002-015, AC-V2-002-017_

## 3. Checkpoint — foundations + generators

- [x] 3.1 CHECKPOINT (mid-build): run `pytest` for lock + cron + secrets + workflow units, `ruff` lint/format, and `test:cov` for the new pure modules. Verify: flock benign-skip + crash-release behavior, cron validation fail-fast, no-secret-substring guard, preset/default mapping, UTC comment present. STOP for human review.
  File: `tests/` (test_lock.py, test_schedule_cron.py, test_schedule_secrets.py, test_schedule_workflow.py)
  _Requirements: AC-V2-002-003, AC-V2-002-005, AC-V2-002-008, AC-V2-002-014, AC-V2-002-015, AC-V2-002-017, AC-V2-002-021, AC-V2-002-022, AC-V2-002-023_

## 4. Crontab adapter — managed block + mockable client

- [x] 4.1 Implement pure `upsert_block(current, cron_line)` and `remove_block(current)` with pinned markers `# >>> osspulse >>>` / `# <<< osspulse <<<`; idempotent replace-in-place; byte-preserving; guaranteed round-trip (ADR-007).
  File: `src/osspulse/schedule/crontab.py`
  _Requirements: AC-V2-002-009, AC-V2-002-010, AC-V2-002-011, AC-V2-002-012_
- [x] 4.2 Implement `CrontabClient` wrapping `subprocess` (`read()`=`crontab -l` normalized to `""` when empty; `write(text)`=`crontab -` via stdin); raise `ScheduleError` when `crontab` binary is absent (ADR-008).
  File: `src/osspulse/schedule/crontab.py`
  _Requirements: AC-V2-002-013, AC-V2-002-024_

## 5. CLI wiring — `schedule` command + cron-safe `run`

- [x] 5.1 Add the `schedule` Typer command (flags `--config`, `--cron`, `--preset`, `--install`, `--uninstall`, `--github-actions`, `--output`): reject `--cron`+`--preset` as mutually exclusive; resolve cadence (default `0 8 * * *`); validate before any write; print-only default; install/uninstall via `CrontabClient`+block funcs; `--github-actions` prints or writes to `--output` (atomic temp+replace, no partial file on unwritable parent); `assert_no_secret` on every generated output.
  File: `src/osspulse/cli.py`
  _Requirements: AC-V2-002-001, AC-V2-002-002, AC-V2-002-007, AC-V2-002-008, AC-V2-002-009, AC-V2-002-010, AC-V2-002-011, AC-V2-002-012, AC-V2-002-016_
- [x] 5.2 Add the `schedule` error boundary: `ScheduleError` → `Error: <msg>` stderr exit 1, no traceback (invalid cron, mutually-exclusive, crontab-missing, unwritable output, secret-leak backstop).
  File: `src/osspulse/cli.py`
  _Requirements: AC-V2-002-006, AC-V2-002-013, AC-V2-002-016_
- [x] 5.3 Wrap `run` in `single_instance_lock(cfg.state_path)`; add `LockHeldError` handler ORDERED FIRST → WARN via logger + exit 0 (benign skip), before the exit-1 fatal arms.
  File: `src/osspulse/cli.py`
  _Requirements: AC-V2-002-021, AC-V2-002-022_
- [x] 5.4 Add cron-safe hardening to `run`: `sys.stdout.isatty()` no-color guard; ensure no interactive prompt in the run path; reaffirm deterministic exit codes (0 success incl. no-new-items; 1 fatal) — reaffirm scheduler-cli-7 logging, do not rewrite it (ADR-010).
  File: `src/osspulse/cli.py`
  _Requirements: AC-V2-002-018, AC-V2-002-019, AC-V2-002-020_

## 6. Tests — crontab round-trip, CLI integration, cron-safe run

- [x] 6.1 Crontab round-trip + preservation tests: install adds one block; re-install replaces (no duplicate); install→install→uninstall byte-identical to original; unrelated lines preserved byte-for-byte; uninstall-absent no-op; trailing-newline handling.
  File: `tests/test_schedule_crontab.py`
  _Requirements: AC-V2-002-009, AC-V2-002-010, AC-V2-002-011, AC-V2-002-012_
- [x] 6.2 `schedule` CLI tests (fake `CrontabClient`): print default daily line; `--cron` verbatim; `--preset` mapping; absolute paths in line; mutual-exclusion error exit 1; invalid cron exit 1 no write; crontab-missing exit 1; `--github-actions` YAML with schedule+UTC comment+secrets refs; `--output` writes file, unwritable parent exit 1 no partial file; no secret substring in any output.
  File: `tests/test_cli_schedule.py`
  _Requirements: AC-V2-002-001, AC-V2-002-002, AC-V2-002-003, AC-V2-002-004, AC-V2-002-005, AC-V2-002-006, AC-V2-002-007, AC-V2-002-008, AC-V2-002-013, AC-V2-002-014, AC-V2-002-015, AC-V2-002-016, AC-V2-002-017, AC-V2-002-024_
- [x] 6.3 Cron-safe `run` + lock integration tests: run with non-TTY stdin/stdout completes without prompt; no ANSI escape in captured output; exit 0 on success incl. no-new-items and exit 1 only on established fatals; two-fd flock contention → second run WARN + exit 0 (pipeline not invoked); close-fd-then-reacquire proves crash auto-release.
  File: `tests/test_cli_run_cronsafe.py`
  _Requirements: AC-V2-002-018, AC-V2-002-019, AC-V2-002-020, AC-V2-002-021, AC-V2-002-022, AC-V2-002-023_

## 7. Checkpoint — final

- [x] 7.1 CHECKPOINT (final): full `pytest` suite + coverage gate (≥80% lines) + `ruff` lint/format clean; run `cross-artifact-audit` (0 CRITICAL) and `openspec change validate "v2-002-cron-scheduler"` (PASS); update README §Scheduling (OS cron primary, Actions optional, UTC vs local TZ, overlap benign-skip, `python -m` binary-path gotcha). STOP for human review before S5.
  File: `README.md`
  _Requirements: AC-V2-002-005, AC-V2-002-011, AC-V2-002-017, AC-V2-002-022, AC-V2-002-023_
