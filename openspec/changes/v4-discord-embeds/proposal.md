## Why

Discord delivery currently POSTs the digest as a single plain-text `{"content": "..."}`
message. Plain text renders the Markdown literally (`## repo`, `### Issue mới (3)`) with
no visual grouping, so a multi-repo digest is a wall of hashes and dashes. Discord Embeds
give each repo its own titled, colored card — the digest becomes scannable in the "readable
in < 2 minutes" spirit of the project. This is an opt-in cosmetic upgrade for the existing
Discord destination; nothing else in the pipeline changes.

## What Changes

- Add an **opt-in** `[discord] use_embeds` boolean config key (default `false` → existing
  plain-text behavior is preserved, backward compatible).
- When `use_embeds = true`, `DiscordDelivery.deliver(content)` parses the rendered Markdown
  digest at `## ` repo-section boundaries and POSTs each section as a **Discord Embed**
  (`{"embeds": [{...}]}`) instead of `{"content": ...}`.
- Per embed: `title` = the repo header text (`vercel/next.js — 1 ngày qua`), `description`
  = the section body, `color` = a deterministic value derived from a **stable** hash of the
  repo slug over a fixed 5–6 color palette, `footer.text` = `OSS Pulse • {timestamp}`.
- Respect Discord embed limits: max 10 embeds/request, description ≤ 4096 chars (code
  points). Batch embeds into requests of ≤ 10; split an over-length section's description
  by line across multiple embeds.
- **Fallback**: if an embed payload cannot be formed within limits, fall back to the
  existing plain-text `content` split path for that content — a run never fails purely
  because of embed formatting.
- The `Delivery` port signature is UNCHANGED (`deliver(self, content: str) -> None`); embed
  conversion happens entirely inside the adapter from the Markdown string (preserves the S5→S6
  string seam and AC-6-002 no-upstream-import boundary).

## Capabilities

### New Capabilities
- _(none)_

### Modified Capabilities
- `delivery`: adds an embed rendering mode to the existing `DiscordDelivery` adapter and a
  new `[discord] use_embeds` config key. Modifies the existing "Discord push delivery POSTs
  the digest to a webhook" requirement (payload shape becomes mode-dependent) and the
  config-driven "Destination selection" requirement (new `[discord]` section). All plain-text
  and file/stdout behavior is unchanged.

## Impact

- Code: `src/osspulse/delivery/discord_delivery.py` (embed builder + mode switch),
  `src/osspulse/config.py` (`_validate_discord_use_embeds` + `[discord]` parse),
  `src/osspulse/models.py` (`Config.discord_use_embeds: bool = False`), pipeline wiring in
  `cli.py`/pipeline passes the new flag to `DiscordDelivery`.
- Tests: `tests/` Discord delivery + config tests (module scope).
- No new dependencies (stdlib `hashlib` for the stable color hash; `httpx` already present).
- No API, no schema, no security-surface change beyond the existing webhook (URL still
  env-resolved + allowlisted; embeds carry no new secret).

## Assumptions

- **[CONFIRMED]** The embed `title` is the repo header line text with the leading `## `
  stripped (`vercel/next.js — 1 ngày qua`) — the renderer already emits exactly this string
  per section (`renderer.py` `## {repo} — {lookback_days} ngày qua`), so no new renderer
  coupling or date-range computation is needed. (User design decision #3.)
- **[CONFIRMED]** One embed per `## ` repo section; the section body (its `### group` lines)
  becomes the embed `description`. (User design decisions #1, #2.)
- **[CONFIRMED]** `use_embeds` defaults to `false` for backward compatibility. (User #6.)
- **[CONFIRMED]** Fallback to plain text when embed limits can't be met. (User #7.)
- **[ASSUMED]** The color palette is a fixed list of 5–6 Discord-friendly integers hardcoded
  in the adapter (e.g. blurple `0x5865F2`, green, yellow, fuchsia, red, blue). The exact
  values are an implementation detail; the AC only pins *determinism*, not specific hues.
- **[ASSUMED]** The `footer` timestamp is the delivery-time UTC instant formatted ISO-8601
  (e.g. `2026-07-12T13:25:00Z`). It is generated at deliver time, so it is NOT idempotent
  across runs — acceptable because the footer is cosmetic and Discord messages are not
  re-delivered idempotently anyway (delivery has no dedupe). Content/description determinism
  is unaffected.
- **[ASSUMED]** The digest's leading `# OSS Pulse Digest` H1 and any preamble before the
  first `## ` are dropped from embeds (they carry no repo content); the "No new items" doc
  (which has NO `## ` section) falls back to a single plain-text `content` message.

## Edge Cases

_(scope=tiny — the categories that genuinely apply)_

1. **Input boundary — no repo sections**: "No new items" digest has zero `## ` sections →
   no embeds can be built → fall back to plain-text `content` (AC-V4-001-006).
2. **Input boundary — section description > 4096 chars**: one repo section body exceeds the
   embed description limit → split its description by line across multiple embeds for that
   repo, none exceeding 4096 code points (AC-V4-001-003).
3. **Input boundary — > 10 repo sections**: more than 10 embeds needed → batch into multiple
   POST requests of ≤ 10 embeds each, in document order (AC-V4-001-004).
4. **Data integrity — color determinism**: builtin `hash()` is process-salted
   (PYTHONHASHSEED), so two runs would color the same repo differently. MUST use a stable
   hash (`hashlib`) so `hash(repo_slug) % len(palette)` is identical every run
   (AC-V4-001-002). This is the main correctness trap.
5. **Data integrity — char vs byte limit**: 4096 is Unicode code points, not UTF-8 bytes
   (matches the existing 2000-char content limit convention) — a section with "Khác"/emoji
   under 4096 chars but over 4096 bytes is NOT split (AC-V4-001-003).
6. **State transition — opt-out default**: config with no `[discord]` section →
   `discord_use_embeds = false` → unchanged plain-text path (AC-V4-001-005).
7. **Data integrity — bool-trap config**: `use_embeds = "yes"` or `= 1` (non-bool) → fail
   fast with `ConfigError` at load (`type(v) is not bool`, mirroring `delta.enabled`)
   (AC-V4-001-008).
8. **Integration — POST failure in embed mode**: an embed request returns non-2xx / times
   out → same fatal `DeliveryError` path as plain text; webhook URL never leaked
   (AC-V4-001-007, preserves AC-V2-005-011).

## Early Risk Flags

- **T1 (URL leak) — preserved**: embed mode reuses the same POST/error path; the webhook URL
  must still never appear in `DeliveryError` messages. No new leak surface, but the embed
  code path must not `str(exc)`/`repr(request)` (see existing adapter guard).
- **Idempotency (project non-negotiable)**: color hash MUST be stable across runs — do not
  use builtin `hash()`. Footer timestamp is deliberately non-idempotent but cosmetic only.
- **DoS-via-hang — preserved**: multi-request embed batching reuses the same explicit
  timeout; a hung endpoint on request _k_ fails fatally (no rollback of earlier requests).
- STRIDE full threat-model not run: this CR adds no new trust boundary, secret, or input
  source — it only reshapes the JSON body sent to the already-validated, allowlisted webhook.
  Security-relevant behavior (URL secrecy, timeout, allowlist) is inherited unchanged from
  v2-005-push-delivery.

Figma: N/A (CLI tool; Discord renders the embed visuals server-side).
