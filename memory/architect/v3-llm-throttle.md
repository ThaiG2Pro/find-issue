# architect memory — v3-llm-throttle

## 2026-07-11 — v3-llm-throttle: inject sleep+clock to keep retry/throttle tests wall-clock-free

Adding a retry/backoff or time-based throttle to an existing adapter silently breaks any
pre-existing "always-fails" error test (e.g. the 429-skip test now sleeps through N retries).
Two reusable moves: (1) inject `sleep=time.sleep` + `clock=time.monotonic` ctor params
(mirror the existing `completion=` injection) so delays are deterministic and instant in
tests; (2) call out in the handoff/tasks that the pre-existing error test MUST be updated to
inject a no-op sleep and expect retries-then-skip — otherwise the suite hangs and the
behavior-change (MODIFIED AC) looks like a regression.

## 2026-07-11 — v3-llm-throttle: time-based throttle window must sit AFTER the short-circuits

A per-call metering window (sleep_if_needed + record) must be placed after the cache-hit
`return` and the empty-item skip, so cache hits / skipped items are never counted or throttled
against. Enforce it structurally by placement (not a comment) — same class of invariant as
"ordering of two methods sharing cached state" from v2-001.
