## ADDED Requirements

### Requirement: Discord delivery retries transient failures with exponential backoff
The `DiscordDelivery` adapter SHALL retry a **transient** POST failure with exponential
backoff before giving up, so a momentary Discord rate-limit or server error does not abort
the run. The adapter's `__init__` SHALL accept three defaulted parameters — `max_retries: int`
(default `3`), `backoff_base: float` (default `1.0`), and `sleep: Callable[[float], None]`
(default `time.sleep`) — where `sleep` exists solely for test injection. A **transient**
failure SHALL be defined as an HTTP `429` response, any HTTP `5xx` response, an
`httpx.TimeoutException`, or an `httpx.RequestError` (connection/DNS/network). A
**non-transient** failure — any other non-2xx response, i.e. a `4xx` other than `429` such as
`400`/`401`/`403`/`404` — SHALL fail immediately with `DeliveryError` and SHALL NOT be retried
or slept on. On a transient failure the adapter SHALL make at most `max_retries + 1` total
attempts (one initial attempt plus up to `max_retries` retries); it SHALL wait
`backoff_base * 2 ** attempt` seconds before each retry, and when the failing response carries
a numeric `Retry-After` header it SHALL instead wait `max(Retry-After, backoff_base * 2 ** attempt)`
seconds. A missing, empty, or non-numeric `Retry-After` SHALL be ignored (fall back to the
pure backoff formula, never crash). The adapter SHALL call `sleep` only *between* attempts and
never after the final failed attempt. When all attempts are exhausted the adapter SHALL raise
`DeliveryError` whose message contains no webhook URL (AC-V2-005-011 preserved). Retry SHALL be
applied **per POST** (per split message and per embed batch); in a multi-message push each POST
has its own retry budget and already-delivered messages are NOT rolled back.

> ACs: AC-001-001 [CONFIRMED], AC-001-002 [CONFIRMED], AC-001-003 [CONFIRMED], AC-001-004 [CONFIRMED], AC-001-005 [ASSUMED], AC-001-006 [CONFIRMED], AC-001-007 [ASSUMED], AC-001-008 [CONFIRMED], AC-001-009 [ASSUMED], AC-001-011 [CONFIRMED]
> Business rules: BR-001-001, BR-001-002, BR-001-003, BR-001-004
> Risk: T1 (URL leak — preserved), T4 (DoS via hang — bounded by max_retries)

#### Scenario: A transient 5xx succeeds on retry (AC-001-001) [CONFIRMED]
- **WHEN** a POST returns HTTP `503` on the first attempt and HTTP `204` on the second, with `max_retries = 3`
- **THEN** `deliver` returns normally, exactly two POSTs are made, and the injected `sleep` is called exactly once (before the retry)

#### Scenario: Retries are exhausted then delivery fails (AC-001-002) [CONFIRMED]
- **WHEN** every attempt returns HTTP `500` with `max_retries = 3`
- **THEN** the adapter makes 4 total attempts, calls `sleep` 3 times, and finally raises `DeliveryError`

#### Scenario: A timeout on every attempt is retried then fatal (AC-001-003) [CONFIRMED]
- **WHEN** every attempt raises `httpx.TimeoutException` with `max_retries = 2`
- **THEN** the adapter makes 3 total attempts, calls `sleep` 2 times, and raises `DeliveryError` mentioning a timeout

#### Scenario: A non-transient 4xx fails immediately without retry (AC-001-004) [CONFIRMED]
- **WHEN** a POST returns HTTP `403` (or `400`/`401`/`404`)
- **THEN** the adapter raises `DeliveryError` after exactly one POST, and `sleep` is never called

#### Scenario: A network error is treated as transient (AC-001-005) [ASSUMED]
- **WHEN** a POST raises `httpx.RequestError` (e.g. `ConnectError`) on the first attempt and returns HTTP `204` on the second, with `max_retries = 3`
- **THEN** `deliver` returns normally, two POSTs are made, and `sleep` is called once

#### Scenario: Retry-After overrides the backoff wait when larger (AC-001-006) [CONFIRMED]
- **WHEN** a POST returns HTTP `429` with header `Retry-After: 5` and `backoff_base = 1.0` so the pure backoff wait for the first retry is `1.0`
- **THEN** the adapter waits `max(5, 1.0) = 5` seconds (the value passed to `sleep` is `5`) before the retry

#### Scenario: A missing or malformed Retry-After falls back to the backoff formula (AC-001-005b) [CONFIRMED]
- **WHEN** a POST returns HTTP `429` with no `Retry-After` header or a non-numeric one (e.g. `Retry-After: soon`) and `backoff_base = 1.0`
- **THEN** the adapter does not crash and waits `backoff_base * 2 ** attempt` seconds (the pure backoff formula) before the retry

#### Scenario: Backoff grows exponentially across retries (AC-001-007) [ASSUMED]
- **WHEN** three consecutive retries occur (all transient failures) with `backoff_base = 1.0`
- **THEN** the successive values passed to `sleep` are non-decreasing and follow `backoff_base * 2 ** attempt` (e.g. `1, 2, 4`), never a fixed constant

#### Scenario: Embed-mode POSTs use the same retry policy (AC-001-008) [CONFIRMED]
- **WHEN** an embed batch POST (`use_embeds = true`) returns HTTP `429` on the first attempt and HTTP `204` on the second
- **THEN** the embed POST is retried identically to a plain-text POST, `deliver` returns normally, and `sleep` is called once

#### Scenario: Per-message retry budget in a multi-message push (AC-001-009) [ASSUMED]
- **WHEN** a digest splits into 2 messages, message 1 succeeds on its first POST, and message 2 returns `503` once then `204`
- **THEN** message 1 is delivered once, message 2 is retried on its own budget and then delivered, and no already-delivered message is re-sent or rolled back

#### Scenario: max_retries = 0 reproduces single-attempt behavior (AC-001-011) [CONFIRMED]
- **WHEN** the adapter is constructed with `max_retries = 0` and a POST returns a transient HTTP `503`
- **THEN** the adapter makes exactly one POST, never calls `sleep`, and raises `DeliveryError` immediately

## MODIFIED Requirements

### Requirement: Discord push failure is fatal with a clear CLI error
Discord delivery SHALL raise `DeliveryError` on any POST failure that is **not recovered by
retry**, which the CLI surfaces as a one-line `Error: <message>` on **stderr** and exits
non-zero (`1`). A **transient** failure — an HTTP `429`, any HTTP `5xx`, a connection/DNS error
(`httpx.RequestError`), or a request timeout (`httpx.TimeoutException`) — SHALL first be retried
with exponential backoff (see "Discord delivery retries transient failures with exponential
backoff"); `DeliveryError` is raised for such a failure only after the retry budget is exhausted.
A **non-transient** HTTP `4xx` other than `429` (`400`/`401`/`403`/`404`) SHALL remain fatal on
the first attempt with no retry. No raw Python stacktrace SHALL be shown. The webhook URL SHALL
NOT appear in the error message. The HTTPS request SHALL use an explicit timeout (default ~10
seconds) so a hung Discord endpoint cannot block the pipeline indefinitely; the timeout applies
to **each** attempt. In a multi-message push, if message _k_ fails fatally (after its own retry
budget is exhausted), delivery SHALL fail fatally at that point (messages already delivered are
accepted; there is no rollback).

> ACs: AC-V2-005-008 [CONFIRMED], AC-V2-005-009 [CONFIRMED], AC-V2-005-010 [CONFIRMED], AC-V2-005-011 [CONFIRMED], AC-001-010 [CONFIRMED]
> Business rules: BR-V2-005-004, BR-001-001, BR-001-002
> Risk: T1 (URL leak), T4 (DoS via hang — now bounded by max_retries)
> Decision: CLAR-3

#### Scenario: A non-transient HTTP error response surfaces a clean fatal error (AC-V2-005-008) [CONFIRMED]
- **WHEN** the webhook responds with a non-transient non-2xx status (e.g. 400, 401, 403, 404)
- **THEN** delivery raises `DeliveryError` after one attempt, the CLI prints `Error: <message>` on stderr, exits non-zero, and shows no Python stacktrace

#### Scenario: A network failure surfaces a clean fatal error after retries (AC-V2-005-009) [CONFIRMED]
- **WHEN** the POST fails due to a connection or DNS error on every attempt (retry budget exhausted)
- **THEN** delivery raises `DeliveryError`, the CLI exits non-zero with `Error: <message>` on stderr and no stacktrace

#### Scenario: A hung endpoint is bounded by a request timeout on every attempt (AC-V2-005-010) [CONFIRMED]
- **WHEN** the webhook does not respond within the configured request timeout on every attempt (retry budget exhausted)
- **THEN** each request is aborted at the timeout, delivery raises `DeliveryError` (timeout) after the retries, and the CLI exits non-zero without hanging

#### Scenario: The webhook URL never appears in the error output (AC-V2-005-011) [CONFIRMED]
- **WHEN** any Discord delivery error is surfaced on stderr (including one raised after retries are exhausted)
- **THEN** the error message does NOT contain the webhook URL (only a generic description of the failure)

#### Scenario: The final DeliveryError after retries never leaks the URL (AC-001-010) [CONFIRMED]
- **WHEN** all retry attempts fail (transient) and the adapter raises the final `DeliveryError`
- **THEN** its message is built from the HTTP status code or the exception *type name* only, and contains neither the webhook URL nor `str(exc)`/`repr(request)`

### Requirement: Embed delivery failure stays fatal without leaking the webhook URL
An embed-mode POST failure that is not recovered by retry SHALL raise `DeliveryError`,
surfaced by the CLI as a one-line `Error: <message>` on stderr with a non-zero exit and no
Python stacktrace — identical to plain-text failure semantics (BR-V2-005-004). A failure is
"not recovered by retry" when it is a non-transient HTTP `4xx` other than `429`, or a transient
`429`/`5xx`/connection error/timeout whose retry budget has been exhausted. Transient embed-POST failures SHALL be retried with the same exponential-backoff
policy as plain-text POSTs before becoming fatal. The webhook URL SHALL NOT appear in any error
message. In a multi-request embed push, a failure on request _k_ (after its own retry budget) SHALL
be fatal at that point (earlier requests already delivered; no rollback), and the same explicit
request timeout SHALL bound every attempt of every request.

> ACs: AC-V4-001-007 [CONFIRMED], AC-001-008 [CONFIRMED]
> Business rules: BR-V4-001-006, BR-001-001
> Risk: T1 (URL leak — preserved), T4 (DoS via hang — preserved, bounded by max_retries)

#### Scenario: An embed POST error surfaces a clean fatal error without the URL (AC-V4-001-007) [CONFIRMED]
- **WHEN** an embed-mode POST responds with a non-transient non-2xx, or fails transiently on every attempt (retry budget exhausted)
- **THEN** the adapter raises `DeliveryError`, the CLI prints `Error: <message>` on stderr, exits non-zero, shows no stacktrace, and the message does NOT contain the webhook URL

#### Scenario: A transient embed POST is retried before failing (AC-001-008) [CONFIRMED]
- **WHEN** an embed batch POST returns HTTP `429` on the first attempt and HTTP `204` on the second
- **THEN** the embed POST is retried with backoff, `deliver` returns normally, and `sleep` is called once

## Business Rules
- BR-001-001: A Discord POST failure is classified before it is fatal. **Transient** = HTTP `429`, any HTTP `5xx`, `httpx.TimeoutException`, or `httpx.RequestError` (connection/DNS/network) → retried with backoff. **Non-transient** = any other non-2xx, i.e. a `4xx` other than `429` (`400`/`401`/`403`/`404`) → fatal on the first attempt, no retry, no sleep. This SUPERSEDES the "No retry in V2" clause of BR-V2-005-004 for transient failures; all other BR-V2-005-004 guarantees (fatal→exit 1, no stacktrace, URL never leaked, no rollback) are preserved.
- BR-001-002: A transient failure is retried up to `max_retries` times (default `3`), for at most `max_retries + 1` total attempts. `max_retries = 0` makes the adapter single-attempt / fatal-immediately (pre-change behavior). The per-attempt request timeout (default ~10s) is preserved on every attempt, so total elapsed time is bounded.
- BR-001-003: The wait before each retry is `backoff_base * 2 ** attempt` seconds (`backoff_base` default `1.0`, `attempt` starting at `0`). When the failing response carries a numeric `Retry-After` header, the wait is `max(Retry-After, backoff_base * 2 ** attempt)`. A missing/empty/non-numeric `Retry-After` is ignored (pure backoff formula, never crash). `sleep` is called only between attempts, never after the final failed attempt.
- BR-001-004: Retry is applied **per POST** (per split plain-text message and per embed batch). Each POST has an independent retry budget; already-delivered messages/requests are never rolled back or re-sent as part of another POST's retry. The injected `sleep: Callable[[float], None]` (default `time.sleep`) exists solely so tests can assert wait behavior without real delays; production uses the default.
