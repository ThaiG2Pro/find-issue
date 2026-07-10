## Why

`osspulse run` (delivered by scheduler-cli-7) runs the full pipeline end-to-end but only when a human types the command. PROJECT_SPEC §3 group D-[P1] and §5 V2 call for the digest to be produced **on a schedule** so the operator gets a periodic digest without remembering to run it. PROJECT_SPEC §8 fixes the mechanism: **OS cron is the primary target, GitHub Actions cron is optional, and there must be no complex background service** ("Một script + cron là đủ"). This change makes scheduled, unattended execution a first-class, safe, documented capability — without turning osspulse into a long-running daemon.

## What Changes

- Add a new CLI subcommand **`osspulse schedule`** that generates a ready-to-use **OS crontab entry** for `osspulse run` (default output: print the line to stdout).
- `osspulse schedule --preset {hourly|daily|weekly}` or `--cron "<expr>"` selects the cadence; the schedule spec is **validated before any write** (fail fast on an invalid expression).
- `osspulse schedule --install` / `--uninstall` idempotently manages a **marker-delimited managed block** inside the operator's crontab (opt-in; default is print-only so nothing in the user's environment is touched implicitly).
- `osspulse schedule --github-actions [--output PATH]` emits an optional **GitHub Actions cron workflow** (`.github/workflows/osspulse.yml`) that runs `osspulse run` in CI.
- Make `osspulse run` verifiably **cron-safe**: never prompts / requires no TTY, deterministic exit codes suitable for cron (reaffirming the scheduler-cli-7 contract), and no ANSI color when stdout is not a TTY.
- Add a **single-instance lock** to `osspulse run` so an overrunning cron schedule (a new fire while the previous run is still working) cannot run two pipelines concurrently against the same JSON state file.
- **Generated artifacts never embed secrets** — the crontab line references the config / env, and the workflow references the repository secrets store.
- Documentation: README section on scheduling (OS cron primary, GitHub Actions optional, TZ semantics, overlap behavior).

## Capabilities

### New Capabilities
- None. This change adds requirements to an existing capability.

### Modified Capabilities
- **`scheduler-cli`** — ADDED requirements only (the cron/scheduling surface that scheduler-cli-7 explicitly deferred as "V2, out of scope"). No existing scheduler-cli requirement changes behavior; the delta is purely additive. Delta spec: `specs/scheduler-cli/spec.md`.

## Impact

- **New code**: `osspulse.cli` gains a `schedule` subcommand; a new schedule/cron helper module (crontab-line + GitHub Actions workflow generation, managed-block install/uninstall); a single-instance lock utility used by `run_pipeline` / `cli.run`.
- **Touched code**: `osspulse.cli.run` / `osspulse.pipeline.run_pipeline` acquire the lock at start; TTY/color detection at the CLI boundary.
- **External**: shells out to the system `crontab` command for `--install`/`--uninstall` (INT-V2-002-001); optional generated GitHub Actions workflow.
- **Config**: reuses `Config.state_path` (state-store-3) for the lock location; the lock path derives from `state_path.parent` per ADR-002 (no new `Config` field — matches scheduler-cli-7 ADR-002 / github-collector-2 ADR-001 discipline). Flag as an architect decision (see Assumptions).
- **No daemon / no queue / no new service** — osspulse stays single-shot; timing is delegated to OS cron or CI cron.

---

## Non-Goals

- ❌ **No long-running daemon / in-process scheduler** (no APScheduler, no `while True: sleep` loop, no systemd service). PROJECT_SPEC §8: "Không cần service chạy nền phức tạp". osspulse remains single-shot; the OS (or CI) owns the timer.
- ❌ No real-time / event-driven triggering ("issue opened 30s ago") — against the project philosophy (PROJECT_SPEC §5 Out of Scope).
- ❌ No cross-platform Windows Task Scheduler support in this change (OS cron = Unix cron; documented). Windows users use WSL or the GitHub Actions path.
- ❌ No distributed / multi-host locking — the lock is a single-host, single-operator file lock (this is a personal/self-host tool).
- ❌ No new digest content or delivery channels — this change only governs *when* and *how safely* `osspulse run` fires, not *what* it produces.
- ❌ No secret management / vault integration — secrets continue to come from the gitignored `.env` (OS cron) or the repo secrets store (Actions).

## Assumptions

- **[CONFIRMED]** OS cron is the primary scheduling mechanism; GitHub Actions cron is an optional secondary. *(Source: PROJECT_SPEC §8 Tech Stack row "Scheduler".)*
- **[CONFIRMED]** osspulse must not become a background service; scheduling is delegated to the OS/CI. *(Source: PROJECT_SPEC §8 "Không cần service chạy nền phức tạp" + §7 lean principles.)*
- **[CONFIRMED]** `osspulse run` is already idempotent (delta filter + write-once `first_seen_at`), so repeated scheduled runs over unchanged activity render the "no new items" doc rather than duplicating output. *(Source: v2-001-delta-filter spec + state-store-3 constraints.)*
- **[CONFIRMED]** Generated cron/CI artifacts must never contain a token or API key — cron references `.env`/env, Actions references the repo secrets store. *(Source: PROJECT_SPEC §8 security notes + github-collector-2 ADR-004.)*
- **[ASSUMED]** The lock file lives at `state_path.parent / osspulse.lock` and is derived in the pipeline rather than added as a `Config` field, following scheduler-cli-7 ADR-002. *(Architect to confirm the derivation vs. a new `Config.lock_path` field at S3.)*
- **[ASSUMED]** A cron overlap (lock already held) is **benign**: the second run logs a WARN and exits **0** so cron does not email a spurious failure. *(An operator who wants a distinct "skipped" exit code can be revisited; default keeps cron mail quiet. Architect/BA to confirm at SPEC LOCK.)*
- **[ASSUMED]** Default cadence when the operator passes neither `--cron` nor `--preset` is **daily at 08:00 local time**. *(A sensible default for a "morning digest"; operator can override.)*
- **[ASSUMED]** The single-instance lock is implemented with an OS advisory file lock (`fcntl.flock`) that the kernel auto-releases on process death, so a hard-killed run leaves **no stale-lock deadlock**. *(Architect to confirm mechanism at S3; pidfile alternative would need stale-lock recovery.)*
- **[CONFIRMED]** `--install` does NOT verify the resolved `osspulse` binary against the cron daemon's PATH; instead the generator emits an **absolute** binary path (`shutil.which("osspulse")`, falling back to an absolute `sys.argv[0]`), which makes cron's minimal PATH irrelevant. *(Resolved at S2: AC-V2-002-004 / AC-V2-002-024, BR-V2-002-006. Emitting an absolute path is simpler and more robust than probing an environment cron will not reproduce.)*

## Edge Cases

1. **Input boundary** — `--cron "99 * * * *"` (out-of-range field) → validation fails fast, `Error: <message>` on stderr, exit 1, no crontab written.
2. **Input boundary** — both `--cron` and `--preset` supplied → mutually-exclusive error, exit 1.
3. **Input boundary** — neither `--cron` nor `--preset` → default to `daily` (08:00 local), documented.
4. **State transition** — `--install` when a managed block already exists → the block is *replaced* idempotently (no duplicate cron entries after N installs).
5. **State transition** — `--uninstall` when no managed block exists → no-op, exit 0 (not an error).
6. **Integration** — the system `crontab` command is not installed / not on PATH → `--install`/`--uninstall` fail with a clear `Error:` message, exit 1.
7. **Data integrity** — generated crontab line uses a *relative* config or binary path → breaks under cron's minimal cwd/PATH; the generator MUST emit absolute paths (BR-V2-002-006).
8. **Concurrency** — a new cron fire starts while the previous `osspulse run` is still working → the single-instance lock makes the second instance skip (WARN + exit 0), so the two runs never interleave `load → mark_seen → save` and lose a state update.
9. **Concurrency / data integrity** — a run is hard-killed (`kill -9`) leaving the lock held → the advisory lock is auto-released by the kernel on process death, so the next scheduled run is not deadlocked (no stale-lock).
10. **Permission / information disclosure** — generated GitHub Actions workflow must reference the token via `${{ secrets.* }}`, never inline the operator's real token value (BR-V2-002-001).
11. **Integration / TZ** — OS cron runs in the system timezone while GitHub Actions cron runs in **UTC**; the two generated artifacts document their respective TZ so a "daily 08:00" schedule is not silently off by hours.
12. **State transition** — the config file is moved/renamed after `--install` → the installed cron entry points at a stale path; documented as "re-run `osspulse schedule --install` after moving config".
13. **Permission** — `--github-actions --output PATH` where PATH's directory is not writable → `Error:` exit 1, no partial file.
14. **UI/UX (unattended)** — cron invokes `run` with no TTY → no interactive prompt, no pager, no ANSI color codes leak into the cron mail / log file.
15. **Concurrency (pathological)** — an every-minute schedule combined with a multi-minute LLM run → perpetual overlap; the lock keeps every fire safe and each skipped fire is logged, so the operator can see the schedule is too tight.

## Early Risk Flags

Threat model (STRIDE, focused — this feature generates artifacts that reference secrets and mutates the operator's crontab):

- **Information disclosure (HIGH)** — a naive generator could inline `GITHUB_TOKEN` / LLM key into the crontab line or workflow YAML, committing a secret to `.github/workflows` or exposing it in `crontab -l`. Mitigation: BR-V2-002-001 — artifacts reference `.env`/env (cron) or the repo secrets store (Actions); a test asserts no secret substring appears in any generated output (mirrors scheduler-cli-7 AC-7-014).
- **Tampering (MEDIUM)** — `--install`/`--uninstall` editing the operator's crontab could clobber unrelated jobs. Mitigation: BR-V2-002-002 — operate strictly inside marker-delimited managed block; everything outside is preserved verbatim; idempotent replace.
- **Denial of service (MEDIUM)** — overrunning schedules could spawn concurrent pipelines racing the JSON state file and corrupting `first_seen_at`/losing updates. Mitigation: BR-V2-002-004 single-instance lock; benign skip (BR-V2-002-005).
- **Repudiation (LOW)** — unattended runs with no record leave the operator unable to tell whether a scheduled run happened/failed. Mitigation: reaffirm scheduler-cli-7 per-repo + summary logging (AC-7-015/AC-7-021) is cron-mail friendly (timestamped, no color, no secret).
- **Elevation of privilege (LOW)** — `--install` writing crontab with the wrong user/permissions. Mitigation: install into the *invoking user's* crontab only; never `sudo`; documented.

## Business Rules

- **BR-V2-002-001**: Generated cron/CI artifacts MUST NOT contain any secret value; the crontab line references env/`.env` and the GitHub Actions workflow references the repository secrets store.
- **BR-V2-002-002**: `--install`/`--uninstall` operate ONLY within a marker-delimited managed block; all other crontab content is preserved byte-for-byte.
- **BR-V2-002-003**: The schedule spec is validated BEFORE any file write or crontab mutation; an invalid spec fails fast with no partial write.
- **BR-V2-002-004**: At most one `osspulse run` executes per state file at any instant, enforced by a single-instance lock.
- **BR-V2-002-005**: A cron overlap (lock already held) is benign — the second run logs WARN and exits 0; it is never a fatal error.
- **BR-V2-002-006**: Generated invocation paths (osspulse binary + config file) MUST be absolute so the entry works under cron's minimal cwd/PATH.
- **BR-V2-002-007**: osspulse remains single-shot; scheduling/timing is delegated to OS cron or CI cron — no in-process daemon or long-running service.

## Integration Points

- **INT-V2-002-001**: `osspulse schedule --install/--uninstall` shells out to the system `crontab` command (read current, edit managed block, write back).
- **INT-V2-002-002**: the generated crontab entry and the generated GitHub Actions workflow both invoke `osspulse run` — the scheduler-cli-7 CLI export.
- **INT-V2-002-003**: the single-instance lock is created under `state_path.parent` (state-store-3 `Config.state_path`), keeping the lock co-located with the state it protects.
- **INT-V2-002-004**: the generated GitHub Actions workflow references the repository secrets store for `GITHUB_TOKEN` (and any LLM key) rather than inlining values.

## Figma
Figma: N/A (CLI tool — no visual design surface).

---
## _Structured Extract

### AC List
- AC-V2-002-001: [CONFIRMED] `osspulse schedule` (no cadence flag) prints a daily crontab line invoking `osspulse run`
- AC-V2-002-002: [CONFIRMED] `--cron "<expr>"` uses the given expression in the generated line
- AC-V2-002-003: [CONFIRMED] `--preset hourly|daily|weekly` maps to a standard cron expression
- AC-V2-002-004: [CONFIRMED] generated line uses absolute binary + config paths (shutil.which/sys.argv[0]; no cron-PATH verify)
- AC-V2-002-005: [CONFIRMED] generated crontab line contains no secret value
- AC-V2-002-006: [CONFIRMED] invalid cron expression → `Error:` exit 1, no traceback, no write
- AC-V2-002-007: [CONFIRMED] `--cron` and `--preset` together → mutually-exclusive error exit 1
- AC-V2-002-008: [CONFIRMED] neither cadence flag → default preset daily 08:00 local
- AC-V2-002-009: [CONFIRMED] `--install` appends a marker-delimited managed block to the user crontab
- AC-V2-002-010: [CONFIRMED] re-install replaces the managed block (idempotent, no duplicate)
- AC-V2-002-011: [CONFIRMED] `--install` preserves all crontab lines outside the managed block
- AC-V2-002-012: [CONFIRMED] `--uninstall` removes only the managed block; absent → no-op exit 0
- AC-V2-002-013: [CONFIRMED] `crontab` command unavailable → `Error:` exit 1
- AC-V2-002-014: [CONFIRMED] `--github-actions` emits valid workflow YAML with `on.schedule.cron`
- AC-V2-002-015: [CONFIRMED] workflow references repo secrets for the token, never inlines it
- AC-V2-002-016: [CONFIRMED] `--output` writes a file; unwritable path → `Error:` exit 1, no partial file
- AC-V2-002-017: [CONFIRMED] generated workflow documents its cron as UTC
- AC-V2-002-018: [CONFIRMED] `osspulse run` never prompts and requires no TTY
- AC-V2-002-019: [CONFIRMED] `osspulse run` exit codes are deterministic (0 success incl. no-new-items; 1 fatal)
- AC-V2-002-020: [CONFIRMED] no ANSI color emitted when stdout is not a TTY
- AC-V2-002-021: [CONFIRMED] `osspulse run` acquires an exclusive single-instance lock before the pipeline
- AC-V2-002-022: [CONFIRMED] concurrent second run detects the lock, logs WARN, exits 0 without running the pipeline
- AC-V2-002-023: [CONFIRMED] lock auto-released on process exit (incl. crash) via fcntl.flock — no stale-lock deadlock
- AC-V2-002-024: [CONFIRMED] `--install` writes the resolved absolute-path line without verifying the cron daemon PATH

### Business Rules
- BR-V2-002-001: No secret value in generated artifacts
- BR-V2-002-002: Install/uninstall confined to a managed block
- BR-V2-002-003: Validate schedule before any write (fail fast)
- BR-V2-002-004: Single-instance lock per state file
- BR-V2-002-005: Overlap skip is benign (exit 0)
- BR-V2-002-006: Generated paths are absolute
- BR-V2-002-007: No daemon — single-shot, timing delegated to cron/CI

### Integration Points
- INT-V2-002-001: schedule → system `crontab` command
- INT-V2-002-002: generated entry/workflow → `osspulse run` (scheduler-cli-7)
- INT-V2-002-003: lock → `state_path.parent` (state-store-3)
- INT-V2-002-004: workflow → repo secrets store

### Risk Flags
- RISK-001: Secret leakage into generated artifacts — HIGH (Information disclosure)
- RISK-002: Crontab clobbering unrelated jobs — MEDIUM (Tampering)
- RISK-003: Concurrent runs racing state file — MEDIUM (Denial of service)
- RISK-004: Stale lock deadlock on hard kill — MEDIUM (mitigated by advisory flock)

### Metadata
ticket_id: V2-002
domain: scheduler-cli
has_figma: false
has_cms_ui: false
actors: [operator]
ac_count: 24
ac_confirmed: 24
ac_assumed: 0
ac_missing: 0
ac_unclear: 0
