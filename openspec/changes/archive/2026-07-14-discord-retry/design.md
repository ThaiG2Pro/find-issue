## Sketch — Gap Analysis

**No critical gaps found.** The spec deltas pin the full contract: the transient/non-transient
classification (BR-001-001), the backoff formula (BR-001-003), the three new constructor params,
and the URL-secrecy invariant (AC-001-010 / AC-V2-005-011). The current
`src/osspulse/delivery/discord_delivery.py` already builds every `DeliveryError` from status
codes / exception *type names* only — the retry refactor must preserve that.

Sketch:
- **Touched file (1):** `src/osspulse/delivery/discord_delivery.py` — constructor + a new shared
  retry helper wrapping the existing per-attempt POST/classify/raise logic; `_post_one` and
  `_post_one_embed` refactored to call it.
- **Endpoints:** none (CLI tool; outbound Discord webhook POST only). **DB tables:** none.
- **Key flows:** (1) transient failure → backoff → retry → success/exhaust; (2) non-transient
  4xx → immediate `DeliveryError`; (3) `Retry-After` floor via `max(...)`.

Minor items pinned as decisions (not gaps): `attempt` index starts at `0` (ASSUMED in S2,
consistent with the AC-001-006 example where `backoff_base=1.0` gives first-retry wait `1.0`);
`sleep` is called only *between* attempts, never after the final failed one.

## Context

`DiscordDelivery.deliver()` splits a digest and POSTs each chunk (plain text via `_post_one`, or
embed batches via `_post_one_embed`). Today **any** POST error — a transient `429`/`5xx`/network
blip or a permanent `4xx` — raises `DeliveryError` on the first attempt, aborting the run. Discord
routinely returns `429` (+`Retry-After`) and occasional `5xx`; a retry moments later usually
succeeds. This change adds bounded retry + exponential backoff for **transient** failures while
keeping **non-transient** `4xx` fatal-on-first-error. It touches one file and adds no dependency
(`httpx` + stdlib `time` already present).

Constraints inherited from v2-005-push-delivery (unchanged): webhook URL never appears in any
error (T1); each attempt keeps an explicit request timeout; multi-message push has no rollback.

## Goals / Non-Goals

**Goals:**
- Retry transient failures (`429` / `5xx` / `httpx.TimeoutException` / `httpx.RequestError`) with
  exponential backoff, `Retry-After`-floored, up to `max_retries` retries (AC-001-001..003,005..007).
- Non-transient `4xx`≠`429` stays fatal on the first attempt, no sleep (AC-001-004).
- One shared retry loop for plain-text AND embed POSTs so the two paths cannot drift (AC-001-008).
- Preserve URL secrecy in the final `DeliveryError` after retries (AC-001-010, AC-V2-005-011).
- Backward compatible: new params are defaulted; `max_retries=0` reproduces today's behavior
  (AC-001-011).

**Non-Goals:** no config-key surface for retry tuning; no retry for File/Stdout delivery; no
jitter; no `Retry-After` cap; no de-dup of at-least-once re-delivery; no circuit-breaker. (Per
proposal §Out of Scope.)

## Architecture Overview

Ports/adapters, delivery layer only. No new module, no new import, no cross-stage coupling. The
change is internal to the `DiscordDelivery` adapter: a new private method `_do_post_with_retry`
owns the attempt loop; `_post_one` and `_post_one_embed` become thin callers that supply (a) the
JSON body and (b) an error-label prefix. `deliver()`, `_post_all`, `_post_embed_batches`, all
parsing/splitting/embed-building helpers are unchanged. Retry is **per POST** — the loop lives
below `_post_all`/`_post_embed_batches`, so each split message / embed batch gets its own budget
and already-delivered POSTs are never rolled back (BR-001-004, BR-V2-005-004 preserved).

## ADRs

### ADR-001: One shared `_do_post_with_retry` helper for both POST paths

**Context:** `_post_one` (plain text, `{"content": msg}`) and `_post_one_embed` (embed batch,
`{"embeds": [...]}`) today duplicate the same try/except/status-check structure with different
JSON bodies and error-label wording. Retry + backoff + classification must apply identically to
both (AC-001-008 tests embed parity). Duplicating the retry loop in two places risks drift — a
recurring failure mode flagged in the S2 handoff §4.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. Single `_do_post_with_retry(client, *, json_body, noun, unit, index, total)` helper; `_post_one`/`_post_one_embed` call it** | One place owns classify + backoff + URL-safe error; no drift; smallest change | Slightly more parameters to thread the two error-message shapes |
| B. Duplicate the retry loop inside each of `_post_one` / `_post_one_embed` | Each method self-contained | Two copies of the classify/backoff logic — exactly the drift the handoff warns against |
| C. Decorator `@with_retry` on the two methods | Reads cleanly | Decorator can't see per-attempt `Retry-After`/status to compute the wait without leaking classification back out; over-engineered for one adapter |

**Decision:** **Option A.** A single helper takes the JSON body plus the two label fragments
(`noun` = `"discord delivery"` / `"discord embed delivery"`, `unit` = `"message"` / `"batch"`) and
runs the whole attempt loop. Both callers shrink to a one-line delegation. This matches the
cross-spec lesson (v2-006-discussions: "parameterize the one retry helper, don't fork a parallel
path").

**Consequences:** classification, backoff, `sleep` placement, and URL-safe error construction
exist exactly once. The two callers only differ in `json_body`/labels. Existing error-message
wording (`"discord delivery failed: HTTP {code} (message {i}/{n})"` etc.) is preserved so
current URL-secrecy assertions keep passing.

### ADR-002: Backoff wait = `max(Retry-After, backoff_base * 2**attempt)`, `attempt` from 0

**Context:** BR-001-003 pins the wait formula and `Retry-After` flooring. Two sub-decisions need
nailing: the `attempt` index base, and how `Retry-After` is parsed from an untrusted response.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. `attempt` starts at 0 → waits `base·1, base·2, base·4…`; `Retry-After` parsed as float seconds, `max()`-floored, malformed ignored** | Matches AC-001-006 example (first-retry wait = `backoff_base` = `1.0`); guards untrusted header per conventions | — |
| B. `attempt` starts at 1 → first wait `base·2` | — | Contradicts the AC-001-006 worked example (`max(5, 1.0)`) |
| C. Trust `Retry-After` blindly / crash on non-numeric | Simpler | Violates BR-001-003 "never crash on malformed header"; untrusted-data convention |

**Decision:** **Option A.** Compute `backoff = backoff_base * 2 ** attempt` with `attempt`
starting at `0`. Read `Retry-After` from the failing response header; if it parses as a finite
number, wait `max(retry_after, backoff)`, else use `backoff`. `sleep` is called only before a
retry, never after the final failed attempt.

**Consequences:** deterministic, monotonic-non-decreasing waits (`1,2,4,…` for `base=1.0`)
satisfying AC-001-007; a garbage `Retry-After` degrades to pure backoff without crashing
(AC-001-005b). Only relevant on a response-carrying failure (`429`/`5xx`); exception failures
(timeout/network) have no response and always use pure backoff.

## API Design

_(unchanged — no HTTP API; this is a CLI tool. Only the internal `DiscordDelivery` constructor
signature gains three defaulted params: `max_retries: int = 3`, `backoff_base: float = 1.0`,
`sleep: Callable[[float], None] = time.sleep`. Call sites need no change — backward compatible.)_

## DB Schema

_(unchanged — no database; state is a JSON file and this change touches neither.)_

## Error Mapping

| Failure at a single POST attempt | Transient? | Behavior | `DeliveryError` message source | AC |
|---|---|---|---|---|
| HTTP `429` | yes | retry w/ backoff, `Retry-After` floor; fatal after budget | `HTTP {code}` | AC-001-006, AC-V2-005-008 |
| HTTP `5xx` (500/502/503…) | yes | retry w/ backoff; fatal after budget | `HTTP {code}` | AC-001-001,002 |
| `httpx.TimeoutException` | yes | retry; fatal after budget → "timed out after {timeout}s" | exception → `"timed out after {timeout}s"` | AC-001-003, AC-V2-005-010 |
| `httpx.RequestError` (Connect/DNS/Network) | yes | retry; fatal after budget | `type(exc).__name__` | AC-001-005, AC-V2-005-009 |
| HTTP `4xx` ≠ `429` (400/401/403/404) | **no** | **immediate** `DeliveryError`, no sleep | `HTTP {code}` | AC-001-004, AC-V2-005-008 |

Every message is composed from status code / exception **type name** only — never `str(exc)` or
`repr(request)` (T1, AC-001-010, AC-V2-005-011). `max_retries=0` → single attempt, no sleep,
fatal immediately even for a transient failure (AC-001-011).

## Sequence Flows

**Per POST (`_do_post_with_retry`):**
```
attempt = 0
loop:
  try response = client.post(url, json=json_body, timeout=timeout)
  except TimeoutException/RequestError as exc:   # transient, no response
     transient = True; retry_after = None; build exc-based error
  else:
     if 2xx: return  (success)
     transient = (status == 429 or 500 <= status <= 599)
     retry_after = parse(response.headers["Retry-After"])  # numeric-or-None
     build status-based error
  if transient and attempt < max_retries:
     wait = max(retry_after, backoff_base*2**attempt) if retry_after else backoff_base*2**attempt
     sleep(wait); attempt += 1; continue
  raise DeliveryError(error)   # non-transient, or budget exhausted
```
Success on retry → `sleep` called `attempt` times (AC-001-001/007). Exhausted → `sleep` called
`max_retries` times then raise (AC-001-002/003). Non-transient → 0 sleeps, 1 POST (AC-001-004).

## Edge Cases

Covered by the 11 scenarios in the spec deltas; the ones that shape the code:
`max_retries=0` (single attempt, no sleep, AC-001-011); malformed/absent `Retry-After` → pure
backoff, no crash (AC-001-005b); embed parity (AC-001-008); per-message budget in a multi-message
push, no rollback (AC-001-009). No trailing sleep after the final failed attempt.

## Performance

Bounded: at most `max_retries + 1` attempts per POST × per-attempt request timeout + Σ backoff
waits. `sleep` is injected so tests run at zero real delay. A hostile huge `Retry-After` is
accepted uncapped (single-operator CLI; noted as a risk, out of scope to cap — proposal §Out of Scope).

## Security

_(inherited unchanged from v2-005-push-delivery — no new trust boundary/secret/input.)_ The one
security-relevant invariant this change must not break: the final `DeliveryError` after retries is
built from status code / exception type name only, so the webhook URL never leaks (T1, AC-001-010,
AC-V2-005-011). No STRIDE re-run (proposal: no new surface).

## Risk Assessment

- **[T1 URL leak in final error]** → the shared helper builds error text exactly like the current
  code (status / type-name); new URL-leak tests assert the post-retry final error is clean.
- **[Drift between plain-text and embed retry]** → ADR-001 single helper; AC-001-008 embed-parity test.
- **[Existing `test_non_2xx_raises_delivery_error` breaks]** → it parametrizes `[400,401,404,429,500,503]`
  expecting an *immediate* error; `429/500/503` now retry. Split it (see Implementation Guide).
- **[Slow test suite from real backoff]** → inject a fake `sleep` (record calls); never `time.sleep` in tests.

## Implementation Guide

**Recommended order** (matches tasks.md):
1. Constructor — add `max_retries`, `backoff_base`, `sleep` params (+ `import time`, `Callable`);
   store on `self`. `File: src/osspulse/delivery/discord_delivery.py`.
2. Add `_do_post_with_retry(self, client, *, json_body, noun, unit, index, total)` — the loop from
   §Sequence Flows, incl. a small `_parse_retry_after(response) -> float | None` and a
   `_backoff_wait(attempt, retry_after) -> float` (or inline). Compose all errors from
   status/type-name only.
3. Refactor `_post_one` → delegate to `_do_post_with_retry(..., json_body={"content": msg},
   noun="discord delivery", unit="message", ...)`. Same for `_post_one_embed`
   (`json_body={"embeds": embeds}`, `noun="discord embed delivery"`, `unit="batch"`).
4. Update tests — split the parametrized non-2xx test; add retry/backoff/`Retry-After`/parity tests.

**Patterns to follow:**
- Error construction: mirror the existing `f"discord delivery failed: HTTP {code} (message {i}/{n})"`
  wording so URL-secrecy tests and message-shape stay stable.
- Test injection: pass `sleep=fake_sleep` (a `MagicMock` or a list-appender) + a small `max_retries`
  so the suite is fast — mirror the v3-llm-throttle sleep-injection pattern.
- Multi-attempt mock: `client.post.side_effect = [resp1, resp2, ...]` to script attempt sequences.

**Gotchas:**
- `sleep` only *between* attempts — assert `sleep.call_count == attempts - 1` on exhaustion, `0`
  on non-transient.
- `attempt` starts at `0` → first-retry wait for `backoff_base=1.0` is `1.0` (keep consistent with
  AC-001-006's `max(5, 1.0)`).
- `Retry-After` only exists on a response; timeout/network failures skip the `max()` floor.
- A `429` with malformed `Retry-After` must not crash — `_parse_retry_after` returns `None`.
- `max_retries=0`: the loop must make exactly one attempt and raise without ever sleeping.
