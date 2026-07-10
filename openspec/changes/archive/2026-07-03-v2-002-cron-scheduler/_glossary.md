# Glossary — v2-002-cron-scheduler (ticket V2-002)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| Schedule (osspulse) | The cadence on which `osspulse run` fires unattended, expressed as a cron expression; produced by `osspulse schedule` and executed by OS cron (primary) or GitHub Actions cron (optional). osspulse itself stays single-shot. | analyst | AC-V2-002-001 | S1 |
| OS cron | The Unix system cron daemon — the PRIMARY scheduling target per PROJECT_SPEC §8; runs in the system local timezone. | analyst | AC-V2-002-001 | S1 |
| GitHub Actions cron | The OPTIONAL secondary scheduler — an `on.schedule.cron` workflow that runs `osspulse run` in CI; evaluated in UTC. | analyst | AC-V2-002-014 | S1 |
| Managed block | A marker-delimited region (`# >>> osspulse >>>` … `# <<< osspulse <<<`) inside the operator's crontab that `--install`/`--uninstall` owns; everything outside is preserved verbatim. | analyst | BR-V2-002-002 | S1 |
| Preset (cadence) | A named shorthand — `hourly` (`0 * * * *`), `daily` (`0 8 * * *`), `weekly` (`0 8 * * 1`) — mapping to a standard cron expression. | analyst | AC-V2-002-003 | S1 |
| Single-instance lock | An exclusive advisory lock acquired by `osspulse run` under `state_path.parent`, ensuring at most one pipeline mutates a given state file at a time. | analyst | BR-V2-002-004 | S1 |
| Benign overlap skip | Behavior when a scheduled run finds the lock held: it logs WARN and exits 0 (not a failure), keeping cron mail quiet. | analyst | BR-V2-002-005 | S1 |
| Stale-lock deadlock | The failure mode where a crashed run leaves a lock held forever, blocking future runs; avoided by using an OS advisory lock (`fcntl.flock`) auto-released on process death. | analyst | AC-V2-002-023 | S1 |
| Cron-safe run | An `osspulse run` invocation that never prompts, needs no TTY, emits deterministic exit codes, and produces no ANSI color when stdout is not a terminal. | analyst | AC-V2-002-018 | S1 |
| Secretless artifact | A generated crontab line or workflow YAML that references env/`.env` (cron) or the repo secrets store (Actions) and never inlines a token/key value. | analyst | BR-V2-002-001 | S1 |
| Binary path resolution | How the generator computes the absolute `osspulse` executable path for a crontab line: `shutil.which("osspulse")`, falling back to an absolute resolution of `sys.argv[0]`. No cron-daemon PATH verification is performed. | analyst | AC-V2-002-004, AC-V2-002-024 | S2 |
| Cron-PATH verification (rejected) | The rejected alternative of probing whether the `osspulse` binary is reachable on the cron daemon's minimal PATH; made unnecessary by emitting an absolute path. | analyst | AC-V2-002-024 | S2 |
| single_instance_lock | `src/osspulse/lock.py` context manager that acquires `fcntl.flock(fd, LOCK_EX\|LOCK_NB)` on `state_path.parent/osspulse.lock`; yields to the pipeline, releases (`LOCK_UN`+close) in `finally`; kernel auto-frees on process death. | architect | AC-V2-002-021 | S3 |
| LockHeldError | Benign exception raised by `single_instance_lock` on `BlockingIOError` (lock already held); the CLI maps it to WARN + exit 0 — distinct from fatal `ScheduleError` (exit 1). | architect | AC-V2-002-022 | S3 |
| ScheduleError | The one fatal error class for the `schedule` module (`schedule/errors.py`); surfaces as `Error: <msg>` stderr exit 1 (invalid cron, mutually-exclusive flags, crontab missing, unwritable output, secret-leak backstop). Mirrors `StateError`/`DeliveryError`. | architect | AC-V2-002-006 | S3 |
| assert_no_secret | Shared RISK-001 backstop in `schedule/secrets.py`; raises `ScheduleError` if any non-empty secret value is a substring of the generated text; called by BOTH the crontab-line and workflow generators. | architect | AC-V2-002-005, AC-V2-002-015 | S3 |
| upsert_block / remove_block | Pure crontab string transforms (`schedule/crontab.py`) that insert/replace/remove the marker-delimited managed block byte-preservingly; guarantee `remove_block(upsert_block(x)) == x`. | architect | AC-V2-002-010, AC-V2-002-011 | S3 |
| CrontabClient | Mockable subprocess wrapper (`schedule/crontab.py`): `read()`=`crontab -l` (normalized to `""` when empty), `write()`=`crontab -`; raises `ScheduleError` when the `crontab` binary is absent. | architect | AC-V2-002-013 | S3 |
| resolve_binary | `schedule/cron.py` helper computing the absolute `osspulse` path: `shutil.which("osspulse")` → fallback `os.path.abspath(sys.argv[0])`; no cron-PATH verification. | architect | AC-V2-002-004, AC-V2-002-024 | S3 |
