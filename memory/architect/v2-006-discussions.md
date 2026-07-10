# Architect memory — v2-006-discussions

## 2026-07-09 — v2-006-discussions: GraphQL 200-with-errors → classify shape-first, never on error string

When an endpoint returns 200 that can still carry an `errors` array + a null sub-object (GraphQL, or
any partial-success envelope), classify on the RESPONSE SHAPE, not on a matched error-type/message
string. Order matters: check the null-connection/null-object shape FIRST (→ graceful skip), THEN
"any remaining errors → raise", THEN map. A disabled/not-found resource carries BOTH the null shape
AND an errors entry, so a "any errors → raise" check placed first would crash instead of skip.
Hardcoding `errors[].type == "..."` is brittle to wording changes — the null shape is stable.

## 2026-07-09 — v2-006-discussions: adding a POST verb to a GET-only client — parameterize the ONE retry helper, don't fork it

To add a second HTTP verb (here a fixed GraphQL POST) to a client whose single retry/backoff/classify
loop was GET-only: add a keyword `json_body: dict | None = None` — `None` keeps GET (all existing
callers unchanged by default), a dict switches to POST. This reuses the retry/status-classification/
token discipline verbatim (one place to keep correct) and scopes the "GET-only" security invariant to
the REST callers while adding exactly one fixed POST. A parallel `_post_with_retry` duplicates the
backoff loop → two places to drift. Assert-in-test that REST still issues GET (no body) as a tripwire.
