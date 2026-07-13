# analyst memory — v4-digest-ux

## 2026-07-13 — v4-digest-ux: a "bundle of small UX tweaks" CR can still carry a real design decision — flag it, don't let scope=tiny bury it
Four independently-trivial tweaks (retry-count bump, top-N cap, an alert line, prettier
embeds) were bundled as one `scope=tiny` CR. Three are genuine one-liners, but the fourth
(per-item Discord embeds) plus the truncation-alert both need data that the CURRENT pipeline
seams don't carry: the renderer is `render(items, *, lookback_days)` (no truncation counts)
and the delivery adapter is `deliver(content: str)` (no per-item structure — v4-discord-embeds
deliberately kept it string-only and parsed Markdown in-adapter). So a "tiny" bundle secretly
proposes MODIFYING two frozen seams. Lesson: when a bundle mixes trivial-config tweaks with an
output-shape change, the output-shape change almost always needs data to travel further
downstream than the existing seam allows — tag it `[ASSUMED]`, pin only the observable output
in the AC, and explicitly hand the plumbing to the architect as a design ADR + `watch_items`,
noting it contradicts the prior "stays inside the adapter" lesson. Do NOT condense that section
because the CR is scope=tiny.

## 2026-07-13 — v4-digest-ux: truncation-before-summarize needs the drop-count to outlive the dropped items
"Cap items per type and tell the reader we truncated" has an ordering trap: to save LLM tokens
the cap MUST run before summarize, which means the dropped items are gone by render time — yet
the alert count must survive to the renderer. Spec the count as a first-class value computed at
truncation time and passed forward, not something recomputed later (it can't be — the items are
gone). Same shape as the delta selection-at-extend rule: what's RECORDED (mark_seen full set,
idempotency) is orthogonal to what's RENDERED (survivors) — keep them separate.

## 2026-07-13 — v4-digest-ux: a fixed value-map is a strictly better "deterministic color" than a hash
v4-discord-embeds needed a stable per-repo color and had to pin hashlib (builtin hash() is
PYTHONHASHSEED-salted). This CR colors by ITEM TYPE (a closed 3-value set) — so a plain fixed
dict is the color source: trivially deterministic, no hash, no seed risk, no determinism AC
needed beyond "it's a fixed map". When the keying dimension is a small closed enum, prefer a
literal map over any hash — it removes the entire idempotency-trap class instead of guarding it.
