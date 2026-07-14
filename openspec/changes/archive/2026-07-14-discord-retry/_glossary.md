# Glossary — discord-retry (ticket 001)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| Transient failure | A Discord POST failure worth retrying: HTTP `429`, any HTTP `5xx`, `httpx.TimeoutException`, or `httpx.RequestError` (connection/DNS/network). | analyst | BR-001-001 | S2 |
| Non-transient failure | A permanent/caller failure that fails immediately with no retry: any non-2xx other than 429, i.e. a `4xx` such as `400`/`401`/`403`/`404`. | analyst | BR-001-001 | S2 |
| max_retries | Constructor param (default `3`) — max number of retries after the initial attempt; total attempts = `max_retries + 1`. `0` = single-attempt (pre-change behavior). | analyst | BR-001-002 | S2 |
| backoff_base | Constructor param (default `1.0`) — base seconds for the exponential backoff wait `backoff_base * 2 ** attempt`. | analyst | BR-001-003 | S2 |
| sleep (injected) | Constructor param `Callable[[float], None]` (default `time.sleep`) — injected so tests assert wait behavior without real delays. | analyst | BR-001-004 | S2 |
| Backoff wait | Seconds waited before a retry: `backoff_base * 2 ** attempt`, or `max(Retry-After, backoff_base * 2 ** attempt)` when a numeric `Retry-After` header is present. | analyst | BR-001-003 | S2 |
| Retry-After | Discord response header (seconds); when numeric it raises the wait via `max(...)`; missing/empty/non-numeric is ignored (never crash). | analyst | BR-001-003, AC-001-006 | S2 |
| Per-POST retry budget | Retry applies independently per split message and per embed batch; already-delivered POSTs are never rolled back or re-sent. | analyst | BR-001-004 | S2 |
| `_do_post_with_retry` | Single private helper on `DiscordDelivery` owning the per-POST attempt loop (POST → classify → backoff → sleep → retry/raise); called by both `_post_one` and `_post_one_embed`. | architect | ADR-001, AC-001-008 | S3 |
| `_parse_retry_after` | Helper returning the `Retry-After` header as a finite float, or `None` when missing/empty/non-numeric (never raises). | architect | ADR-002, AC-001-006 | S3 |
| attempt index | Loop counter starting at `0`; the wait before retry `n` is `backoff_base * 2 ** attempt`, so first-retry wait = `backoff_base` (`1.0` by default). | architect | ADR-002, AC-001-007 | S3 |
