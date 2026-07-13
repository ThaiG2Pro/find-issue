## Why

Four small, independent digest-UX tweaks bundled into one CR (V4-002). Each targets a
concrete pain observed after v4-discord-embeds shipped:

1. **Retry too shallow** — the LLM summarizer gives up after 3 retries (max ~7s of
   backoff). On a busy free-tier provider a 429 burst outlasts that, so items get
   skipped and drop out of the digest. Bumping to 7 retries (1/2/4/8/16/32/64 s ≈ 2 min
   total) rides out longer rate-limit windows.
2. **Unbounded per-type volume** — a repo with a flood of new issues sends every item to
   the LLM (token cost) and produces an unreadable wall, breaking the "readable in < 2
   minutes" principle. Cap each item-type per repo to N (default 10), truncating the
   OLDEST — and do it **before** the LLM call so we never pay to summarize dropped items.
3. **Silent truncation** — if we drop items, the reader must know. A per-repo notice
   `⚠️ +{count} items not shown (limit: {N})` keeps the digest honest.
4. **Repo-level embeds are still a wall** — v4-discord-embeds gives one embed per repo
   whose description is the whole Markdown section. "Option A" makes each **item** its own
   embed (title = item title, description = summary, color by item type) with a per-repo
   header embed, so a Discord reader scans item-by-item.

All four are opt-in-safe: retry/truncate have backward-compatible defaults; the embed
change only affects the already-opt-in `discord_use_embeds=true` path.

## What Changes

- **Retry x7**: `SummarizerConfig.max_retries` default `3 → 7`; the existing exponential
  backoff (`base * 2**attempt`, base `1.0`) then yields the sequence 1/2/4/8/16/32/64 s.
  No code-shape change — only the default and the spec's stated attempt count. `Retry-After`
  honoring and skip-log-continue-on-exhaustion are unchanged.
- **Top-N truncate**: new `[watchlist] max_items_per_type` (positive int, default `10`).
  In the pipeline, after collect and **before** summarize, each `(repo, item_type)` group
  is truncated to at most N items, keeping the N **newest** by `created_at` (desc). Groups
  with ≤ N items are untouched.
- **Truncation alert**: when a repo had any item truncated, the rendered digest includes a
  per-repo-section line `⚠️ +{count} items not shown (limit: {N})` (aggregate count for
  that repo). No truncation → no line (output byte-identical to today). The renderer must
  receive per-repo truncated counts — the exact plumbing (render() signature vs. a small
  metadata object) is an architect ADR (flagged below).
- **Option A embed** (only when `discord_use_embeds=true`): embed mode changes from
  one-embed-per-repo-section to **one-embed-per-item** plus a per-repo header embed:
  - Item embed: `title` = item title (truncated at **256** code points — Discord embed
    title limit), `description` = the item's LLM summary, `color` by item type
    (`issue`=`0xED4245` red, `release`=`0x57F287` green, `discussion`=`0x5865F2` blurple;
    unknown → a defined fallback), `footer.text` = `"{repo} • {item_type} • OSS Pulse"`.
  - Header embed (one per repo, before that repo's item embeds): `color` = `0xFEE75C`
    (yellow), `title` = repo name, `description` = `"{N} items — {lookback} ngày qua"`.
  - The ≤ 10-embeds-per-request batching and the URL-never-leaked fatal-error path are
    unchanged. Building per-item embeds needs per-item data (repo, item_type, title,
    summary) — its source (parse the rendered Markdown vs. pass a structured item list)
    is an architect ADR (flagged below).

## Capabilities

### New Capabilities
- _(none)_

### Modified Capabilities
- `summarizer`: raise the default retry count (MODIFIES "Retry with backoff on rate-limit
  before skipping" — default 3 → 7; adds an explicit backoff-sequence scenario).
- `scheduler-cli`: add per-type truncation to the pipeline + a `[watchlist]
  max_items_per_type` config key (ADDED requirement + config validation).
- `digest-renderer`: surface a per-repo truncation notice when items were dropped (ADDED
  requirement; may modify the `render()` signature — architect ADR).
- `delivery`: change opt-in embed mode from one-embed-per-repo to one-embed-per-item plus a
  per-repo header embed (MODIFIES the v4-discord-embeds embed requirements: payload shape,
  color source, per-embed limits).

## Impact

- Code: `src/osspulse/summarizer/config.py` (default), `src/osspulse/config.py`
  (`_validate_max_items_per_type` + `[watchlist]` parse), `src/osspulse/models.py`
  (`Config.max_items_per_type`), `src/osspulse/pipeline.py` (truncation step + pass
  truncation counts to render), `src/osspulse/render/renderer.py` (alert line + signature),
  `src/osspulse/delivery/discord_delivery.py` (per-item embed builder + header embed).
- Tests: `tests/` summarizer, config, pipeline, renderer, discord delivery (module scope).
- No new dependencies. No API, no DB schema. No new secret/trust boundary (embed change
  reshapes the JSON body sent to the already-validated, allowlisted webhook).

## Non-Goals

Out of scope for this CR (explicitly NOT changed):
- **Batching LLM calls** — the summarizer still calls the LLM one item at a time; only the
  retry ceiling changes. No multi-item/batch prompt.
- **GitHub fetch logic** — collection, pagination, rate-limit backoff, ETag conditional
  requests are untouched. Truncation happens in the pipeline *after* collection.
- **State / ETag logic** — `mark_seen`, delta filtering, and the ETag store are unchanged;
  truncation never alters what is recorded as seen.
- **New destinations or the plain-text/file/stdout paths** — Option A only reshapes the
  already-opt-in Discord embed body; `use_embeds=false` and all non-Discord delivery are
  byte-identical to today.
- **A per-item "not shown" list** — the truncation alert is an aggregate count only; dropped
  items are not enumerated.

## Assumptions

- **[CONFIRMED]** Retry sequence is 1/2/4/8/16/32/64 s = the existing `base(1.0)*2**attempt`
  for attempts 0..6; only `max_retries` default changes (3 → 7). (User scope #1.)
- **[CONFIRMED]** Truncation keeps the **newest** N per `(repo, item_type)` by `created_at`
  desc and runs **before** the LLM summarize call (saves tokens). (User scope #2.)
- **[CONFIRMED]** `max_items_per_type` default is `10`, lives under `[watchlist]`, and is a
  positive int validated fail-fast at load (mirrors `lookback_days`). (User scope #2.)
- **[CONFIRMED]** The truncation alert is a per-repo-section aggregate line
  `⚠️ +{count} items not shown (limit: {N})`; absent when nothing was truncated. (User #3.)
- **[CONFIRMED]** Item-type→color map is exactly issue=`0xED4245`, release=`0x57F287`,
  discussion=`0x5865F2`; header embed = `0xFEE75C`. Item title truncated at 256 code
  points; footer = `"{repo} • {item_type} • OSS Pulse"`. (User scope #4.)
- **[ASSUMED]** The renderer learns per-repo truncated counts via a new `render()` parameter
  (e.g. `truncation: dict[str, int]` mapping repo → dropped count) rather than parsing them
  back out of anything. Exact shape is an **architect ADR** — the AC pins only the observable
  output. This may MODIFY the digest-renderer signature requirement (AC-5-001).
- **[ASSUMED]** Per-item embeds are built from per-item structured data (repo, item_type,
  title, summary) rather than re-parsing the rendered Markdown. The rendered Markdown *does*
  carry item_type only implicitly (via `### group` headers) and title/summary in a line
  format that contains quotes/em-dashes, so re-parsing is fragile; passing a structured item
  list to the adapter is cleaner. **This is the central design decision — architect ADR.**
  It may widen the `Delivery`/`DiscordDelivery` seam (currently `deliver(content: str)`),
  which the v4-discord-embeds change deliberately kept string-only — so it interacts with
  the memory lesson "payload-shape CR stays inside the adapter". Architect must reconcile.
- **[ASSUMED]** Unknown item types in embed mode get a defined fallback color (reuse the
  header yellow or a neutral grey); no item is dropped from embeds.

## Edge Cases

_(scope=tiny — the categories that genuinely apply across the four tweaks)_

1. **Input boundary — group exactly at N**: a `(repo, item_type)` group with exactly N
   items is NOT truncated and shows NO alert (off-by-one guard). (AC-V4-002-004/007)
2. **Input boundary — title > 256 chars**: an item title longer than 256 code points is
   truncated to 256 for the embed title (code points, not bytes — reuse the project's
   len(str) convention). (AC-V4-002-011)
3. **Data integrity — config bool/int trap**: `max_items_per_type = "10"`, `0`, `-1`, or a
   float → `ConfigError` at load (positive int only, mirrors `lookback_days`). (AC-V4-002-005)
4. **State transition — default when absent**: no `[watchlist] max_items_per_type` key →
   default 10; retry default 7 with no config present. Backward compatible. (AC-V4-002-005)
5. **Data integrity — truncation before summarize**: dropped items are never sent to the
   LLM (token-cost correctness), so the truncated count is computed pre-summarize, but the
   alert count must survive to the renderer even though those items are gone. (AC-V4-002-006)
6. **Integration — retry exhaustion unchanged**: after 7 failed retries the item is
   skip-logged-continued exactly as before (no new failure mode, just a higher ceiling).
   (AC-V4-002-002)
7. **Data integrity — unknown item_type color**: an item whose type is not
   issue/discussion/release still gets an embed with a defined fallback color; not dropped.
   (AC-V4-002-010)
8. **Input boundary — >10 item embeds**: many items now mean many embeds; the existing
   ≤10-embeds-per-request batching must still hold (a repo with 10 items + 1 header = 11
   embeds spans 2 requests). (AC-V4-002-008, preserves AC-V4-001-004)
9. **Concurrency/idempotency — determinism preserved**: with no truncation and embeds off,
   the digest is byte-identical to pre-change output; embed colors are a fixed type map
   (trivially deterministic, no hash). (AC-V4-002-007/010)

## Early Risk Flags

- **Idempotency (project non-negotiable)** — retry/truncate/alert are all deterministic
  functions of input + config. The Option A embed color is now a fixed item-type map (even
  simpler than v4-001's hashlib color — no hash at all), so no PYTHONHASHSEED risk.
- **Token-cost correctness** — truncation MUST happen before summarize; a regression that
  truncates after summarize would silently pay for dropped items (defeats the feature).
- **Seam-widening coupling (design)** — both the truncation alert (renderer needs counts)
  and Option A embeds (adapter needs per-item data) push against the current string-only
  seams (`render(items, *, lookback_days)` and `deliver(content: str)`). The architect must
  decide the plumbing for both together — they may share a "carry structured data further
  downstream" decision. This is the main design risk; do NOT condense it despite scope=tiny.
- **T1 (webhook URL leak) — preserved** — Option A reuses the same POST/error path; the URL
  must still never appear in `DeliveryError`. No new leak surface.
- STRIDE full threat-model NOT run: no new trust boundary, secret, input source, auth, PII,
  or payment surface — this only tunes retry counts, caps volume, and reshapes an existing
  webhook body. `security.stride_analysis=auto` → skip is correct.

Figma: N/A (CLI tool; Discord renders embed visuals server-side).
