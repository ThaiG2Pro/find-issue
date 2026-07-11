## Why

On Groq's free tier (6000 tokens/min, 500k tokens/day) a run over ~12 items floods the
provider: every item hits a `RateLimitError`, is caught by the batch loop, and is skipped —
so the digest comes back nearly empty. Summaries are also currently English-only. This CR
makes the summarizer pace itself under the per-minute token budget, retry instead of skip on
rate limits, and emit Vietnamese summaries.

## What Changes

- **Token-aware throttle** — after each LLM completion the summarizer reads
  `response.usage.total_tokens`, records it in a 60-second sliding window, and sleeps before
  the next call when the window is near the per-minute token budget (default 6000).
- **Vietnamese summaries** — the prompt gains the instruction `Trả lời bằng tiếng Việt.` so
  summaries are returned in Vietnamese. Only `title`+`body` are still sent (RF-1 unchanged).
- **Retry-then-skip on rate limit** (bonus) — `RateLimitError` now triggers exponential
  backoff (max 3 retries, honoring a `Retry-After` header when present) BEFORE falling back to
  the existing skip-log-continue. This **MODIFIES** the current "skip immediately on 429"
  behavior of AC-4-010.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `summarizer`: adds a per-minute token throttle and Vietnamese prompt instruction, and
  changes 429 handling from skip-immediately to retry-with-backoff-then-skip.

## Impact

- Code: `src/osspulse/summarizer/client.py` (prompt build, batch loop, new throttle helper),
  `src/osspulse/summarizer/config.py` (new tunables: per-minute token budget, window seconds,
  max retries). No pipeline signature change; `src/osspulse/pipeline.py` unaffected.
- Dependencies: none new (uses stdlib `time`; reads `usage` off the existing LiteLLM response).
- Boundary invariants preserved: pure LLM+cache I/O (AC-4-021), no secret in logs (AC-4-012),
  only title+body egress (RF-1).

## Assumptions

- [CONFIRMED] Groq free-tier limit is 6000 tokens/min; the throttle budget is configurable and
  defaults to a safety margin under 6000.
- [CONFIRMED] `response.usage.total_tokens` is available on the LiteLLM/Groq completion response.
- [ASSUMED] When `usage` is absent/None (some providers/mocks omit it), the item's token cost is
  treated as 0 for the window rather than crashing — throttle stays best-effort.
- [ASSUMED] The throttle is run-scoped and in-memory (one batch of `summarize_items`); it is NOT
  persisted across runs. The daily 500k budget is out of scope (see Non-Goals).
- [CONFIRMED] Vietnamese instruction text is exactly `Trả lời bằng tiếng Việt.`.

## Non-Goals

- No daily (500k tokens/day) budget tracking or cross-run persistence — this CR only paces the
  per-minute window within a single run.
- No change to the cache-key, content-hash, or cache-aside logic.
- No change to the `LLMClient` Protocol signature or the pipeline wiring.
- No provider-specific token counting (tiktoken etc.) — token cost is read from the response's
  reported `usage`, not pre-computed.

## Edge Cases

Scope is `tiny`; the categories that genuinely apply:

1. **Data integrity** — `response.usage` is `None` or missing `total_tokens`: record 0, do not
   crash (AC-V3-001-003).
2. **Input boundary** — a single item's tokens alone exceed the per-minute budget: the call is
   still made once (cannot summarize in <1 call); throttle is best-effort, never a hard block.
3. **State transition** — cache hit or fully-empty-item skip makes no LLM call: nothing is added
   to the window and no sleep is triggered (AC-V3-001-004).
4. **Integration** — `RateLimitError` with a `Retry-After` header: honor the header delay; when
   absent, use exponential backoff (AC-V3-001-006/007).
5. **Integration** — retries exhausted after 3 attempts: fall back to skip-log-continue, run not
   aborted, no secret logged (AC-V3-001-008).
6. **Concurrency** — the sliding window is single-threaded within one batch loop; no locking
   needed (the summarizer processes items sequentially).

## Early Risk Flags

- STRIDE not run: this change touches no auth/payment/PII/token-secret/upload/admin surface. The
  LLM API key handling is unchanged (still ctor-only, never logged — AC-4-012/022 preserved).
- Availability (RF-2): a mis-set/too-large `Retry-After` or a long backoff could stall a run; the
  max-3-retries cap and best-effort throttle bound the delay.

Figma: N/A
