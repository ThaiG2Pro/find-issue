## 2026-07-08 — v2-005-push-delivery: a message-limited push channel needs char-vs-byte + split-boundary + SSRF-allowlist ACs the raw "send to webhook" requirement never mentions

A "push the digest to a Discord/Slack webhook" requirement looks like a one-line HTTP POST, but
a message-limited channel hides three spec gaps the raw ask never states:
1. **Char-vs-byte length limit** — Discord's 2000 limit counts Unicode *characters*, not UTF-8
   bytes. A naive `len(content.encode())` split corrupts/over-splits any non-ASCII digest
   ("Khác", emoji). Spec the counting unit explicitly (AC-V2-005-007).
2. **Split boundary + oversized-unit fallback** — splitting a long digest needs a natural
   boundary (repo `## ` section) AND a hard fallback (split-by-line) for when a single unit alone
   exceeds the limit, or you can still emit an illegal >limit message.
3. **Webhook URL is a bearer secret AND an SSRF vector** — must be env-var-only (never in the
   committed config), never logged/echoed in errors, and validated at config load to https +
   a host allowlist (blocks mis-route + SSRF to internal hosts like 169.254.169.254). STRIDE
   auto-triggers here (secret + outbound network) — run it.

Generalizes to any push/notification channel with a payload size cap (SMS 160, Slack blocks, etc.):
size-limit unit, split strategy + fallback, and secret/SSRF handling are all CONTRACT ACs, not
implementation trivia. Also re-hit the delivery-6 "first-comma-SHALL" openspec-validate trap — a
requirement whose opening clause front-loads a dash-list before SHALL fails validation; put
SHALL in the first clause.
