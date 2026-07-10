## 2026-07-08 — v2-005-push-delivery: an HTTP-client error message can leak a URL secret — compose it from status/exception-type, never str(exc)

When an infra adapter POSTs to a URL that IS a bearer secret (Discord/Slack webhook, presigned
upload URL, etc.), the naive `DeliveryError(f"push failed: {exc}")` leaks the secret: httpx
`RequestError`/`HTTPStatusError` `str()`/repr embeds the full request URL. The design must
mandate composing the surfaced error from the **status code** and/or `type(exc).__name__`, never
`str(exc)` when the exception carries the URL. Also gate the secret at CONFIG LOAD, not delivery
time: resolve from env + validate scheme(https) + host allowlist there, so mis-route/SSRF fails
fast before any network I/O and the URL never lives in the committed config. Generalizes to any
outbound integration whose endpoint URL is itself the credential.

## 2026-07-08 — v2-005-push-delivery: a message-size-capped sink needs a pure char-based two-level splitter, specced in an ADR

For a delivery sink with a per-message size cap (Discord 2000 chars), the split logic is the real
design work, not the POST. Make it a PURE function (`_split_for_discord(content, limit) -> list`)
so it's unit-testable at boundaries, and spec two levels in the ADR: (1) split at a natural
content boundary (here renderer `## repo` sections), (2) a hard fallback (line-split, then
char-slice) for when a single unit alone exceeds the cap — otherwise you can still emit an illegal
oversized message. Measure `len(str)` (code points) when the sink counts characters; a byte-based
`len(x.encode())` over-splits non-ASCII. Reused delivery-6's per-module-error-class + CLI-catch
pattern (no new error class) and the CLI-tool no-openapi ADR precedent.
