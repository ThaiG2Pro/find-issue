## 2026-07-14 — discord-retry: retry-budget URL-secrecy check pattern

When a delivery adapter gains a retry loop, the URL-secrecy test must explicitly target the
**post-retry exhaustion** path — not just the single-attempt failure. Two dedicated tests are
the minimum: one via HTTP status exhaustion (`max_retries=N`, all transient responses) and one
via exception exhaustion (TimeoutException). Each test must assert both the full URL AND the
token substring are absent from the final `DeliveryError`. A single pre-retry URL-leak test does
not catch a regression where the retry loop appends diagnostic info from `str(exc)` on the final
raise.

## 2026-07-14 — discord-retry: backoff formula pin test pattern

Pinning the exact sleep call sequence (`sleep_calls == [1.0, 2.0, 4.0]`) is more valuable than
asserting monotonic growth, because it catches both off-by-one on `attempt` index AND a wrong
base. A lambda that appends to a list (`lambda s: calls.append(s)`) is cleaner than a MagicMock
for sequence-order assertions. Also: `Retry-After` header test must assert the exact sleep value
`max(header, backoff)` — `assert_called_once_with(5.0)` — not just "sleep was called".

## 2026-07-14 — discord-retry: shared helper eliminates retry-logic drift risk

When two delivery paths (plain-text POST and embed POST) share a retry loop via a single
`_do_post_with_retry` helper, the QA test burden for the second path is just parity (one
retry-then-success + one URL-secrecy test). The exhaustion/backoff-growth tests only need to
run against one path. If the paths ever diverge (separate loops), the full test matrix must
double — use this as a signal to push back on any design that forks the retry loop.
