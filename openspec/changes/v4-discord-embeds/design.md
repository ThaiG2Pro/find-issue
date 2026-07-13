## Sketch — Gap Analysis

**No critical gaps found.** The CR reshapes the JSON body `DiscordDelivery` POSTs to an
already-validated, allowlisted webhook. All 9 ACs (AC-V4-001-001, 002, 002b, 003, 004,
005, 006, 007, 008, 008a) map cleanly onto three touched files with no new trust boundary,
dependency, or upstream import.

Sketch (from spec deltas + code read):
- **Config**: 1 new optional key `[discord] use_embeds` (bool, default `false`) →
  `Config.discord_use_embeds`. Mirrors the existing `_validate_delta` bool-trap guard.
- **Adapter**: pure helpers `_parse_sections` → `_repo_color` → `_build_embeds` →
  `_batch_embeds`, plus a `deliver()` mode switch. No new I/O primitive — the embed POST
  reuses the existing `_post_one`/`_post_all` timeout + URL-never-leaked path with a
  different JSON body.
- **Flows**: 5 key flows — embed happy path, >4096-char split, >10-embed batch, no-section
  fallback, POST-failure fatal.

Verified against code:
- `_split_for_discord` already splits at `## ` line-boundaries (renderer output) — the
  section-parse logic is reused, not reinvented (search-first: Extend > Build).
- `_post_one` hardcodes `json={"content": msg}`; embed mode needs a sibling that sends
  `json={"embeds": [...]}` — the transport (try/except → `DeliveryError`, no `str(exc)`) is
  identical, so parameterize the payload rather than fork the error path.
- `Config` is a frozen dataclass; adding one field with a default is backward compatible.

No conflict with prior changes: v2-005-push-delivery owns the URL-secrecy + timeout
contract; this CR inherits it unchanged. No API surface, no DB, no schema.

## Context

Discord delivery (v2-005) POSTs the rendered digest as a single plain-text
`{"content": ...}` body, split into ≤2000-char messages at `## ` boundaries. Discord
renders Markdown literally, so a multi-repo digest is a wall of `##`/`###`/`-`. This CR
adds an **opt-in** embed mode: when `[discord] use_embeds = true`, each `## ` repo section
becomes a titled, colored Discord Embed card — scannable per the project's "readable in
< 2 minutes" principle. Off by default → byte-identical to current behavior.

Constraints: `deliver(self, content: str) -> None` signature is UNCHANGED (S5→S6 string
seam); the adapter MUST NOT import `osspulse.render`/`github`/`summarizer`/`cache`
(AC-6-002 / AC-V2-005-003); embed conversion is derived entirely from the Markdown string.

## Goals / Non-Goals

**Goals:**
- Opt-in `[discord] use_embeds` bool config, default `false`, strict bool-trap validated at load (AC-V4-001-008/008a).
- Embed-mode delivery: one embed per `## ` repo section with title/description/color/footer (AC-V4-001-001).
- Deterministic color per repo via a stable `hashlib` hash — never builtin `hash()` (AC-V4-001-002).
- Enforce Discord limits in code points: ≤10 embeds/request (batch), ≤4096 chars/description (line-split) (AC-V4-001-003/004).
- Plain-text fallback for no-`##`-section digests and unformattable embeds; a run never fails on formatting alone (AC-V4-001-006).
- Preserve the fatal-on-failure, URL-never-leaked, timeout-bounded error path in embed mode (AC-V4-001-007).

**Non-Goals:**
- No change to file/stdout delivery, destination selection semantics, or URL resolution/allowlist.
- No new dependency (stdlib `hashlib`; `httpx` already present), no new trust boundary, no rollback of already-sent requests in a multi-request push.
- No renderer coupling — the embed title reuses the string the renderer already emits.

## Architecture Overview

Ports/adapters (hexagonal-lite) unchanged. All work stays inside the S6 delivery adapter
plus the S1 config loader; the `Delivery` port and pipeline seam are untouched.

- `models.py` — `Config` gains `discord_use_embeds: bool = False` (carried value only).
- `config.py` — `_validate_discord_use_embeds(data)` parses `[discord] use_embeds`
  (bool-trap), wired into `load_config` → `Config(...)`.
- `delivery/discord_delivery.py` — new pure helpers (`_parse_sections`, `_repo_color`,
  `_build_embeds`, `_batch_embeds`) + a `use_embeds` ctor flag + a `deliver()` mode switch
  that reuses the existing POST/error transport with an `{"embeds": [...]}` body.
- pipeline/CLI wiring passes `use_embeds=config.discord_use_embeds` into `DiscordDelivery`
  (INT-V4-001-001).

Dependency direction preserved: adapter → stdlib + httpx + `delivery.errors` only.

## Decisions (ADRs)

### ADR-001 — Section parser: reuse the existing `## `-boundary split
**Context:** Embed mode needs to split the digest into repo sections. `_split_for_discord`
already splits at line-start `## ` for the plain-text path.
**Options:**
| Option | Pros | Cons |
|--------|------|------|
| A. Extract a shared `_parse_sections(content) -> list[{title, body}]` and have both paths use the same boundary logic | One boundary rule, no drift; embed title/body fall straight out | Small refactor of existing split |
| B. New independent regex/splitter for embeds | No touch to existing code | Two boundary rules that can drift (glossary/idempotency risk) |
**Decision:** A — `_parse_sections(content)` returns `list[{"title", "body"}]` where
`title` = header line minus leading `## ` and `body` = the rest of the section; returns
`[]` when there is no `## ` section (drives the fallback). Reusing one boundary rule
matches the memory lesson "reuse existing pattern instead of reinventing" (delivery-6).
**Consequences:** The plain-text splitter and the embed builder agree on what a "section"
is. `[]` is the single, explicit fallback trigger (AC-V4-001-006).

### ADR-002 — Stable color: `hashlib.md5` over the repo slug, not builtin `hash()`
**Context:** Each embed needs a deterministic color from a fixed palette. Python's builtin
`hash()` is salted per process (`PYTHONHASHSEED`) → same repo, different color each run →
violates the project idempotency non-negotiable. (Single genuinely-reasonable approach →
per R8 scope=tiny exception, no options table.)
**Decision:** `_repo_color(slug)` = `int(hashlib.md5(slug.encode()).hexdigest(), 16) %
len(_PALETTE)` indexed into a fixed 6-color palette of Discord-friendly ints (blurple
`0x5865F2`, green, yellow, fuchsia, red, blue). md5 is used purely as a stable
integer digest (no security role), so it is appropriate here.
**Consequences:** Same repo → same palette color on every run/process (AC-V4-001-002).
Color is a member of the fixed palette (AC-V4-001-002b). Never call builtin `hash()`.

### ADR-003 — Embed builder: one embed per section, description capped at 4096 code points
**Context:** Discord caps `description` at 4096 Unicode code points; a section body may
exceed it. The plain-text path already has a two-level (line → char) splitter.
**Options:**
| Option | Pros | Cons |
|--------|------|------|
| A. `_build_embeds` maps each section → embed, splitting an over-limit body by line into multiple embeds (reuse `_split_lines` at limit=4096) | Reuses proven splitter; measures code points via `len(str)` | Multiple embeds share one repo title |
| B. Truncate an over-limit description with an ellipsis | Always 1 embed/repo | Drops content — violates "no item dropped" spirit |
**Decision:** A — `_build_embeds(sections) -> list[embed]`; each embed =
`{title, description: body_chunk[:4096-safe via line split], color, footer:{text}}`.
`footer.text` = `OSS Pulse • {timestamp}` (delivery-time UTC ISO-8601). Over-4096 bodies
are line-split (reuse `_split_lines(body, 4096)`), each chunk a separate embed carrying the
same title/color. Measurement is `len(str)` = code points, not bytes (AC-V4-001-003).
**Consequences:** No content dropped; every `description` ≤4096 code points. Footer
timestamp is intentionally non-idempotent but cosmetic (no dedupe on delivery) — content
determinism unaffected.

### ADR-004 — Batching: sequential POSTs of ≤10 embeds, reusing the existing transport
**Context:** Discord caps 10 embeds/request; a digest may have >10 sections. The existing
`_post_all` loops messages sequentially through `_post_one` with the shared timeout.
**Options:**
| Option | Pros | Cons |
|--------|------|------|
| A. `_batch_embeds(embeds) -> list[list]` chunks into ≤10, then POST each batch via a payload-parameterized `_post_one` (add `json_body=` / embeds variant) | Reuses timeout + URL-never-leaked error path; fatal-at-k semantics identical to plain text | Touches `_post_one` signature |
| B. Separate embed-POST method duplicating the try/except | No touch to `_post_one` | Forks the error path → drift risk (URL leak / timeout) |
**Decision:** A — parameterize the single POST helper to accept the JSON body (content vs
embeds), keep one try/except → `DeliveryError` path. Mirrors the memory lesson "parameterize
the one retry helper, don't fork a parallel POST helper" (v2-006-discussions).
**Consequences:** Batches POST in document order; failure on request _k_ is fatal, earlier
batches already delivered, no rollback (AC-V4-001-004/007). Every request bounded by the
existing `self._timeout`. URL never in any message (composed from status/type only).

### ADR-005 — `deliver()` mode switch + fallback
**Context:** `deliver(content)` must pick embed vs plain-text without changing its
signature, and degrade gracefully.
**Decision:** `deliver()` = if `self._use_embeds`: `sections = _parse_sections(content)`;
if `sections` non-empty → build+batch+POST embeds; **else fall back** to the existing
`_split_for_discord` plain-text path. If `use_embeds` is false → existing path unchanged
(single genuinely-reasonable control flow → no options table per scope=tiny). Fallback is
triggered structurally by `_parse_sections` returning `[]` (no `## ` section, e.g. the
"No new items" doc), so embed formatting alone never fails a run.
**Consequences:** Default (`false`) path is byte-identical to pre-change (AC-V4-001-005).
No-section digests deliver as one `{"content": ...}` POST (AC-V4-001-006).

### ADR-006 — Config: `_validate_discord_use_embeds` mirrors `_validate_delta`
**Context:** `[discord] use_embeds` must be a strict bool, fail-fast at load. `config.py`
already has the `type(v) is not bool` bool-trap pattern (`_validate_delta`,
`_validate_etag_cache`). (Single reasonable approach → no options table.)
**Decision:** Add `_validate_discord_use_embeds(data) -> bool`: read
`data.get("discord", {}).get("use_embeds", False)`; `if type(value) is not bool: raise
ConfigError("discord.use_embeds must be a boolean")`; else return it. Wire into
`load_config` and pass to `Config(discord_use_embeds=...)`.
**Consequences:** `"yes"`/`1` → `ConfigError` before the pipeline runs (AC-V4-001-008);
absent section → `False` (AC-V4-001-008a). Consistent with existing bool-trap guards.

## API Design

_(N/A — CLI tool, no HTTP API. No `openapi.yaml` for this change. The only contract change
is the internal `DiscordDelivery(..., use_embeds: bool = False)` ctor param and the
mode-dependent webhook JSON body — see ADR-004/005.)_

## DB Schema

_(unchanged — no database; state is a JSON file and this CR touches neither state nor cache.)_

## Error Mapping

| Condition | Behavior | AC |
|-----------|----------|----|
| Embed POST non-2xx | `DeliveryError(f"discord delivery failed: HTTP {status} (request {k}/{n})")` — no URL | AC-V4-001-007 |
| Embed POST connection/DNS error | `DeliveryError(f"discord delivery failed: {type(exc).__name__} (request {k}/{n})")` — no `str(exc)` | AC-V4-001-007 |
| Embed POST timeout | `DeliveryError(f"discord delivery timed out after {timeout}s (request {k}/{n})")` | AC-V4-001-007 |
| `[discord] use_embeds` non-bool | `ConfigError("discord.use_embeds must be a boolean")` at load | AC-V4-001-008 |
| No `## ` section / unformattable embed | NOT an error — fall back to plain-text `content` POST | AC-V4-001-006 |

`DeliveryError` → CLI prints `Error: <message>` on stderr, exit non-zero, no stacktrace
(inherited BR-V2-005-004). Webhook URL never appears (T1 preserved).

## Sequence Flows

1. **Embed happy path (≤10 sections, each ≤4096):** `deliver(content)` →
   `_parse_sections` → N sections → `_build_embeds` → N embeds → `_batch_embeds` → 1 batch
   → POST `{"embeds":[...]}` → 2xx → return. (AC-V4-001-001)
2. **Over-length section:** a body >4096 → `_build_embeds` line-splits it into multiple
   same-title embeds, each ≤4096 code points. (AC-V4-001-003)
3. **>10 sections:** `_batch_embeds` chunks into ≤10-embed batches → sequential POSTs in
   document order → all 2xx → return. (AC-V4-001-004)
4. **No-section fallback:** `_parse_sections` returns `[]` → `deliver` routes to
   `_split_for_discord` → plain `{"content":...}` POST(s). (AC-V4-001-006)
5. **POST failure:** request _k_ non-2xx/timeout/conn-error → `DeliveryError` raised
   immediately (earlier batches already sent, no rollback); URL absent. (AC-V4-001-007)

## Edge Cases

Per proposal §Edge Cases (all map to ACs): no-section digest → fallback (006); >4096-char
description → line-split, code points not bytes (003); >10 sections → batch (004); color
determinism vs `hash()` salt (002); opt-out default (005/008a); bool-trap config (008);
POST failure fatal + no URL leak (007). The main correctness trap is ADR-002 (stable hash).

## Performance

Negligible. Embed building is pure in-memory string work over an already-in-memory digest;
md5 over a short slug is trivial. Network cost is unchanged in the common case (≤10 repos =
1 request, same as today's single content POST for a short digest); a >10-repo digest makes
⌈N/10⌉ sequential requests, each timeout-bounded — no worse than the plain-text multi-message
path already does for long digests.

## Security

No new attack surface (STRIDE full model not run — inherited from v2-005, per proposal).
Preserved invariants: (T1) webhook URL never in `DeliveryError` — the embed POST reuses the
status/type-only message composition, never `str(exc)`/`repr(request)`; (T4 DoS-via-hang)
every batched request bounded by the existing explicit `self._timeout`; (T2/T3) URL
resolution + https/allowlist validation unchanged at config load. Embeds carry no new
secret (title/body come from the already-public digest).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dev uses builtin `hash()` for color → non-idempotent | Med | High (breaks project non-negotiable) | ADR-002 explicit; test 2.3 asserts cross-invocation stability; active_concern flagged |
| Byte-vs-code-point confusion in the 4096 split | Med | Med | ADR-003 pins `len(str)`; test 2.4 asserts >4096 bytes-but-≤4096 chars is NOT split |
| Forking the POST helper reintroduces URL leak / drops timeout | Low | High | ADR-004 parameterizes the single `_post_one`; test 2.6 asserts URL absent |
| Fallback not triggered → run fails on no-section digest | Low | Med | ADR-005 structural `[]`-trigger; test 2.5 covers "No new items" doc |

## Implementation Guide

**Recommended order** (follows layering: models → config → adapter helpers → adapter
switch → wiring → tests):
1. `models.py` — add `Config.discord_use_embeds: bool = False` (task 1.1).
2. `config.py` — `_validate_discord_use_embeds` + wire into `load_config`/`Config(...)` (task 1.2).
3. `discord_delivery.py` — `_PALETTE` + `_repo_color(slug)` via `hashlib.md5` (task 1.3, ADR-002).
4. `discord_delivery.py` — `_parse_sections` (extract from `_split_for_discord`'s boundary
   logic, ADR-001) then `_build_embeds` (ADR-003) then `_batch_embeds` (ADR-004) (task 1.4).
5. `discord_delivery.py` — add `use_embeds` ctor param; parameterize `_post_one` to accept
   the JSON body; `deliver()` mode switch + fallback (tasks 1.5/1.6, ADR-004/005).
6. pipeline/CLI — pass `use_embeds=config.discord_use_embeds` (task 1.7, INT-V4-001-001).
7. Tests (module scope) then the gate (tasks 2.x, 3.x).

**Patterns to follow (with file paths):**
- Bool-trap guard: copy `_validate_delta` in `src/osspulse/config.py` (`type(v) is not bool`).
- Section boundary: reuse the `## `-at-line-start rule already in `_split_for_discord`
  (`src/osspulse/delivery/discord_delivery.py`).
- Line/char two-level split: reuse `_split_lines` at `limit=4096` for over-length descriptions.
- Error composition: mirror the existing `_post_one` — message from status code /
  `type(exc).__name__` only, `raise ... from exc`, NEVER `str(exc)`.

**Gotchas:**
- ⚠ Use `hashlib`, NOT builtin `hash()` for color (idempotency non-negotiable) — the #1 trap.
- ⚠ 4096 and 2000 limits are Unicode **code points** (`len(str)`), not UTF-8 bytes.
- ⚠ Do NOT import `osspulse.render` (or github/summarizer/cache) in the adapter — parse the
  Markdown string in-place (AC-6-002 / AC-V2-005-003).
- ⚠ `_parse_sections` returning `[]` is the ONLY fallback trigger — keep it structural, not a flag.
- ⚠ Multi-request push: failure at request _k_ is fatal, no rollback of already-sent batches.
