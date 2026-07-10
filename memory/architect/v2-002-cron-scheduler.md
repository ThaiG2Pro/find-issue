## 2026-07-03 — v2-002-cron-scheduler: benign-outcome paths need a SEPARATE exception, not a flag on the fatal error class

The per-module-one-error-class convention (delivery-6/state) maps a module's error to `Error:` exit
1. But a single-instance lock's overlap path must exit **0** (benign skip), not 1. The clean design
is a distinct `LockHeldError` in `lock.py` (separate from the fatal `ScheduleError`) that the CLI
error ladder matches FIRST → WARN + `typer.Exit(0)`, before the exit-1 arms. Generalizes: whenever a
new code path has a *different exit-code contract* than a module's fatal error, give it its own
exception class and an ordered-first CLI arm — never a `benign: bool` flag on the fatal class (the
CLI would have to branch on the flag, which is exactly the fragility the one-class-per-module
convention exists to avoid). Mirror the order-dependent except arms already used in
`pipeline._collect_all` (most-specific/most-benign first).

## 2026-07-03 — v2-002-cron-scheduler: fcntl.flock(LOCK_EX|LOCK_NB) is the stale-lock-free single-instance primitive on Unix

For a single-host single-operator lock, `fcntl.flock` on a dedicated advisory file beats a pidfile:
the kernel auto-releases the fd on process death (incl. `kill -9`), so there is NO staleness
heuristic to get wrong (no pid-alive check, no mtime timeout). `LOCK_NB` (non-blocking) is
load-bearing — it turns "lock held" into an immediate `BlockingIOError` (→ benign skip) instead of a
silent block. Derive the lock path from an existing `Config` path's parent (`state_path.parent`)
rather than adding a `Config.lock_path` field — upholds the scheduler-cli-7 ADR-002 derive-don't-add
discipline. Wrap it in a context manager with `LOCK_UN`+close in `finally` (explicit release matters
for long-lived test processes even though the kernel would free it). Accepted tradeoff: Unix-only,
which matches "OS cron = Unix" scope.

## 2026-07-03 — v2-002-cron-scheduler: for secret-in-generated-artifact risk, add ONE reused runtime backstop, not just tests

When multiple generators (crontab line + Actions YAML) could each leak a secret, a single shared
`assert_no_secret(text, secret_values)` called at the end of every generator is a defense-in-depth
backstop: generators still reference `.env`/`${{ secrets.* }}` by construction, but a future edit
that regresses is caught at runtime, not only in CI. One function → one focused test (feed a real
env token, assert no substring in any output) covering the hardest surface (YAML). Prefer this to
"tests only" (a regression ships if the test isn't updated) or post-hoc redaction (masks the bug).
