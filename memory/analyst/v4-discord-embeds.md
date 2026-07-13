# analyst memory — v4-discord-embeds

## 2026-07-12 — v4-discord-embeds: a "richer output format" CR hides a hash-determinism idempotency trap
A cosmetic "make Discord output prettier with embeds" CR looks like pure formatting, but
"color derived from repo name hash" is the trap: Python's builtin `hash(str)` is salted by
`PYTHONHASHSEED`, so it produces a DIFFERENT color every process/run — silently violating the
project's idempotency non-negotiable. Spec MUST pin a STABLE hash (`hashlib`) and explicitly
forbid builtin `hash()`. General rule: any AC of the form "X derived from hash(name)" needs an
explicit stability/determinism AC.

## 2026-07-12 — v4-discord-embeds: new Discord limits mirror the existing content-limit convention
Embeds add a second set of Discord limits (≤10 embeds/request, ≤4096 chars/description) that
must be specified in the SAME units as the prior push-delivery work — Unicode code points, NOT
UTF-8 bytes (see v2-005). Reuse the established convention instead of re-deciding; and a
message-shaped-output CR still needs the batch/split + fallback ACs (over-limit → split/batch,
unformattable/empty → fall back to the old path) so formatting alone never fails a run.

## 2026-07-12 — v4-discord-embeds: a payload-shape CR on a fixed port stays inside the adapter
When the delivery port is `deliver(content: str)` (string seam), a "change the output format"
CR is adapter-internal: the embed conversion parses the rendered Markdown itself (split at
`## `) and the port signature + no-upstream-import boundary (AC-6-002) stay UNCHANGED. Don't
propose widening the port or importing the renderer — the string handoff already carries
everything, and the header line doubles as the embed title for free.
