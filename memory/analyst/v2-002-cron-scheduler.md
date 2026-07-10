## 2026-07-03 — v2-002-cron-scheduler: for a "run on a schedule" feature in a single-shot CLI, the scope trap is building a daemon
The obvious reading of "chạy theo cron/scheduler" is an in-process scheduler (APScheduler loop /
systemd service). For a lean single-shot tool this is almost always wrong scope — PROJECT_SPEC §8
explicitly said "Không cần service chạy nền phức tạp" and pinned OS cron as primary. The correct
S1 framing is **generate-and-delegate**: a `schedule` command that emits a crontab line / CI workflow,
and the OS/CI owns the timer. Watch for this whenever a requirement says "run periodically" — clarify
daemon-vs-delegate BEFORE writing ACs, because the two produce completely different specs.

## 2026-07-03 — v2-002-cron-scheduler: "run on a schedule" implicitly requires a concurrency lock + secretless-artifact ACs that the raw requirement never mentions
Two requirements are always latent in a scheduling feature and are easy to miss at S1:
(1) **Overlap safety** — a cadence faster than the run duration will fire a second process that races
shared mutable state (here the JSON state file's load→mark_seen→save). Add a single-instance lock AC
+ a benign-skip (exit 0) decision, and an auto-release-on-crash AC to avoid stale-lock deadlock.
(2) **Secretless generated artifacts** — any generated crontab/CI-workflow that touches auth must
reference env/.env or the repo secrets store, never inline the token (a committed workflow with an
inlined token leaks it). Add a "no secret substring in generated output" AC. Both come straight out
of a quick STRIDE pass (DoS + Information disclosure) even for a "small" feature.

## 2026-07-03 — v2-002-cron-scheduler: cron TZ semantics differ by backend — spec it, don't assume
OS cron evaluates in the system local timezone; GitHub Actions `schedule.cron` evaluates in UTC. If a
feature can generate both, a single "daily 08:00" intent silently means two different wall-clock times.
Keep an explicit AC that the generated artifact documents its own TZ, so the off-by-hours bug is caught
at spec time rather than by a confused operator.
