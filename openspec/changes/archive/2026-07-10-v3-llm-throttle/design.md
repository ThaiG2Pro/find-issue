## Sketch — Gap Analysis

No critical gaps found. All 8 ACs (AC-V3-001-001..008) plus the MODIFIED AC-4-010 are
fully specified in `specs/summarizer/spec.md`; the change is confined to one adapter
(`src/osspulse/summarizer/client.py`) + its config (`src/osspulse/summarizer/config.py`),
touches no port signature, and adds no dependency. Scope is `tiny`.

Two reconciliations recorded (not gaps):
- **Retry-After default**: the S3 kickoff note said "default 10s" but the approved spec
  (AC-V3-001-007) requires **exponential backoff when `Retry-After` is absent**. The spec
  wins — no fixed 10s default. `Retry-After`, when present, sets the *minimum* wait
  (ADR-005).
- **openapi.yaml**: N/A. OSS Pulse is a CLI tool with no HTTP API (see
  `context/conventions.md`); no prior change ships an `openapi.yaml`. R5/R9 (OpenAPI) do
  not apply. The pipeline stage contract is plain Python method calls — the only "API" here
  is the unchanged `LLMClient` Protocol.

## Context

On Groq's free tier (6000 tokens/min) a run over ~12 items floods the provider: every item
hits `RateLimitError`, is caught by `summarize_items`' skip-log-continue, and is dropped —
so the digest comes back nearly empty. Summaries are also English-only. This CR makes the
summarizer (S4) pace itself under a per-minute token budget, retry on 429 before skipping,
and emit Vietnamese summaries. Boundary invariants preserved: pure LLM+cache I/O
(AC-4-021), no secret in logs (AC-4-012), only title+body egress (RF-1).

## Goals / Non-Goals

**Goals:**
- Pace LLM calls under a configurable per-minute token budget via an in-memory 60s sliding
  window (AC-V3-001-001..004).
- Append the exact instruction `Trả lời bằng tiếng Việt.` to the prompt (AC-V3-001-005).
- Retry a 429 with backoff (max 3, honoring `Retry-After`) before falling back to the
  existing skip-log-continue (AC-V3-001-006..008; MODIFIES AC-4-010).

**Non-Goals:**
- No daily-budget (500k/day) tracking, no cross-run persistence — throttle is run-scoped.
- No `LLMClient` Protocol / pipeline signature change; `pipeline.py` untouched.
- No provider-side token counting (tiktoken) — token cost is read from `response.usage`.
- No change to cache-key, content-hash, or cache-aside logic.

## Architecture Overview

Single adapter (`LiteLLMSummarizer`) gains one collaborator — an in-memory `TokenWindow` —
and two injected callables (`sleep`, `clock`) for testability. Data flow inside
`summarize(item)` is unchanged up to the LLM call; the throttle wraps *only* the real
completion (after cache-hit and empty-item short-circuits, so cache hits/skips are never
counted — AC-V3-001-004). Retry wraps the same completion call.

```
summarize(item):
  prepare → empty? → _SkipItem            (no window touch)
  cache hit? → return                     (no window touch)
  window.sleep_if_needed()                # AC-V3-001-001/002
  response = _call_with_retry(...)        # AC-V3-001-006/007/008
  window.record(usage.total_tokens or 0)  # AC-V3-001-003
  normalize → cache set → return
```

Dependency direction unchanged: adapter → (models, ports, summarizer.*, litellm, stdlib
`time`). No new import class (AC-4-021 preserved).

## Decisions

### ADR-001 — Sliding window as `TokenWindow` holding `list[(timestamp, tokens)]`

**Context**: Need a 60s record of per-call `total_tokens` to decide when to sleep
(AC-V3-001-001/002). Must prune expired entries and sum the live ones.

| Option | Pros | Cons |
|---|---|---|
| **A. `list[(ts, tokens)]`, prune-on-access** | trivial, exact per-call granularity, easy to test | O(n) prune per call — n is tiny (≤ items/min) |
| B. Single running sum + reset timer | O(1) | coarse — can't expire individual calls inside the window; over/under-sleeps |
| C. `collections.deque` | O(1) popleft | same shape as A with marginal gain at this scale; less obvious to read |

**Decision**: **A** — a dedicated `TokenWindow` class in `client.py` holding
`list[tuple[float, int]]`. At OSS Pulse's scale (single operator, sequential batch, a
handful of calls/min) O(n) prune is free and the per-entry expiry is what makes the sleep
math correct.

**Consequences**: One small pure class, fully unit-testable with an injected clock. No new
module/file.

### ADR-002 — Sleep computed as "time until enough headroom frees", looped

**Context**: When recorded window tokens meet/exceed `tokens_per_minute`, sleep "until the
oldest entries fall outside the window" (spec). Must not undershoot.

| Option | Pros | Cons |
|---|---|---|
| **A. Loop: sleep until oldest entry expires, re-prune, re-check** | correct for any budget/entry mix; converges | may sleep in ≥1 hops |
| B. Sleep a flat `window_seconds` | simple | over-sleeps grossly; stalls the run (RF-2) |

**Decision**: **A** — `sleep_if_needed()` prunes, and while `sum(tokens) >= budget` it
sleeps `window_seconds - (now - oldest_ts)` (min a tiny epsilon), re-prunes, re-checks.
Best-effort: a single item whose own tokens exceed the budget still makes exactly one call
(cannot summarize in <1 call) — the guard is on *already-recorded* tokens, never a hard
block (proposal Edge Case 2).

**Consequences**: Bounded, minimal sleeping. Correct under mixed entry sizes.

### ADR-003 — Inject `sleep` and `clock` callables (default `time.sleep`/`time.monotonic`)

**Context**: The retry loop and throttle both sleep. The existing test
`test_llm_rate_limit_item_skipped_AC_4_010` raises `RateLimitError` on every attempt — with
real backoff it would sleep for seconds in the suite. New tests must assert *how long* was
slept without wall-clock waits.

**Decision** _(tiny — single reasonable approach)_: add `sleep: Callable[[float], None] =
time.sleep` and `clock: Callable[[], float] = time.monotonic` to `__init__`, threaded into
`TokenWindow` and `_call_with_retry`. Tests inject a fake that records durations and a
manually-advanced clock. Rationale: mirrors the existing `completion` injection pattern
(A-C8, stack.md) — no new abstraction, matches how this adapter is already tested.

**Consequences**: Deterministic, fast tests. The existing AC-4-010 test must inject a no-op
sleep (it now retries 3× before skipping) — flagged as a gotcha.

### ADR-004 — Vietnamese instruction appended to the system message

**Context**: AC-V3-001-005 requires the exact string `Trả lời bằng tiếng Việt.` in the
messages, without changing which item fields egress (title+body only — RF-1).

**Decision** _(tiny — single reasonable approach)_: append `Trả lời bằng tiếng Việt.` to
`system_content` in `_build_messages`. It is a static instruction, not item data, so RF-1
(only title+body of the item leave) is untouched. Placing it in `system` (not `user`) keeps
it out of the title/body content block and makes the RF-1 test assertion clean.

**Consequences**: One-line change; existing normalization contract (≤2 sentences) unchanged.

### ADR-005 — Retry-then-skip wraps the completion call; re-raise on exhaustion

**Context**: 429 must retry (max `max_retries`, honoring `Retry-After`) before skipping
(AC-V3-001-006/008; MODIFIES AC-4-010). All other errors still skip immediately (AC-4-010
unchanged for them).

| Option | Pros | Cons |
|---|---|---|
| **A. `_call_with_retry` around `_completion`; re-raise `RateLimitError` after N attempts** | existing `summarize_items` `except openai.APIError` handles the skip-log-continue unchanged — smallest diff; other errors untouched | retry logic co-located with the call |
| B. Move all error handling into a new retry+skip layer | centralizes | rewrites the working batch loop; risks AC-4-011/012 regressions |

**Decision**: **A** — a private `_call_with_retry` catches only `RateLimitError`
(litellm's, which subclasses `openai.APIStatusError`/`APIError`). Wait = `max(Retry-After,
exp_backoff(attempt))` when the header is present, else `exp_backoff(attempt)` (e.g.
`base * 2**attempt`). After `max_retries` it re-raises the `RateLimitError`, which
propagates to the *unchanged* `summarize_items` `except openai.APIError` branch →
skip-log-continue. Non-429 errors never enter the retry loop (they skip immediately as
today).

**`Retry-After` extraction** is defensive: litellm may not attach a `response`. Read via
`getattr(exc, "response", None)` → `getattr(response, "headers", None)` → `Retry-After`;
parse to float; on any absence/parse failure fall back to exp-backoff. Never let extraction
crash the run (mirrors the "missing usage ⇒ 0" best-effort stance).

**Consequences**: `summarize_items` and AC-4-011/012 behavior unchanged. The 429 path now
retries before the existing skip — exactly the AC-4-010 modification. Log lines in the
retry path carry item identity + error class only (AC-4-012).

## API Design
_(N/A — CLI tool, no HTTP API. The `LLMClient` Protocol `summarize(item) -> str` signature
is unchanged; `summarize_items` remains an adapter-only helper.)_

## DB Schema
_(unchanged — V1 state is a JSON file; this CR adds no persisted state, throttle is
in-memory per batch.)_

## Error Mapping

| Trigger | Handling | AC |
|---|---|---|
| `RateLimitError` (429), attempt < max | wait `max(Retry-After, backoff)`, retry | AC-V3-001-006/007 |
| `RateLimitError`, retries exhausted | re-raise → `summarize_items` skip-log-continue | AC-V3-001-008, AC-4-010 |
| Timeout / 4xx / 5xx (non-429) | skip immediately (unchanged) | AC-4-009/010 |
| `response.usage` None / no `total_tokens` | record 0, continue | AC-V3-001-003 |
| `_SkipItem` (empty) / cache hit | no window touch, no sleep | AC-V3-001-004 |

## Sequence Flows

Covered in Architecture Overview pseudocode. Retry sub-flow: `attempt=0`; loop `_completion`
→ on `RateLimitError`: if `attempt == max_retries` re-raise; else `sleep(wait); attempt+=1`.

## Edge Cases

1. Single item's tokens > budget → still makes one call (best-effort, not a hard block).
2. `usage` absent/None → 0 tokens recorded, no crash (AC-V3-001-003).
3. Cache hit / empty item → window untouched, no sleep (AC-V3-001-004).
4. `Retry-After` present but malformed/negative → clamp to ≥0, fall back to backoff floor.
5. Retries exhausted → skip-log-continue, run not aborted, no secret logged (AC-V3-001-008).

## Performance

Sequential, single-threaded batch — no locking (proposal Edge Case 6). Prune is O(n) over a
tiny n. Intentional sleeps are the only latency, bounded by `max_retries` + best-effort
throttle math (RF-2). No memory growth: window entries expire within `window_seconds`.

## Security

No new surface. API key remains ctor-private, passed only to `litellm.completion` — never
logged/repr'd (AC-4-012/022, ADR-008 preserved). New throttle/retry log lines carry item
identity (repo/type/id) + error class only — no api_key, no prompt/body (AC-4-012). STRIDE
skipped: no auth/payment/PII/upload/admin/secret-handling change (proposal Early Risk Flags).

## Risk Assessment

- [Long stall from a large `Retry-After` or backoff] → bounded by `max_retries=3` + the
  header is honored as a *minimum*, not multiplied; best-effort throttle never hard-blocks.
- [Existing AC-4-010 test now sleeps during retries] → inject a no-op/recording `sleep` in
  tests (ADR-003); update that test to expect retries-then-skip.
- [Provider omits `usage`] → treated as 0 (AC-V3-001-003), throttle degrades gracefully.

## Implementation Guide

**Recommended order** (follows tasks.md 1→5, layered config → prompt → throttle → retry →
tests):
1. `src/osspulse/summarizer/config.py` — add `tokens_per_minute: int = 6000`,
   `throttle_window_seconds: float = 60.0`, `max_retries: int = 3`,
   `retry_backoff_base_seconds: float = 1.0` to `SummarizerConfig` (frozen dataclass).
2. `client.py` `_build_messages` — append `Trả lời bằng tiếng Việt.` to `system_content`
   (ADR-004).
3. `client.py` — add `TokenWindow` class (ADR-001/002): `record(tokens)`, `_prune()`,
   `sleep_if_needed()`, using the injected `clock`/`sleep`.
4. `client.py` `__init__` — inject `sleep=time.sleep`, `clock=time.monotonic`; instantiate
   `TokenWindow` per adapter (per-batch scope). In `summarize`: call `sleep_if_needed()`
   right before the completion (after cache-miss + non-empty guards), and `record(...)`
   right after (reading `getattr(response.usage, "total_tokens", 0) or 0`, guarding a None
   `usage`).
5. `client.py` — add `_call_with_retry` (ADR-005) wrapping `self._completion(...)`; call it
   from `summarize`. Keep `summarize_items` untouched.
6. `tests/test_summarizer_client.py` — add the 8 unit tests (task 5.1). **Update the
   existing `test_llm_rate_limit_item_skipped_AC_4_010`** to inject a no-op `sleep` and
   expect 3 attempts then skip.

**Patterns to follow**:
- Injection mirrors the existing `completion=` ctor param (`client.py.__init__`).
- Best-effort/defensive reads mirror `_cache_get`/`_cache_set` (`getattr` + fallback, never
  crash) — apply the same to `usage` and `Retry-After`.
- Log with `_identity(item)` only (existing helper) — never format the key/prompt.

**Gotchas**:
- Call `sleep_if_needed()` / `record()` ONLY on the real-completion path — cache hits and
  `_SkipItem` must bypass both (AC-V3-001-004). This is guaranteed by placing them after the
  cache-hit `return` and the empty-item `raise _SkipItem`.
- `TokenWindow` is instance state on the adapter → run/batch-scoped, not persisted
  (AC-V3-001-002). A fresh adapter = fresh window.
- litellm's `RateLimitError` may have no `.response`; extraction must not assume it (ADR-005).
- Tests MUST inject `sleep` — otherwise the suite sleeps for real backoff seconds.
