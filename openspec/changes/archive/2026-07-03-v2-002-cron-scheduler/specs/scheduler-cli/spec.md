## ADDED Requirements

### Requirement: osspulse schedule generates an OS crontab entry for osspulse run
The `osspulse schedule` command SHALL generate a ready-to-use OS crontab entry that invokes
`osspulse run` on a cadence, printing the line to stdout by default so nothing in the operator's
environment is mutated implicitly. The cadence SHALL be selectable via `--preset {hourly|daily|weekly}`
or `--cron "<expr>"`; when neither is given the command SHALL default to a daily schedule at 08:00
local time. The generated invocation SHALL use absolute paths for both the `osspulse` binary and the
config file so the entry works under cron's minimal cwd/PATH. This is the primary scheduling
mechanism per PROJECT_SPEC §8 (OS cron), and osspulse SHALL remain single-shot with timing delegated
to cron.

> ACs: AC-V2-002-001 [CONFIRMED], AC-V2-002-002 [CONFIRMED], AC-V2-002-003 [CONFIRMED], AC-V2-002-004 [CONFIRMED], AC-V2-002-005 [CONFIRMED], AC-V2-002-008 [CONFIRMED]
> Business rules: BR-V2-002-006, BR-V2-002-007, BR-V2-002-001
> Integration: INT-V2-002-002

#### Scenario: Bare schedule prints a daily crontab line (AC-V2-002-001) [CONFIRMED]
- **WHEN** `osspulse schedule` is invoked with no cadence flag
- **THEN** it prints one crontab line to stdout that runs `osspulse run` on the default daily schedule and exits 0, without touching the operator's crontab

#### Scenario: Explicit cron expression is used verbatim (AC-V2-002-002) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "30 6 * * 1"` is invoked with a valid expression
- **THEN** the printed crontab line begins with `30 6 * * 1` and invokes `osspulse run`

#### Scenario: Preset maps to a standard expression (AC-V2-002-003) [CONFIRMED]
- **WHEN** `osspulse schedule --preset hourly` (and likewise `daily`, `weekly`) is invoked
- **THEN** the printed line uses the corresponding standard cron expression (`hourly` → `0 * * * *`, `daily` → `0 8 * * *`, `weekly` → `0 8 * * 1`)

#### Scenario: Generated invocation uses absolute paths (AC-V2-002-004) [CONFIRMED]
- **WHEN** any crontab line is generated
- **THEN** both the `osspulse` executable and the `--config` path in the line are absolute paths (the binary is resolved via `shutil.which("osspulse")`, falling back to an absolute resolution of `sys.argv[0]`; the config path is resolved to its absolute form), never relative, so the entry runs correctly under cron's minimal working directory and minimal PATH — and the command does NOT attempt to verify the binary against the cron daemon's PATH (emitting the absolute path makes cron-PATH verification unnecessary)

#### Scenario: No cadence flag defaults to daily 08:00 local (AC-V2-002-008) [CONFIRMED]
- **WHEN** `osspulse schedule` is invoked with neither `--cron` nor `--preset`
- **THEN** the generated expression is `0 8 * * *` (daily 08:00 in the system local timezone)

#### Scenario: Generated crontab line contains no secret value (AC-V2-002-005) [CONFIRMED]
- **WHEN** `osspulse schedule` generates a crontab line in an environment where `GITHUB_TOKEN` and any LLM key are set
- **THEN** neither the token nor the api-key value appears anywhere in the generated line — the line references the config / environment, not the raw secret

### Requirement: Schedule specification is validated before any write
The command SHALL validate the resolved schedule specification before performing any file write or
crontab mutation so an invalid input fails fast with no partial side effect. An invalid cron
expression SHALL surface as `Error: <message>` on stderr with no Python traceback and exit 1, and
supplying both `--cron` and `--preset` SHALL be rejected as mutually exclusive.

> ACs: AC-V2-002-006 [CONFIRMED], AC-V2-002-007 [CONFIRMED]
> Business rules: BR-V2-002-003

#### Scenario: Invalid cron expression fails fast (AC-V2-002-006) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "99 * * * *"` (an out-of-range field) is invoked
- **THEN** the command prints `Error: <message>` on stderr, shows no traceback, exits 1, and neither prints a crontab line nor mutates any crontab

#### Scenario: --cron and --preset are mutually exclusive (AC-V2-002-007) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "0 8 * * *" --preset daily` is invoked
- **THEN** the command reports the flags are mutually exclusive on stderr and exits 1 without generating anything

### Requirement: schedule --install manages a marker-delimited crontab block idempotently
The `osspulse schedule --install` command SHALL install the generated entry inside a
marker-delimited managed block in the invoking user's crontab so repeated installs never create
duplicate entries and all crontab content outside the managed block is preserved verbatim.
Installation SHALL be opt-in (default behavior is print-only). `--uninstall` SHALL remove only the
managed block, and SHALL be a no-op exit 0 when no managed block is present. The command SHALL
operate on the invoking user's crontab only and SHALL never use elevated privileges.

> ACs: AC-V2-002-009 [CONFIRMED], AC-V2-002-010 [CONFIRMED], AC-V2-002-011 [CONFIRMED], AC-V2-002-012 [CONFIRMED], AC-V2-002-013 [CONFIRMED]
> Business rules: BR-V2-002-002
> Integration: INT-V2-002-001

#### Scenario: Install adds a managed block (AC-V2-002-009) [CONFIRMED]
- **WHEN** `osspulse schedule --install` is invoked and the user crontab has no osspulse block
- **THEN** a marker-delimited block (e.g. `# >>> osspulse >>>` … `# <<< osspulse <<<`) containing the cron line is added to the crontab and the command exits 0

#### Scenario: Re-install is idempotent (AC-V2-002-010) [CONFIRMED]
- **WHEN** `osspulse schedule --install` is invoked twice (or with a changed cadence)
- **THEN** the managed block is replaced in place and the crontab contains exactly one osspulse managed block (no duplicate entries)

#### Scenario: Install preserves unrelated crontab lines (AC-V2-002-011) [CONFIRMED]
- **WHEN** the user crontab already contains unrelated jobs and `--install` runs
- **THEN** every line outside the osspulse managed block is preserved byte-for-byte

#### Scenario: Uninstall removes only the managed block (AC-V2-002-012) [CONFIRMED]
- **WHEN** `osspulse schedule --uninstall` is invoked
- **THEN** only the osspulse managed block is removed, unrelated lines remain, and when no block exists the command is a no-op that exits 0

#### Scenario: crontab command unavailable is reported clearly (AC-V2-002-013) [CONFIRMED]
- **WHEN** `--install` or `--uninstall` runs on a host with no `crontab` command on PATH
- **THEN** the command prints `Error: <message>` on stderr, shows no traceback, and exits 1

#### Scenario: Install writes the absolute-path line without verifying the cron daemon PATH (AC-V2-002-024) [CONFIRMED]
- **WHEN** `osspulse schedule --install` installs the managed block
- **THEN** the installed cron line invokes the `shutil.which`/`sys.argv[0]`-resolved absolute `osspulse` binary path (AC-V2-002-004), and the command does NOT probe or assert the binary's presence on the cron daemon's PATH — because the emitted absolute path is independent of cron's minimal PATH, no such verification is performed

### Requirement: schedule --github-actions emits a secretless CI cron workflow
The `osspulse schedule --github-actions` command SHALL emit a GitHub Actions workflow that runs
`osspulse run` on an `on.schedule.cron` trigger, referencing the repository secrets store for the
GitHub token and any LLM key so no secret value is ever inlined. The generated workflow SHALL
document that GitHub Actions cron is evaluated in UTC. With `--output PATH` the workflow SHALL be
written to that path; an unwritable destination SHALL fail with `Error: <message>` exit 1 and leave
no partial file.

> ACs: AC-V2-002-014 [CONFIRMED], AC-V2-002-015 [CONFIRMED], AC-V2-002-016 [CONFIRMED], AC-V2-002-017 [CONFIRMED]
> Business rules: BR-V2-002-001
> Integration: INT-V2-002-004

#### Scenario: Workflow YAML has a schedule trigger (AC-V2-002-014) [CONFIRMED]
- **WHEN** `osspulse schedule --github-actions` is invoked
- **THEN** the emitted YAML is a valid workflow containing an `on.schedule` with a `cron` expression and a job step that runs `osspulse run`

#### Scenario: Workflow references secrets, never inlines them (AC-V2-002-015) [CONFIRMED]
- **WHEN** a workflow is generated in an environment where `GITHUB_TOKEN`/LLM key are set
- **THEN** the token and key are referenced via `${{ secrets.* }}` and neither raw value appears anywhere in the generated YAML

#### Scenario: --output writes a file, unwritable path errors cleanly (AC-V2-002-016) [CONFIRMED]
- **WHEN** `--github-actions --output <path>` is given a path whose parent directory is not writable
- **THEN** the command prints `Error: <message>` on stderr, exits 1, and writes no partial file

#### Scenario: Workflow documents UTC cron semantics (AC-V2-002-017) [CONFIRMED]
- **WHEN** a workflow is generated
- **THEN** the YAML includes a comment noting that GitHub Actions `schedule.cron` is evaluated in UTC (distinct from OS cron's local time)

### Requirement: osspulse run is cron-safe for unattended execution
The `osspulse run` command SHALL be safe to run unattended so that a cron/CI invocation never
blocks on input and produces deterministic, cron-friendly output. The command SHALL never prompt
and SHALL require no TTY, SHALL keep the deterministic exit-code contract (0 on success including
the no-new-items case; 1 on fatal ConfigError/AuthError/DeliveryError/StateError), and SHALL emit
no ANSI color codes when stdout is not a TTY.

> ACs: AC-V2-002-018 [CONFIRMED], AC-V2-002-019 [CONFIRMED], AC-V2-002-020 [CONFIRMED]
> Business rules: BR-V2-002-007
> Integration: INT-V2-002-002

#### Scenario: Run never prompts and needs no TTY (AC-V2-002-018) [CONFIRMED]
- **WHEN** `osspulse run` is invoked with stdin/stdout not attached to a terminal (as under cron)
- **THEN** the command completes the pipeline without ever awaiting interactive input

#### Scenario: Exit codes are deterministic for cron (AC-V2-002-019) [CONFIRMED]
- **WHEN** `osspulse run` completes a scheduled run
- **THEN** it exits 0 on success (including a delivered no-new-items digest) and exits 1 only on the established fatal errors, so cron can distinguish success from failure

#### Scenario: No ANSI color when not a TTY (AC-V2-002-020) [CONFIRMED]
- **WHEN** `osspulse run` writes to a non-TTY stdout (redirected to a file or cron mail)
- **THEN** the output contains no ANSI escape/color sequences

### Requirement: osspulse run enforces a single-instance lock to prevent overlapping schedules
The `osspulse run` command SHALL acquire an exclusive single-instance lock before executing the
pipeline so that at most one run mutates a given state file at a time, preventing a fast cron
cadence from racing two pipelines over the JSON state. The lock SHALL be co-located with the state
it protects (under `state_path.parent`). A second run that finds the lock held SHALL log a WARN and
exit 0 (a benign skip, not a failure), and the lock SHALL be released automatically on process exit
including an abnormal termination so a crashed run leaves no stale-lock deadlock.

> ACs: AC-V2-002-021 [CONFIRMED], AC-V2-002-022 [CONFIRMED], AC-V2-002-023 [CONFIRMED]
> Business rules: BR-V2-002-004, BR-V2-002-005
> Integration: INT-V2-002-003

#### Scenario: Run acquires the lock before the pipeline (AC-V2-002-021) [CONFIRMED]
- **WHEN** `osspulse run` starts
- **THEN** it acquires an exclusive lock under `state_path.parent` before invoking `run_pipeline`, and releases it when the run finishes

#### Scenario: Overlapping run skips benignly (AC-V2-002-022) [CONFIRMED]
- **WHEN** a second `osspulse run` starts while a first run still holds the lock
- **THEN** the second run does not execute the pipeline, logs a WARN that a run is already in progress, and exits **0** (a benign skip — deliberately NOT a distinct non-zero "skipped" code, so an overrunning cron cadence never emails a spurious failure)

#### Scenario: Lock auto-releases on crash (AC-V2-002-023) [CONFIRMED]
- **WHEN** a run holding the lock is terminated abnormally (e.g. `kill -9`)
- **THEN** the next scheduled run can acquire the lock (the `fcntl.flock` advisory lock is released by the OS kernel on process death) and is not blocked by a stale lock — no manual staleness heuristic (pidfile age / mtime timeout) is required

## Business Rules

Definitions for every business rule referenced by the requirements above:

- **BR-V2-002-001**: Generated cron/CI artifacts MUST NOT contain any secret value; the crontab line references env/`.env` and the GitHub Actions workflow references the repository secrets store. *(Referenced by AC-V2-002-005, AC-V2-002-015.)*
- **BR-V2-002-002**: `--install`/`--uninstall` operate ONLY within a marker-delimited managed block; all other crontab content is preserved byte-for-byte. *(Referenced by AC-V2-002-009..012.)*
- **BR-V2-002-003**: The schedule spec is validated BEFORE any file write or crontab mutation; an invalid spec fails fast with no partial write. *(Referenced by AC-V2-002-006, AC-V2-002-007.)*
- **BR-V2-002-004**: At most one `osspulse run` executes per state file at any instant, enforced by a single-instance lock. *(Referenced by AC-V2-002-021.)*
- **BR-V2-002-005**: A cron overlap (lock already held) is benign — the second run logs WARN and exits 0; it is never a fatal error. *(Referenced by AC-V2-002-022.)*
- **BR-V2-002-006**: Generated invocation paths (osspulse binary + config file) MUST be absolute so the entry works under cron's minimal cwd/PATH; the binary is resolved via `shutil.which`/`sys.argv[0]` and no cron-daemon PATH verification is performed. *(Referenced by AC-V2-002-004, AC-V2-002-024.)*
- **BR-V2-002-007**: osspulse remains single-shot; scheduling/timing is delegated to OS cron or CI cron — no in-process daemon or long-running service. *(Referenced by AC-V2-002-001, AC-V2-002-018.)*

## Integration Points

Definitions for every integration point referenced by the requirements above:

- **INT-V2-002-001**: `osspulse schedule --install/--uninstall` shells out to the system `crontab` command (read current, edit managed block, write back). *(Referenced by the install requirement.)*
- **INT-V2-002-002**: the generated crontab entry and the generated GitHub Actions workflow both invoke `osspulse run` — the scheduler-cli-7 CLI export. *(Referenced by the schedule-generation and cron-safe requirements.)*
- **INT-V2-002-003**: the single-instance lock is created under `state_path.parent` (state-store-3 `Config.state_path`), keeping the lock co-located with the state it protects. *(Referenced by the lock requirement.)*
- **INT-V2-002-004**: the generated GitHub Actions workflow references the repository secrets store for `GITHUB_TOKEN` (and any LLM key) rather than inlining values. *(Referenced by the github-actions requirement.)*

## Early Risk Flags

STRIDE-focused risks carried from S1 into design (see `proposal.md` §Early Risk Flags for full mitigations):

- **RISK-001 — Information disclosure (HIGH)**: a naive generator could inline `GITHUB_TOKEN`/LLM key into the crontab line or workflow YAML. Mitigation: BR-V2-002-001; a test asserts no secret substring appears in any generated output (AC-V2-002-005, AC-V2-002-015). Hardest surface = the Actions YAML path.
- **RISK-002 — Tampering (MEDIUM)**: `--install`/`--uninstall` could clobber unrelated crontab jobs. Mitigation: BR-V2-002-002 managed-block confinement + idempotent replace; round-trip test (install→install→uninstall leaves the crontab byte-identical) (AC-V2-002-010, AC-V2-002-011).
- **RISK-003 — Denial of service (MEDIUM)**: overrunning schedules could race concurrent pipelines over the JSON state file. Mitigation: BR-V2-002-004 single-instance lock + BR-V2-002-005 benign skip (AC-V2-002-021, AC-V2-002-022).
- **RISK-004 — Stale-lock deadlock (MEDIUM)**: a hard-killed run could leave the lock held forever. Mitigation: `fcntl.flock` advisory lock auto-released by the kernel on process death (AC-V2-002-023).
