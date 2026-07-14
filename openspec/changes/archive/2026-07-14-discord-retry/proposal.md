## Why

`DiscordDelivery` currently fails the whole run on the FIRST POST error of any kind —
a 429 rate-limit, a transient 5xx, or a momentary network blip aborts delivery with a
`DeliveryError` even though a retry moments later would very likely succeed. Discord
routinely returns 429 with a `Retry-After` header and occasional 5xx; treating these as
permanent makes delivery brittle. This change adds bounded retry + exponential backoff for
**transient** failures while keeping **non-transient** 4xx (bad request / auth / not found)
fatal-on-first-error as today. Nothing else in the pipeline changes.

## What Changes

- `DiscordDelivery.__init__` gains three injected, defaulted params:
  `max_retries: int = 3`, `backoff_base: float = 1.0`, `sleep: Callable[[float], None] = time.sleep`.
  `sleep` is injected purely so tests can assert wait behavior without real delays.
- Both low-level POST methods (`_post_one` plain text and `_post_one_embed`) retry on a
  **transient** failure and re-raise `DeliveryError` only once retries are exhausted.
- **Transient** (retried): HTTP `429`, any HTTP `5xx`, `httpx.TimeoutException`,
  `httpx.RequestError` (connection/DNS/network).
- **Non-transient** (fail immediately, unchanged): HTTP `4xx` other than 429
  (`400`, `401`, `403`, `404`, …) — no retry, no sleep.
- Wait before each retry = `backoff_base * 2**attempt` (exponential, attempt starting at 0).
  When a `Retry-After` header is present and numeric, wait = `max(Retry-After, backoff_base * 2**attempt)`.
- Total attempts = `max_retries + 1` (one initial + up to `max_retries` retries). `max_retries = 0`
  reproduces today's single-attempt, fail-immediately behavior.
- On success at any attempt, `deliver()` returns normally. The webhook URL still NEVER appears
  in the final `DeliveryError` (AC-V2-005-011 preserved).

## Capabilities

### New Capabilities
- _(none)_

### Modified Capabilities
- `delivery`: adds bounded retry + exponential backoff to the existing `DiscordDelivery`
  adapter. **MODIFIES** the "Discord push failure is fatal with a clear CLI error"
  requirement (a transient failure is no longer fatal-on-first-error — it is retried, and
  only fatal after retries are exhausted; non-transient 4xx stays fatal immediately) and the
  "Embed delivery failure stays fatal without leaking the webhook URL" requirement (same
  retry semantics apply to embed POSTs). **ADDS** a "Discord delivery retries transient
  failures with exponential backoff" requirement describing the classification, backoff, and
  `Retry-After` handling. All file/stdout, splitting, and embed-formatting behavior is unchanged.

## Impact

- Code: `src/osspulse/delivery/discord_delivery.py` (constructor params + a retry wrapper
  around the existing per-attempt POST/classify logic in `_post_one` and `_post_one_embed`).
  Pipeline wiring (`cli.py`/pipeline) MAY pass the new params but they are defaulted, so the
  call site can stay unchanged (backward compatible).
- Tests: `tests/delivery/test_discord_delivery.py` — existing 429/500 tests that expect an
  immediate `DeliveryError` MUST be updated to expect retry-then-error (inject
  `max_retries` + a fake `sleep`); new tests for backoff/`Retry-After`/transient
  classification. Module scope (`test_scope = module`).
- No new dependencies (`httpx` and stdlib `time` already present).
- No API, no schema, no config-surface change (params are constructor-level with defaults;
  no new config key is required for this change). No new security surface — the webhook URL
  is still env-resolved + allowlisted and never leaked in errors.

## Out of Scope

- No new config key for retry tuning — `max_retries`/`backoff_base`/`sleep` stay constructor
  params with defaults (a `[discord] max_retries` config surface can be a later change).
- No retry for `FileDelivery`/`StdoutDelivery` — this change is Discord-webhook-only.
- No jitter / full-jitter randomization on the backoff (deterministic backoff only for now).
- No cap on an oversized `Retry-After` value (accepted for a single-operator CLI; flagged as a
  risk for the architect to note).
- No de-duplication of at-least-once re-delivery (a retry after a lost-response POST may deliver
  twice; webhooks have no dedupe — unchanged, out of scope).
- No circuit-breaker / cross-run backoff state.

## Assumptions

- **[CONFIRMED]** Transient set = `{429, 5xx, httpx.TimeoutException, httpx.RequestError}`;
  everything else non-2xx (4xx except 429) is non-transient and fails immediately. (User goal.)
- **[CONFIRMED]** Retry wait = `max(Retry-After, backoff_base * 2**attempt)` when a numeric
  `Retry-After` is present, else `backoff_base * 2**attempt`. (User goal.)
- **[CONFIRMED]** Constructor gains `max_retries: int = 3`, `backoff_base: float = 1.0`,
  `sleep: Callable = time.sleep`; `sleep` injected for testability. (User goal.)
- **[ASSUMED]** `attempt` in the backoff formula starts at `0` for the first wait, so waits are
  `backoff_base·1, backoff_base·2, backoff_base·4, …` — the natural reading of
  `backoff_base * 2**attempt`. Architect/dev may pin the exact indexing; the AC pins the
  formula and monotonic growth, not a specific first-wait constant beyond `backoff_base`.
- **[ASSUMED]** `Retry-After` is read from the response header as seconds (integer/float form,
  Discord's format). A missing, empty, or non-numeric `Retry-After` is ignored and the pure
  backoff formula is used (never crash on a malformed header).
- **[ASSUMED]** Retry is **per POST** (per split message / per embed batch). In a multi-message
  push, each message gets its own independent retry budget; there is no rollback of
  already-delivered messages (existing no-rollback semantics preserved, BR-V2-005-004).
- **[ASSUMED]** `sleep` is only called *between* attempts, never after the final failed attempt
  (no pointless trailing sleep before raising).

## Edge Cases

_(scope=tiny — the categories that genuinely apply)_

1. **State transition — success on a retry**: attempt 1 gets 503, attempt 2 gets 204 → `deliver()`
   returns normally, `sleep` called exactly once (AC-001-001/007).
2. **Boundary — retries exhausted**: every attempt returns 500 with `max_retries = 3` →
   4 total attempts, `sleep` called 3 times, then `DeliveryError` (AC-001-002).
3. **Classification — non-transient 4xx**: a `403` (or `400/401/404`) → immediate `DeliveryError`,
   `sleep` NOT called, only one POST (AC-001-004).
4. **Data integrity — Retry-After honored**: `429` with `Retry-After: 5` and `backoff_base·2**0 = 1`
   → wait is `max(5, 1) = 5` (AC-001-006).
5. **Data integrity — Retry-After absent/malformed**: `429` with no/garbage `Retry-After` →
   fall back to `backoff_base * 2**attempt`, never crash (AC-001-006).
6. **Boundary — `max_retries = 0`**: single attempt, transient failure fails immediately with no
   sleep — reproduces pre-change behavior (AC-001-011).
7. **Integration — timeout/network on every attempt**: `TimeoutException`/`RequestError` on all
   attempts → retried, then `DeliveryError`, webhook URL not leaked (AC-001-003/010).
8. **Parity — embed mode**: `_post_one_embed` retries transient failures identically to
   `_post_one` (AC-001-008).
9. **Integration — multi-message**: message 2's transient failure is retried on its own budget;
   message 1 already delivered is not rolled back (AC-001-009, BR-V2-005-004 preserved).

## Early Risk Flags

- **T1 (URL leak) — preserved**: the retry wrapper must build the final `DeliveryError` from
  status codes / exception *type names* only, exactly like the current code — never `str(exc)`
  / `repr(request)`, which embed the URL (AC-V2-005-011 / AC-001-010).
- **T4 (DoS via hang) — bounded**: retries are bounded by `max_retries`; each attempt keeps the
  existing explicit request timeout, so total time is bounded (`max_retries+1` attempts ×
  timeout + Σ backoff waits). A hostile/huge `Retry-After` could still stall — acceptable for a
  single-operator CLI, but the architect should note whether to cap it.
- **Idempotency — unaffected**: retry does not re-split or re-render; it re-POSTs the same
  message. Delivery has no dedupe, so a message that Discord accepted but whose response was lost
  could be delivered twice on a retry — a known, accepted at-least-once property of webhooks
  (out of scope to fix here).
- STRIDE full threat-model NOT run: this change adds no new trust boundary, secret, or input
  source — it only adds bounded retry to the already-validated, allowlisted webhook POST.
  Security-relevant behavior (URL secrecy, timeout, allowlist) is inherited unchanged from
  v2-005-push-delivery.

Figma: N/A (CLI tool; Discord renders any visuals server-side).

## _Structured Extract

```yaml
change: discord-retry
ticket_id: "001"
scope: tiny
rigor: lite
capability: delivery
requirements_added: 1
requirements_modified: 2
acs:
  new: [AC-001-001, AC-001-002, AC-001-003, AC-001-004, AC-001-005, AC-001-006, AC-001-007, AC-001-008, AC-001-009, AC-001-010, AC-001-011]
  modified: [AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V4-001-007]
business_rules: [BR-001-001, BR-001-002, BR-001-003, BR-001-004]
integration_points: []
transient_errors: [HTTP-429, HTTP-5xx, httpx.TimeoutException, httpx.RequestError]
non_transient_errors: [HTTP-400, HTTP-401, HTTP-403, HTTP-404]
new_constructor_params:
  max_retries: {type: int, default: 3}
  backoff_base: {type: float, default: 1.0}
  sleep: {type: "Callable[[float], None]", default: time.sleep}
backoff_formula: "max(Retry-After, backoff_base * 2**attempt) if numeric Retry-After else backoff_base * 2**attempt"
touches: [auth: false, payment: false, pii: false]
figma: N/A
edge_cases: 9
```
