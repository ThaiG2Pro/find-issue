# Glossary — v4-digest-ux

| Term | Definition | Added by (phase) |
|------|------------|------------------|
| max_items_per_type | `[watchlist]` positive-int cap (default 10) on items per `(repo, item_type)`; truncates the OLDEST, keeps the newest by `created_at` desc, applied BEFORE the LLM summarize call | analyst (S2) |
| truncation alert | Renderer line `⚠️ +{count} items not shown (limit: {N})` emitted once per repo section when that repo had items dropped by the cap | analyst (S2) |
| dropped count | Per-repo aggregate number of items removed by truncation; computed in the pipeline, passed to the renderer for the alert | analyst (S2) |
| Option A embed | Discord embed mode where each ITEM is its own embed (title=item title ≤256cp, description=summary, color by item type, footer=`{repo} • {item_type} • OSS Pulse`), preceded by one per-repo header embed | analyst (S2) |
| header embed | The per-repo leading embed in Option A mode: color `0xFEE75C` (yellow), title=repo name, description=`{N} items — {lookback} ngày qua` | analyst (S2) |
| item-type color map | Fixed embed color lookup: issue `0xED4245` (red), release `0x57F287` (green), discussion `0x5865F2` (blurple), header `0xFEE75C` (yellow), plus a fixed fallback for unknown types — no hashing | analyst (S2) |
| retry x7 | `SummarizerConfig.max_retries` default raised 3 → 7, giving backoff 1/2/4/8/16/32/64 s via the existing `base(1.0)*2**attempt` | analyst (S2) |
| _truncate_per_type | Module-private `pipeline.py` step (ADR-001): `(all_items, cap) -> (kept, dropped_counts)`; runs AFTER `_collect_all`+`commit()`, BEFORE `_summarize`; keeps newest N per `(repo,item_type)` by filtering the original list (preserves input order) | architect (S3) |
| dropped_counts | `dict[str,int]` (repo → aggregate dropped) computed by `_truncate_per_type`, passed to `render()` as an additive kw param; only repos with >0 drops get an entry | architect (S3) |
| label→type reverse map | In-adapter lookup (ADR-003) turning renderer `### ` group labels back to item_type for the embed footer: `"Issue mới"→issue`, `"Discussion"→discussion`, `"Release"→release`, `"Khác"→other` | architect (S3) |
| in-adapter re-parse | ADR-003 mechanism: `discord_delivery.py` extends `_parse_sections` to extract per-item title/summary/type from the rendered Markdown — keeps `deliver(content:str)` unchanged and imports no upstream module (v4-001 adapter-internal lesson) | architect (S3) |
| item-line parse | Tolerant parse of `- #{id} "{title}" — {summary} [link]({url})` (em-dash U+2014, all segments optional); zero parseable lines → plain-text fallback | architect (S3) |
