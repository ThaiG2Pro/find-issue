# Tasks — v4-digest-ux (V4-002, CR)

## 1. Retry x7 (summarizer)

- [x] 1.1 Change `SummarizerConfig.max_retries` default `3 → 7`. File: `src/osspulse/summarizer/config.py` _Requirements: AC-V4-002-001_
- [x] 1.2 (No logic change) confirm existing `_call_with_retry` backoff `base * 2**attempt` with default base `1.0` yields 1/2/4/8/16/32/64 s over 7 attempts. File: `src/osspulse/summarizer/client.py` _Requirements: AC-V4-002-002_

## 2. Config — max_items_per_type

- [x] 2.1 Add `Config.max_items_per_type: int = 10`. File: `src/osspulse/models.py` _Requirements: AC-V4-002-005_
- [x] 2.2 Add `_validate_max_items_per_type(watchlist)` — strict positive-int guard (reject bool/float/str, require ≥ 1), default 10; wire into `load_config` + `Config(...)`. File: `src/osspulse/config.py` _Requirements: AC-V4-002-005, AC-V4-002-005b_

## 3. Truncation (pipeline)

- [x] 3.1 Add a pre-summarize truncation step: group `all_items` by `(repo, item_type)`, keep newest `max_items_per_type` by `created_at` desc, compute per-repo dropped counts. Runs AFTER `_collect_all`/`mark_seen`, BEFORE `_summarize`. File: `src/osspulse/pipeline.py` _Requirements: AC-V4-002-003, AC-V4-002-004, AC-V4-002-006_
- [x] 3.2 Pass per-repo dropped counts + cap into `render(...)` (per architect ADR on renderer signature). File: `src/osspulse/pipeline.py` _Requirements: AC-V4-002-007_

- [x] 3.C CHECKPOINT — retry/config/truncation land together; run module tests + lint before UI work.

## 4. Truncation alert (renderer)

- [x] 4.1 Extend `render()` to accept per-repo dropped counts + cap; emit `⚠️ +{count} items not shown (limit: {N})` once per repo section when count > 0; no line when 0/absent (byte-identical to pre-change otherwise). File: `src/osspulse/render/renderer.py` _Requirements: AC-V4-002-007, AC-V4-002-012_

## 5. Option A embeds (delivery)

- [x] 5.1 Add fixed item-type color map (issue `0xED4245`, release `0x57F287`, discussion `0x5865F2`, fallback) + header color `0xFEE75C`. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-V4-002-010_
- [x] 5.2 Rebuild `_build_embeds` for Option A: per repo emit a header embed (`title`=repo, `description`="{N} items — {lookback} ngày qua", color yellow) then one embed per item (`title`=item title truncated ≤ 256 code points, `description`=summary, color by type, `footer.text`="{repo} • {item_type} • OSS Pulse"). File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-V4-002-009, AC-V4-002-011_
- [x] 5.3 Preserve ≤10-embeds/request batching (header + item embeds counted together), ≤4096-char description line-split, and the URL-never-leaked fatal-error path; fall back to plain text when no items / no `##` section. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-V4-002-008, AC-V4-001-003, AC-V4-001-004, AC-V4-001-006_
- [x] 5.4 Feed per-item data (repo, item_type, title, summary) to the adapter per architect ADR (widened seam vs in-adapter parse) WITHOUT importing `osspulse.github`/`summarizer`/`cache`. File: `src/osspulse/pipeline.py`, `src/osspulse/delivery/discord_delivery.py` _Requirements: INT-V4-002-001_

## 6. Tests (module scope)

- [x] 6.1 summarizer: default `max_retries==7`; 7-attempt backoff sequence 1/2/4/8/16/32/64 s via injected sleep. File: `tests/test_summarizer.py` _Requirements: AC-V4-002-001, AC-V4-002-002_
- [x] 6.2 config: `max_items_per_type` default 10; `0`/`-1`/`"10"`/`true`/`2.5` → `ConfigError`. File: `tests/test_config.py` _Requirements: AC-V4-002-005, AC-V4-002-005b_
- [x] 6.3 pipeline: 15 issues + cap 10 → 10 newest summarized, 5 dropped, dropped-count≥5; exactly-N → 0 dropped; `mark_seen` gets full set. File: `tests/test_pipeline.py` _Requirements: AC-V4-002-003, AC-V4-002-004, AC-V4-002-006_
- [x] 6.4 renderer: dropped count 5 → one `⚠️ +5 items not shown (limit: 10)` line; zero → byte-identical output. File: `tests/test_renderer.py` _Requirements: AC-V4-002-007, AC-V4-002-012_
- [x] 6.5 embeds: header + per-item embeds shape/footer/description; type→color map incl. fallback; title >256 truncated (code points); 10 items+header=11 embeds → ≥2 requests ≤10; no-items → plain-text fallback. File: `tests/test_discord_delivery.py` _Requirements: AC-V4-002-008, AC-V4-002-009, AC-V4-002-010, AC-V4-002-011_

## 7. Gate

- [x] 7.C CHECKPOINT (final) — `openspec validate v4-digest-ux --changes` passes; module-scope test + lint/static-analysis green; digest byte-identical when no truncation + embeds off.
