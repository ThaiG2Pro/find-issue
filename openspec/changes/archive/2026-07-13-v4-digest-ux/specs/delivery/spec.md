## MODIFIED Requirements

### Requirement: Discord delivery can POST the digest as Embeds when opted in
When `discord_use_embeds` is `true`, the `DiscordDelivery` adapter SHALL deliver the digest
as Discord **Embeds** — a JSON body of the shape
`{"embeds": [ {"title", "description", "color", "footer": {"text"}}, ... ]}` — instead of the
plain-text `{"content": ...}` body. The adapter SHALL build **one embed per item** grouped by
repo, preceded by **one header embed per repo**:
- **Header embed** (one per repo, emitted before that repo's item embeds): `color` =
  `0xFEE75C` (yellow), `title` = the repo name, `description` = `"{N} items — {lookback} ngày
  qua"` where `{N}` is the count of that repo's items shown.
- **Item embed** (one per surviving item): `title` = the item's title truncated to at most
  **256** Unicode code points (Discord's embed-title limit), `description` = the item's LLM
  summary, `color` = the item-type color (issue=`0xED4245`, release=`0x57F287`,
  discussion=`0x5865F2`, and a defined fallback color for any other type), `footer.text` =
  `"{repo} • {item_type} • OSS Pulse"`.
The adapter SHALL NOT import `osspulse.github`, `osspulse.summarizer`, or `osspulse.cache`
(the S5→S6 boundary is preserved; whether per-item data reaches the adapter via a widened
seam or in-adapter parsing is an architect decision, but no upstream *pipeline* module is
imported). When `discord_use_embeds` is `false` (the default) the adapter SHALL POST the
existing plain-text `{"content": ...}` body unchanged.

> ACs: AC-V4-001-001 [CONFIRMED], AC-V4-001-005 [CONFIRMED], AC-V4-002-009 [CONFIRMED], AC-V4-002-010 [CONFIRMED], AC-V4-002-011 [CONFIRMED]
> Business rules: BR-V4-001-001, BR-V4-001-002, BR-V4-002-006, BR-V4-002-007
> Integration: INT-V4-001-001, INT-V4-002-001
> Risk: T1 (URL leak — preserved)

#### Scenario: Embed mode emits a header embed plus one embed per item (AC-V4-002-009) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and a repo `owner/name` has 3 items shown
- **THEN** the request's `embeds` array contains, for that repo, a header embed first (`color = 0xFEE75C`, `title = "owner/name"`, `description = "3 items — {lookback} ngày qua"`) followed by 3 item embeds, each with `description` equal to that item's summary and `footer.text` equal to `"owner/name • {item_type} • OSS Pulse"`

#### Scenario: Item embed color is chosen by item type (AC-V4-002-010) [CONFIRMED]
- **WHEN** item embeds are built for an issue, a release, a discussion, and an item of an unrecognized type
- **THEN** their `color` values are `0xED4245`, `0x57F287`, `0x5865F2`, and the defined fallback color respectively, and no item is omitted from the embeds

#### Scenario: An over-length item title is truncated to 256 code points (AC-V4-002-011) [CONFIRMED]
- **WHEN** an item's title is longer than 256 Unicode code points in embed mode
- **THEN** the item embed's `title` is that title truncated to 256 code points (measured in code points, not UTF-8 bytes), and the untruncated title is not sent

#### Scenario: Embed mode is off by default and preserves plain-text delivery (AC-V4-001-005) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `false` (or the `[discord]` section is absent) and `deliver(content)` is called
- **THEN** the adapter POSTs the existing plain-text JSON body whose `content` field equals the (split) digest string, and sends NO `embeds` field — byte-identical to the pre-change behavior

#### Scenario: Embed mode POSTs a well-formed embeds body (AC-V4-001-001) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and the digest contains items for two repos that fit within all embed limits
- **THEN** the adapter issues an HTTPS POST whose JSON body has an `embeds` array containing a header embed and item embeds for each repo in document order, and returns normally on a 2xx response

### Requirement: Embed color is deterministic across runs
Each embed's `color` SHALL be a deterministic integer that is identical on every run and
across processes. Item embeds SHALL be colored from a **fixed item-type map** (issue =
`0xED4245`, release = `0x57F287`, discussion = `0x5865F2`, with a fixed fallback color for any
other type); header embeds SHALL use the fixed color `0xFEE75C`. Because colors are a fixed
lookup by item type (no hashing), the mapping is trivially stable. The adapter SHALL NOT use
Python's builtin `hash()` (process-salted via `PYTHONHASHSEED`) for any color selection.

> ACs: AC-V4-001-002 [CONFIRMED]
> Business rules: BR-V4-001-003, BR-V4-002-006
> Risk: Idempotency (project non-negotiable)

#### Scenario: The same item type yields the same color on repeated runs (AC-V4-001-002) [CONFIRMED]
- **WHEN** item embeds for the same item type are built in two separate adapter invocations (simulating two runs / two processes)
- **THEN** both carry the identical integer `color` from the fixed item-type map, and builtin `hash()` is not used

### Requirement: Embed payloads respect Discord's embed limits with plain-text fallback
Embed delivery SHALL respect Discord's limits: at most **10 embeds per request**, each embed
`description` at most **4096** Unicode characters (code points), and each embed `title` at
most **256** Unicode characters (code points, not UTF-8 bytes, matching the existing
content-limit convention). When the total number of embeds (header + item embeds) exceeds 10,
the adapter SHALL batch them into multiple sequential POST requests of ≤ 10 embeds each, in
document order. When a single embed `description` exceeds 4096 characters, the adapter SHALL
split it by line across multiple embeds so no `description` exceeds 4096 characters; an item
`title` exceeding 256 characters SHALL be truncated to 256. When an embed body cannot be
formed within these limits, or when there are no items to render (e.g. the "No new items"
digest), the adapter SHALL fall back to the existing plain-text `content` delivery path so the
run never fails purely due to embed formatting.

> ACs: AC-V4-001-003 [CONFIRMED], AC-V4-001-004 [CONFIRMED], AC-V4-001-006 [CONFIRMED], AC-V4-002-008 [CONFIRMED]
> Business rules: BR-V4-001-004, BR-V4-001-005, BR-V4-002-008
> Risk: DoS-via-hang (timeout preserved across batched requests)

#### Scenario: More than 10 embeds are batched into multiple requests (AC-V4-002-008) [CONFIRMED]
- **WHEN** a single repo has 10 items in embed mode (10 item embeds + 1 header embed = 11 embeds)
- **THEN** the adapter issues ≥ 2 sequential POST requests, each carrying ≤ 10 embeds, in document order, and returns normally when all responses are 2xx

#### Scenario: An over-length description is split by line across embeds (AC-V4-001-003) [CONFIRMED]
- **WHEN** one embed's `description` (an item summary) exceeds 4096 Unicode characters in embed mode
- **THEN** it is emitted as multiple embeds whose `description` fields are each ≤ 4096 characters (split on line boundaries), measured in code points

#### Scenario: More than 10 total embeds across repos are batched (AC-V4-001-004) [CONFIRMED]
- **WHEN** the digest yields 11+ total embeds (header + item embeds) in embed mode
- **THEN** the adapter issues ≥ 2 sequential POST requests, each carrying ≤ 10 embeds, in document order, and returns normally when all responses are 2xx

#### Scenario: A digest with no items falls back to plain text (AC-V4-001-006) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and `content` is the S5 "No new items in the last N days" document (no items / no `## ` section)
- **THEN** the adapter delivers it via the existing plain-text `content` path (one `{"content": ...}` POST), not as embeds, and returns normally on 2xx

## Business Rules
- BR-V4-002-001: The default `SummarizerConfig.max_retries` is `7`; combined with the existing `retry_backoff_base_seconds=1.0` exponential backoff this gives the 1/2/4/8/16/32/64 s retry sequence. Only the default value changes — retry structure, `Retry-After` honoring, and skip-log-continue-on-exhaustion are unchanged.
- BR-V4-002-002: The pipeline truncates each `(repo, item_type)` group to `Config.max_items_per_type`, keeping the newest by `created_at` desc, BEFORE the summarize call so dropped items incur no LLM cost.
- BR-V4-002-003: Truncation never changes what is recorded as seen; `mark_seen` always records the full collected set (idempotency invariant, unchanged from BR-V2-001-002).
- BR-V4-002-004: `[watchlist] max_items_per_type` is validated fail-fast as a strict positive int (rejects bool/float/str, requires ≥ 1) at config load, defaulting to 10 — mirroring the `lookback_days` guard.
- BR-V4-002-005: The renderer emits `⚠️ +{count} items not shown (limit: {N})` once per repo section iff that repo's dropped count is non-zero; a no-truncation digest is byte-identical to pre-change output.
- BR-V4-002-006: In Option A embed mode, item embeds are colored by a fixed item-type map (issue `0xED4245`, release `0x57F287`, discussion `0x5865F2`, fixed fallback for others) and the per-repo header embed is `0xFEE75C`; no builtin `hash()` is used.
- BR-V4-002-007: Each embed carries `footer.text = "{repo} • {item_type} • OSS Pulse"` (item embeds) and the header embed's `description = "{N} items — {lookback} ngày qua"`; the item title is truncated to ≤ 256 code points.
- BR-V4-002-008: Embed limits are enforced in Unicode code points — ≤ 10 embeds/request (batch when exceeded), ≤ 4096 chars/description (line-split when exceeded), ≤ 256 chars/title (truncate when exceeded); over-limit or item-less digests fall back to the plain-text path.

## Integration Points
- INT-V4-002-001: S7 CLI/pipeline continues to construct `DiscordDelivery(webhook_url, timeout=..., use_embeds=config.discord_use_embeds)` for the `discord` destination. Option A per-item embeds require the adapter to have per-item data (repo, item_type, title, summary); the mechanism by which that data reaches the adapter — a widened delivery seam versus in-adapter parsing of the rendered digest — is resolved by the architect (ADR) and MUST NOT introduce an `osspulse.github`/`summarizer`/`cache` import.
