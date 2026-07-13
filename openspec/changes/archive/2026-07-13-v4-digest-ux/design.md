## Sketch — Gap Analysis

**No critical gaps found.** All twelve ACs (AC-V4-002-001..012 + 005b) map to existing
seams; the two seam-widening flags from the analyst (`_handoff.md` §2, `INT-V4-002-001`,
`AC-V4-002-012`) are resolved here as ADR-002 (renderer) and ADR-003 (embeds).

Sketch inventory (4 bundled tweaks, `scope=tiny`, `rigor=lite`):

| Tweak | Touch point | AC(s) | Seam impact |
|-------|-------------|-------|-------------|
| Retry x7 | `summarizer/config.py` default | 001, 002 | none (default value only) |
| Top-N truncate | `pipeline.py` new pre-summarize step | 003, 004, 006 | none (internal helper) |
| Truncation config | `models.py` + `config.py` validator | 005, 005b | none (mirrors `lookback_days`) |
| Truncation alert | `render/renderer.py` | 007, 012 | **`render()` signature widens** (ADR-002) |
| Option A embeds | `delivery/discord_delivery.py` | 008, 009, 010, 011 | **in-adapter parse extends** (ADR-003); `deliver(content:str)` UNCHANGED |

**Two flagged decisions, resolved together (per `_handoff.md` §3):**
- **Renderer counts (`AC-V4-002-012`)** → ADR-002: add an optional keyword param to
  `render()`. Renderer stays a pure transform; no upstream import.
- **Per-item embed data (`INT-V4-002-001`)** → ADR-003: **in-adapter re-parse** of the
  rendered Markdown. The hard constraint (`deliver(content: str)` MUST NOT change; no
  `osspulse.github`/`summarizer`/`cache` import) forbids the widened-seam alternative, and
  in-adapter parse is exactly the v4-discord-embeds memory lesson ("payload-shape CR stays
  inside the adapter"). The rendered Markdown already carries every field the embed needs
  (repo + lookback in the `## ` header, item_type via the `### ` group label, title/summary
  in the item line) — no upstream data is required.

No contradiction with prior specs: v4-discord-embeds (`AC-V4-001-*`) is MODIFIED, not
broken — its batching (≤10/req), description line-split (≤4096), title truncation (≤256
code points), and URL-never-leaked error path (T1) are all preserved and reused.

## Context

OSS Pulse ships a working V1→V3 pipeline (S1→S7, ports/adapters). This CR is four small,
independent UX tunings observed after v4-discord-embeds shipped: retries too shallow for
free-tier 429 bursts; unbounded per-type volume breaks the "readable in < 2 min" principle
and wastes LLM tokens; silent truncation is dishonest; and one-embed-per-repo is still a
wall of text. All four are opt-in-safe with backward-compatible defaults.

Key constraints (locked at SPEC LOCK): truncation MUST run **before** summarize (token
cost); `mark_seen` MUST still record the full fetched set (idempotency, BR-V2-001-002);
the `Delivery` port `deliver(content: str)` MUST NOT change; `discord_delivery.py` MUST NOT
import `osspulse.github`/`summarizer`/`cache`; with no truncation + embeds off the output
MUST be byte-identical to today.

## Goals / Non-Goals

**Goals:**
- Raise the retry ceiling via a single default change (no retry-logic reshape).
- Cap `(repo, item_type)` volume pre-summarize, keeping the newest N, with a per-repo alert.
- Reshape the opt-in Discord embed body to one-embed-per-item + per-repo header embed,
  entirely inside the adapter, with a legacy fallback.

**Non-Goals:** (per proposal §Non-Goals — all `_(unchanged)_`)
- Batching LLM calls, GitHub fetch logic, state/ETag logic, new destinations, and a
  per-item "not shown" enumeration are all out of scope.

## Architecture Overview

Linear pipeline + ports/adapters is unchanged. Two new internal transforms and one adapter
reshape; no new port, no new module, no new dependency.

```
_collect_all ──► [NEW] _truncate_per_type ──► _summarize ──► render(…, dropped_counts, cap) ──► deliver(content:str)
   (mark_seen         (drop oldest,             (only              (alert line per repo)         │
    FULL set)          count dropped/repo)       survivors)                                       ▼
                                                                              DiscordDelivery: in-adapter
                                                                              Markdown re-parse → per-item embeds
```

- **`pipeline.py`** gains one pure helper `_truncate_per_type(all_items, cap)` called
  AFTER `_collect_all` (so `mark_seen` already recorded the full set) and BEFORE
  `_summarize`. Returns `(kept_items, dropped_counts: dict[str, int])`.
- **`render/renderer.py`** — `render()` gains two optional keyword params
  (`dropped_counts`, `max_items_per_type`); still pure, still imports only `models` + stdlib.
- **`delivery/discord_delivery.py`** — `_build_embeds` is rebuilt to parse each section body
  into items and emit header+item embeds; `deliver(content: str)` signature untouched.
- **`config.py` / `models.py`** — `[watchlist] max_items_per_type` parsed/validated
  (mirrors `lookback_days`), carried on `Config.max_items_per_type`.
- **`summarizer/config.py`** — `max_retries` default `3 → 7`.

Dependency boundaries: no adapter imports another; renderer/delivery gain no upstream
imports; `pipeline.py` remains the only multi-stage importer.

## API Design

_(unchanged — CLI tool, no HTTP API; no `openapi.yaml` per R5.)_ Internal stage contracts
change as follows:

- `render(items, *, lookback_days, dropped_counts: dict[str, int] | None = None, max_items_per_type: int | None = None) -> str`
  — additive keyword params, default `None` ⇒ no alert lines ⇒ byte-identical output.
- `_truncate_per_type(all_items: list[RawItem], cap: int) -> tuple[list[RawItem], dict[str, int]]`
  — new module-private pipeline helper.
- `Delivery.deliver(content: str) -> None` — **UNCHANGED** (hard constraint).

## DB Schema

_(unchanged — no database in V1; no state-shape change. `mark_seen` still records the full
fetched set, so the JSON/Upstash seen-record is unaffected by truncation.)_

## ADRs

### ADR-001 — Truncate in a dedicated pre-summarize pipeline step, keep-newest by filtering

**Context:** AC-V4-002-003/004/006 require capping each `(repo, item_type)` group to N
newest by `created_at` desc, dropping the oldest, BEFORE the LLM call, while `mark_seen`
still records the full set and the render order stays deterministic.

| Option | Pros | Cons |
|--------|------|------|
| A. New `_truncate_per_type` step between `_collect_all` and `_summarize` | Clear seam; `mark_seen` (inside `_collect_all`) already ran on full set; token-cost correctness structural | one extra pass over items |
| B. Truncate inside `_collect_all` per repo | one loop | risks truncating BEFORE `mark_seen` records full set → breaks idempotency invariant |
| C. Truncate inside `_summarize` | co-located with LLM call | dropped items already passed the summarize boundary → easy to accidentally pay tokens; violates "before summarize" |

**Decision: Option A.** A standalone step placed after `_collect_all` returns and before
`_summarize` makes the "full set recorded, then truncate, then summarize" ordering a
structural invariant, not a comment (memory lesson v2-001: enforce ordering structurally).
Algorithm keeps determinism: for each `(repo, item_type)` group, select the survivor set =
the N items with the greatest `created_at` (ISO-8601 UTC strings sort correctly
lexicographically; `sorted(..., key=created_at, reverse=True)[:cap]`); then rebuild
`kept_items` by **filtering the original `all_items` in place** (keep iff in survivor set)
so surviving items retain their original relative order — the renderer emits input order, so
a no-truncation run is byte-identical. `dropped_counts[repo]` = original count − survivors,
aggregated across item types, recorded only for repos with >0 drops.

**Consequences:** Dropped items never reach `_summarize` (zero LLM cost). Ties on identical
`created_at` are broken by original order (stable filter). `mark_seen` unaffected.

### ADR-002 — Renderer learns dropped counts via an additive keyword param

**Context:** AC-V4-002-007/012 — the renderer must emit `⚠️ +{count} items not shown
(limit: {N})` once per repo with drops, but it is a pure transform and cannot reconstruct
dropped items (they are gone). It needs the per-repo counts + the cap as inputs, and a
no-truncation run must be byte-identical (BR-V4-002-005).

| Option | Pros | Cons |
|--------|------|------|
| A. Add optional kw params `dropped_counts: dict[str,int] \| None`, `max_items_per_type: int \| None` | Backward-compatible default `None`; pure; no import; minimal | widens `render()` sig (AC-5-001) — acceptable, additive only |
| B. New metadata dataclass passed alongside items | typed | new type + wiring for a 2-field payload = over-engineering at `scope=tiny` |
| C. Attach counts to items / parse downstream | no sig change | renderer can't attach to dropped items; parsing back = fragile |

**Decision: Option A.** Additive keyword params with `None` defaults keep every existing
`render(items, lookback_days=…)` call byte-identical and the transform pure (only
`models` + stdlib imported). The alert line is appended immediately after the
`## {repo} — {lookback} ngày qua` header line, exact form `⚠️ +{count} items not shown
(limit: {N})` (no blockquote prefix — matches the locked AC-V4-002-007 scenario verbatim),
emitted only when `dropped_counts.get(repo, 0) > 0`.

**Consequences:** `MarkdownDigestRenderer.render` adapter method mirrors the new params.
`pipeline.py` passes `dropped_counts=…, max_items_per_type=config.max_items_per_type`.
`DigestRenderer` port doc widens but stays structurally satisfied (kwargs have defaults).

### ADR-003 — Per-item embeds are built by in-adapter re-parse of the rendered Markdown (no widened seam)

**Context:** INT-V4-002-001 / AC-V4-002-009/010/011 — Option A needs per-item
`repo / item_type / title / summary`. The `deliver(content: str)` port MUST NOT change and
`discord_delivery.py` MUST NOT import `osspulse.github`/`summarizer`/`cache`. The analyst
flagged re-parse as fragile and left the mechanism to the architect (search-first: no new
lib helps — this is a format-mapping decision, Build/Extend the existing `_parse_sections`).

| Option | Pros | Cons |
|--------|------|------|
| A. Widen the delivery seam to carry a structured item list | no parsing fragility | **VIOLATES the hard constraint** (port must not change); contradicts v4-001 string-only-seam lesson; forces pipeline↔delivery coupling |
| B. In-adapter re-parse of the rendered Markdown (extend `_parse_sections`) | port unchanged; zero upstream import; reuses the v4-001 adapter-internal pattern; every field is already in the Markdown | parser is coupled to the renderer line format → needs a robust fallback |
| C. Import upstream item models into the adapter | typed data | **VIOLATES the no-import boundary** |

**Decision: Option B.** The constraint forecloses A and C; B is also the correct reuse of
the v4-discord-embeds memory lesson. The rendered Markdown carries everything:
- `repo` + `lookback` ← the `## {repo} — {lookback} ngày qua` header (already parsed by
  `_parse_sections`; split repo at `" —"`, take the integer before `"ngày qua"` for lookback).
- `item_type` ← the `### {label}` group header via a fixed **label→type reverse map**
  (`"Issue mới"→issue`, `"Discussion"→discussion`, `"Release"→release`, `"Khác"→other`).
- `title` / `summary` / (url) ← the item line `- #{id} "{title}" — {summary} [link]({url})`
  parsed with a tolerant regex (quoted title between the first pair of `"`; summary between
  ` — ` (em-dash U+2014) and ` [link](` or EOL; segments are all optional per `_build_item_line`).

Embed assembly per repo section: one **header embed** first (`color=0xFEE75C`,
`title=repo`, `description="{N} items — {lookback} ngày qua"`, N = parsed item count shown —
matches locked AC-V4-002-009; note this follows the SPEC's header description, not the
looser "3 issues • 1 release" phrasing in the request brief), then one **item embed** per
parsed item (`title`=item title truncated to ≤256 code points, `description`=summary,
`color`=item-type map, `footer.text="{repo} • {item_type} • OSS Pulse"`). Color map is a
**fixed dict** (issue `0xED4245`, release `0x57F287`, discussion `0x5865F2`, fallback for
any other incl. `other`) — no `hash()`, no `hashlib`, no PYTHONHASHSEED risk (simpler than
v4-001's palette; ADR supersedes the v4-001 `_color_for_repo`/`_EMBED_PALETTE` approach).

**Fallback (mandatory, AC-V4-001-006):** if `_parse_sections` finds no `## ` section, OR
per-item parsing across all sections yields **zero** parseable item lines (format drift /
"No new items" doc), fall back to the existing plain-text `{"content": …}` path. This keeps
"formatting alone never fails a run".

**Consequences:** Parser is coupled to the renderer's line format — a gotcha called out in
§Implementation Guide (change both together). The per-repo truncation alert line
(`⚠️ +N items not shown …`) does not match `- #` so it is ignored by the item parser (not
rendered as an embed); embed readers rely on the header count. "Khác"-bucket items lose
their original item_type in the Markdown → footer shows `other` + fallback color (never
dropped, parallels the renderer Khác rule). Existing `_split_description` (≤4096 line-split),
`_batch_embeds` (≤10/req), and `_post_one_embed` (T1 URL-safe error) are reused unchanged.

### ADR-004 — Retry ceiling is a config-default change only (3 → 7)

**Context:** AC-V4-002-001/002 — ride longer free-tier 429 windows. `scope=tiny`; only one
approach is genuinely reasonable (per R8 tiny exception), but the analyst already weighed one
alternative, recorded here.

| Option | Pros | Cons |
|--------|------|------|
| A. Bump `SummarizerConfig.max_retries` default `3 → 7` | zero logic change; 1/2/4/8/16/32/64 s falls out of existing `base*2**attempt`; `Retry-After` + skip-log-continue unchanged | ~127 s worst-case wait per stuck item (acceptable, still skip-continues) |
| B. Explicit delay list `[1,2,4,8,16,32,64]` in config | delays visible | needless code churn — reshapes `_call_with_retry` for an identical sequence |

**Decision: Option A.** Only the default literal changes; the existing exponential-backoff
formula and exhaustion→skip-log-continue behavior in `_call_with_retry` are untouched. An
optional `[llm] max_retries` override MAY be surfaced but is not required by any AC — keep
the default-only change at `scope=tiny`.

**Consequences:** Pre-existing "always-fails 429" tests that assert 3 retries must update to
7 (memory lesson v3-llm-throttle: retry-ceiling changes break always-fails tests — flagged
for developer). Worst-case per-item stall grows to ~127 s but the run still completes via
skip-log-continue.

## Error Mapping

_(unchanged — no new error classes.)_ `ConfigError` on bad `max_items_per_type`
(non-int/bool/float/str or `< 1`), raised at load, mirrors the `lookback_days` guard →
CLI maps to `Error: <msg>` exit 1. Embed POST failures keep the existing status/type-only
`DeliveryError` (T1: webhook URL never in the message). Retry exhaustion keeps
skip-log-continue (no propagation).

## Sequence Flows

**Truncation + alert (pipeline → renderer):**
1. `_collect_all` returns `all_items` (full set already `mark_seen`-recorded per repo).
2. `_truncate_per_type(all_items, config.max_items_per_type)` → `(kept, dropped_counts)`.
3. `_summarize(config, kept)` → survivors only (dropped items never sent to LLM).
4. `render(summarized, lookback_days=…, dropped_counts=dropped_counts, max_items_per_type=cap)`
   → per-repo alert line where count > 0.
5. `deliver(digest)`.

**Option A embeds (adapter-internal):**
1. `deliver(content)` with `use_embeds=True` → `_parse_sections(content)`.
2. For each section: parse header (repo, lookback) + `### ` groups (label→item_type) + item
   lines (title, summary). Build header embed + item embeds.
3. If total parsed items == 0 (or no `## ` section) → plain-text fallback.
4. `_batch_embeds` (≤10) → `_post_embed_batches` → `_post_one_embed` (T1-safe).

## Edge Cases

Covered by proposal §Edge Cases 1–9. Design-specific handling:
- **Group exactly at N** (EC1, AC-004): filter keeps all → `dropped_counts[repo]` has no
  entry → no alert line (off-by-one guard via `> 0` check).
- **Title > 256 code points** (EC2, AC-011): `title[:256]` (code points, `len(str)`).
- **Config bool/float/str/≤0** (EC3, AC-005b): strict `type(v) is not int` + `< 1` → `ConfigError`.
- **Unknown item_type / Khác** (EC7, AC-010): fallback color; footer `item_type=other`; never dropped.
- **>10 embeds** (EC8, AC-008): 10 items + 1 header = 11 → 2 batched requests via reused `_batch_embeds`.
- **No truncation + embeds off** (EC9): `dropped_counts=None`/empty ⇒ no lines; embeds off ⇒ plain text ⇒ byte-identical.

## Performance

Truncation reduces LLM calls (fewer items summarized) → net token savings, the feature's
intent. Per-item embeds increase embed count → more sequential POSTs only when a repo
exceeds 10 items (batched, ≤10/req); timeout bound per request unchanged. Truncation is one
extra O(n log n) group-sort over already-in-memory items — negligible.

## Security

_(no new trust boundary — STRIDE full model correctly skipped, `security.stride_analysis=auto`.)_
T1 (webhook URL leak) is **preserved**: the reshaped embed path reuses `_post_one_embed`,
which composes `DeliveryError` from HTTP status / exception type name only — never
`str(exc)`/URL. No new secret, input source, auth, PII, or payment surface. Truncation and
retry are deterministic functions of input+config (idempotency non-negotiable held); color
map is a fixed dict (no `hash()`).

## Risk Assessment

| Risk | → Mitigation |
|------|--------------|
| Truncate-after-summarize regression (pays for dropped) | ADR-001 structural placement; pipeline test asserts summarizer sees only survivors |
| Wrong `created_at` sort keeps wrong items | ISO-8601 UTC lexicographic desc is correct; test with 15 items asserts newest 10 kept |
| Alert line perturbs byte-identical output | `None`/empty `dropped_counts` short-circuits; renderer test asserts byte-identical when zero |
| Embed parser fragility (renderer format drift) | mandatory zero-items fallback to plain text; parser + renderer format changed together (gotcha) |
| Retry-ceiling test breakage | flagged for developer (v3-llm-throttle lesson): update always-fails 429 tests 3→7 |
| Embed count off-by-one (header+items > 10) | reuse v4-001 `_batch_embeds`; test 10 items+header=11 → ≥2 requests ≤10 |
| T1 URL leak in reshaped POST | reuse `_post_one_embed` unchanged |

## Implementation Guide

**Recommended order** (follows tasks.md; foundational → domain → interface):
1. **Retry default** — `summarizer/config.py` `max_retries: int = 7` (ADR-004). Trivial.
2. **Config** — `models.py` `Config.max_items_per_type: int = 10`; `config.py`
   `_validate_max_items_per_type(watchlist)` mirroring `_validate_lookback` (strict int,
   `≥ 1`, bool-trap `type(v) is not int`), wire into `load_config` + `Config(...)`.
3. **Truncation** — `pipeline.py` `_truncate_per_type(all_items, cap)` (ADR-001); call it
   after `_collect_all` + `commit()`, before `_summarize`; pass counts to `render`.
4. **CHECKPOINT 3.C** — retry/config/truncation land together; module tests + lint.
5. **Renderer** — `render/renderer.py` additive kwargs + alert line (ADR-002).
6. **Embeds** — `delivery/discord_delivery.py`: fixed color map + label→type reverse map;
   rebuild `_build_embeds` (header + per-item) with tolerant item-line parse; keep
   `_split_description`/`_batch_embeds`/`_post_one_embed`; add zero-items fallback (ADR-003).
7. **Tests** (module scope) + **CHECKPOINT 7.C** (final): `openspec validate`, module tests
   + lint green, byte-identical no-op verified.

**Patterns to follow (with file paths):**
- Config validator: copy `_validate_lookback` in `src/osspulse/config.py` verbatim in shape.
- Ordering-is-correctness: enforce truncate-after-mark_seen structurally (v2-001 lesson) —
  `_truncate_per_type` is a separate step, not a branch inside `_collect_all`.
- Adapter-internal parse: extend `_parse_sections` in
  `src/osspulse/delivery/discord_delivery.py` (v4-001 lesson: stay inside the adapter).
- Determinism: fixed color dict, no `hash()`/`hashlib` (supersede `_color_for_repo`).

**Gotchas:**
- The embed item parser is coupled to `_build_item_line`'s format
  (`- #{id} "{title}" — {summary} [link]({url})`, em-dash U+2014, segments optional). If the
  renderer line format ever changes, update the parser in the same change; the zero-items
  fallback is the safety net, not a license to skip the test.
- `dropped_counts` must key on `repo` (the `RawItem.repo` string), matching the renderer's
  `item.raw.repo` grouping key — mismatched keys silently drop the alert.
- Header embed `{N}` = items **shown** (post-truncation), parsed from the Markdown, not the
  pre-truncation count.
- Bump the always-fails-429 summarizer test expectation 3 → 7 (else it fails on the default).
- Remove/replace the v4-001 `_EMBED_PALETTE` + `_color_for_repo` (repo-hash color) — Option A
  colors by item type, not repo.
