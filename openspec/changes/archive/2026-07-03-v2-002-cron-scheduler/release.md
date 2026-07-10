# Release — V2-002 (v2-002-cron-scheduler)
Date: 2026-07-03
Deploy strategy: direct (CLI tool — no HTTP service, no blue-green/canary required)

## Release Notes

### Features

- **`osspulse schedule` — OS crontab entry generator** (AC-V2-002-001 – 005, AC-V2-002-008)
  New `osspulse schedule` command prints a ready-to-use OS crontab line to stdout.
  Use `--preset {hourly|daily|weekly}` or `--cron "<expr>"` to choose a cadence; omitting both
  defaults to daily at 08:00 local time (`0 8 * * *`). The generated line always uses absolute
  paths (binary resolved via `shutil.which("osspulse")` → `sys.argv[0]` fallback; config path
  resolved to absolute form) so the entry works under cron's minimal PATH. No secret value is ever
  inlined — the generated line references the operator's environment, not raw token values.

- **`osspulse schedule --install` / `--uninstall` — managed crontab block** (AC-V2-002-009 – 013, AC-V2-002-024)
  `--install` adds a marker-delimited block (`# >>> osspulse >>>` … `# <<< osspulse <<<`) to the
  invoking user's crontab. Repeated installs are idempotent — the block is replaced in place, never
  duplicated. `--uninstall` removes only the managed block; all other crontab jobs are preserved
  byte-for-byte. `--uninstall` is a no-op (exit 0) when no block is present. If the `crontab`
  command is not on PATH, both flags fail fast with `Error: <message>` on stderr (exit 1).
  The command DOES NOT attempt to verify the binary against the cron daemon's PATH — the emitted
  absolute path makes that unnecessary.

- **`osspulse schedule --github-actions` — secretless CI cron workflow** (AC-V2-002-014 – 017)
  Emits a GitHub Actions workflow YAML with an `on.schedule.cron` trigger. Secrets (`GITHUB_TOKEN`,
  LLM key) are referenced via `${{ secrets.* }}` — never inlined. The YAML includes a comment
  noting that GitHub Actions `schedule.cron` is evaluated in UTC (distinct from OS cron's local
  time). Use `--output PATH` to write directly to a file; an unwritable destination fails with
  `Error: <message>` exit 1 and leaves no partial file.

- **Single-instance lock on `osspulse run`** (AC-V2-002-021 – 023)
  `osspulse run` now acquires an exclusive `fcntl.flock(LOCK_EX|LOCK_NB)` lock (co-located with
  the state file under `state_path.parent`) before executing the pipeline. A second concurrent run
  that finds the lock already held logs a WARN and exits **0** (a benign skip — deliberately not a
  non-zero exit, so an overrunning cron cadence never emails a spurious failure). The lock is an
  OS advisory lock — if a run is hard-killed (`kill -9`), the kernel releases the lock automatically
  on process death, eliminating stale-lock deadlocks with no manual heuristic required.

  > **Load-bearing exit-code contract**: `LockHeldError` is intentionally NOT a subclass of
  > `ScheduleError`. The CLI exception handler for `LockHeldError` MUST remain the first `except`
  > clause in `cli.run`. Any future refactor that reorders or merges exception arms must re-verify
  > the overlap-skip exit-0 contract (guarded by `test_run_lock_held_exits_0_not_1`).

- **Cron-safe hardening on `osspulse run`** (AC-V2-002-018 – 020)
  When `stdout` is not attached to a TTY (as under cron or redirected to a file), `osspulse run`
  automatically sets `NO_COLOR=1` in the process environment before invoking the pipeline, ensuring
  zero ANSI escape sequences appear in cron mail or log files. The command never prompts and
  requires no TTY for any code path.

- **Schedule validation fail-fast** (AC-V2-002-006 – 007)
  An invalid cron expression (e.g. `--cron "99 * * * *"`) is rejected before any write with
  `Error: <message>` on stderr (exit 1, no traceback). `--cron` and `--preset` are mutually
  exclusive — combining both is rejected with an explicit error.

### Bug fixes
- None (feature release).

### Breaking changes
- `osspulse run` now acquires a file lock before running. On systems where `fcntl` is unavailable
  (non-POSIX / Windows), the lock silently degrades to a no-op (no behavioral change in that case,
  but concurrent runs will not be serialized). **This is expected** — the tool targets Linux/macOS.
- The `NO_COLOR` environment variable is now set by `osspulse run` when stdout is not a TTY.
  Any downstream process that explicitly relies on `NO_COLOR` being unset in a non-TTY context
  should explicitly clear it. This is only relevant to shell pipelines, not to cron invocations.

### Dependency changes
- None. No new packages added; `fcntl` is stdlib (POSIX only).

### Security notes
- **RISK-001 (Information Disclosure) — MITIGATED**: A runtime backstop (`assert_no_secret`)
  verifies that no `GITHUB_TOKEN` or LLM key value appears in any generated output. Applied at both
  the crontab line generator and the GitHub Actions workflow generator. All 3 Low QA findings
  (B-001, B-002, B-003) were resolved before GO.
- **RISK-002 (Tampering) — MITIGATED**: `--install`/`--uninstall` are confined to the
  marker-delimited managed block; round-trip idempotency verified by tests.
- **RISK-003 (DoS overlap) — MITIGATED**: single-instance lock prevents concurrent pipeline
  mutations to the state file.
- **RISK-004 (Stale lock) — MITIGATED**: `fcntl.flock` advisory lock auto-released by the OS
  kernel on process death.

---

## Migration Checklist
| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | N/A — no database | — | — | — | — |

No state file schema changes. Existing `.osspulse/state.json` files are fully compatible.
A new lock file (`<state_path_parent>/osspulse.lock`) is created on the first `osspulse run`
after upgrade — this file can be safely deleted if needed (it is recreated on the next run).

---

## Deploy Checklist

### Pre-deploy
- [ ] Branch `feature/V2-002-cron-scheduler` pushed to remote and PR created
- [ ] CI green on the branch (lint + tests — 429 passing, 96.47% coverage)
- [ ] PR reviewed and approved
- [ ] Merge PR → `feature/V2-001-delta-filter` (or main, per project branching strategy)

### Post-deploy smoke tests

**Schedule command smoke tests** (requires the installed `osspulse` binary):

- [ ] `osspulse schedule` → prints one crontab line with `0 8 * * *`, absolute binary path, no
      secret value, exits 0. Confirms default daily preset.
- [ ] `osspulse schedule --preset daily` → same cron expression `0 8 * * *`. Confirms preset mapping.
- [ ] `osspulse schedule --preset hourly` → cron expression `0 * * * *`. Confirms preset mapping.
- [ ] `osspulse schedule --preset weekly` → cron expression `0 8 * * 1`. Confirms preset mapping.
- [ ] `osspulse schedule --cron "30 6 * * 1"` → printed line begins with `30 6 * * 1`. Confirms passthrough.
- [ ] `osspulse schedule --cron "99 * * * *"` → `Error:` on stderr, exit 1, no crontab line printed.
      Confirms validation fail-fast.
- [ ] `osspulse schedule --cron "0 8 * * *" --preset daily` → mutual-exclusion error, exit 1.

**Install/Uninstall smoke tests** (sandbox crontab — use a test user or `EDITOR=cat crontab -e`
to inspect; this smoke test requires a real crontab subprocess and CANNOT be run in CI):

- [ ] `osspulse schedule --install` on a clean crontab → managed block appears between markers,
      cron line uses absolute path, exits 0.
- [ ] `osspulse schedule --install` a second time → crontab still contains exactly ONE managed
      block (idempotent replace), exits 0.
- [ ] `osspulse schedule --install --preset hourly` → managed block updated to hourly expression
      in place (no duplicate block).
- [ ] `osspulse schedule --uninstall` → managed block removed, any pre-existing unrelated jobs
      preserved byte-for-byte, exits 0.
- [ ] `osspulse schedule --uninstall` on a crontab with no managed block → no-op, exits 0.

**GitHub Actions smoke test**:

- [ ] `osspulse schedule --github-actions` → emits valid YAML with `on.schedule.cron`, a step
      running `osspulse run`, references `${{ secrets.GITHUB_TOKEN }}`, contains UTC comment,
      exits 0.
- [ ] `osspulse schedule --github-actions --output /tmp/osspulse-test.yml` → file written,
      content as above, exits 0.

**Single-instance lock smoke test**:

- [ ] `osspulse run --config config.toml` → lock file created at `<state_path_parent>/osspulse.lock`
      during run, lock released (file remains but is unlocked) after run completes.
- [ ] Start `osspulse run --config config.toml` in background, immediately start a second
      `osspulse run --config config.toml` → second run logs WARN "already in progress" and exits 0,
      first run completes normally.

**Cron-safe / BrokenPipeError smoke test** (requires a real pipe — CANNOT be run in CI):

- [ ] `osspulse run --config config.toml | head -1` → command exits without a Python traceback
      (BrokenPipeError suppressed), exits 0 or 1 depending on pipeline result. Confirms
      `_handle_broken_pipe()` guard.
- [ ] `NO_COLOR=` `osspulse run --config config.toml 2>&1 | cat` → output contains no ANSI
      escape sequences. Confirms non-TTY color suppression.

---

## Rollback Plan

**Forward-fixable** (bug found in dev/stg before master promotion, or in master without a
reverted deploy): open a new `bugfix` or `hotfix` pipeline. Do not touch this archived change
or hand-edit `openspec/specs/scheduler-cli/spec.md`.

**Real rollback** (deploy reverted):
1. `git revert <archive-merge-commit>` — undoes both the code and the spec fold atomically.
   Never hand-edit `openspec/specs/scheduler-cli/spec.md` back manually.
2. The lock file (`<state_path_parent>/osspulse.lock`) left on disk by the rolled-back release
   is harmless — `fcntl.flock` advisory locks are process-local and do not persist across process
   death. The file can be deleted manually if desired.
3. Confirm rollback: `uv run pytest -q` on the reverted code — all pre-V2-002 tests should pass;
   `tests/test_lock.py`, `tests/test_schedule_*.py`, `tests/test_cli_schedule.py`,
   `tests/test_cli_run_cronsafe.py` should not exist on that commit.

---

## Archive
- [x] `openspec archive "v2-002-cron-scheduler"` run on 2026-07-03 — spec deltas (+6 requirements)
      merged into `openspec/specs/scheduler-cli/spec.md`; change moved to
      `openspec/changes/archive/2026-07-03-v2-002-cron-scheduler/`.
- [ ] `_state.json.deploy_status` initialized: `{"dev":"pending","master":"pending"}` — updated
      out-of-band as each real promotion completes via
      `node .kiro/tools/state-set.mjs --change v2-002-cron-scheduler --set deploy_status.<env>=pass`.
      Not a gate — a breadcrumb only.

---

## If Rejected After Archive (Revert Playbook)
- **Forward-fixable**: open a new `bugfix` or `hotfix` pipeline. Do not touch this archived
  change or hand-edit `openspec/specs/`.
- **Real rollback** (deploy reverted): `git revert <archive-merge-commit>` — undoes code AND
  spec fold atomically. Never hand-edit `openspec/specs/scheduler-cli/spec.md` back manually.

---

## S6 Operator Checklist (items that could not be verified in CI)

The following two smoke tests require a real subprocess environment (OS crontab command present,
real pipe, or real terminal) and MUST be performed manually by the operator before production:

1. **`--install` / `--uninstall` real crontab**: run in a sandbox user account (or use
   `EDITOR=cat crontab -e` to inspect without saving). Verify managed block is added, replaced
   idempotently, and removed cleanly without touching unrelated jobs.

2. **Live pipe smoke test**: `osspulse run --config config.toml | head -1` — confirm no Python
   traceback appears in stderr and the process exits cleanly (BrokenPipeError suppressed by
   `_handle_broken_pipe()` in cli.py).
