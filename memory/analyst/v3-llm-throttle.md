# analyst memory — v3-llm-throttle

## 2026-07-11 — v3-llm-throttle: a "just add throttling/retry" CR to a graceful-skip summarizer must MODIFY the existing skip-on-429 requirement, not only ADD

The summarizer already caught 429 and skipped-log-continued (AC-4-010). Adding retry means
429 no longer skips *immediately* — so the change is a MODIFIED requirement on AC-4-010, not a
pure ADD. Pure-ADD would leave two contradictory specs (skip-now vs retry-then-skip). Split the
error handling in the modified text: 429 = retry-then-skip, all other errors (timeout/4xx/5xx) =
skip immediately.

Two more traps this ask hid that the raw requirement never mentioned:
- The token window must EXCLUDE cache hits and empty-item skips (no LLM call ⇒ no tokens) — else
  the throttle sleeps on phantom cost.
- `response.usage` can be None/absent (some providers, and most test mocks) — spec it as 0 tokens,
  best-effort, never a crash. Otherwise adding throttle turns a working run into a crash on a mock.
