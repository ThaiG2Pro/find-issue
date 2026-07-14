# Architect memory — discord-retry

## 2026-07-14 — discord-retry: adding retry to a fatal-on-first-error sink = parameterize the ONE post helper, don't fork per body-shape
When a sink has two near-identical POST paths differing only in JSON body + error label
(`_post_one` `{"content"}` vs `_post_one_embed` `{"embeds"}`), fold retry/backoff/classify into a
single `_do_post_with_retry(*, json_body, noun, unit, ...)` helper both call — a duplicated loop is
the exact drift the embed-parity AC (AC-001-008) exists to catch. (Same shape as v2-006 "parameterize
the one retry helper, don't fork a parallel POST").

## 2026-07-14 — discord-retry: backoff attempt-index and Retry-After parsing are ADR-worthy even in a tiny change
Pin `attempt` from 0 (first-retry wait = `backoff_base`) so it matches the AC's worked example
`max(Retry-After, backoff_base*2**attempt)`; parse `Retry-After` to a finite float or None (untrusted
header, never crash); call `sleep` only BETWEEN attempts. Exception failures (timeout/network) carry no
response, so they always use pure backoff — the `max()` floor only applies on a response-carrying 429/5xx.
