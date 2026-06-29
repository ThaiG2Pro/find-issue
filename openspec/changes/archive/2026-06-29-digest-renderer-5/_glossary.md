# Glossary — digest-renderer-5

Shared, append-only domain/technical glossary. Every phase adds rows. Keep **Phase** as the LAST column.

| Term | Definition | Phase |
|------|------------|-------|
| Digest Renderer | S5 stage: pure transform `render(items: list[SummarizedItem], *, lookback_days: int) -> str` producing the Markdown digest string | S1 |
| DigestRenderer (port) | New role-named Protocol in `osspulse.ports` for the renderer; concrete adapter in `src/osspulse/render/` (ports/adapters pattern) | S1 |
| Pure transform | The renderer's defining contract: no file/network/LLM/state I/O, no upstream imports; `output = f(input)` — depends only on `items` + `lookback_days` | S1 |
| Deterministic output | Same `items` + `lookback_days` → byte-for-byte identical Markdown; underpins idempotency (PROJECT_SPEC §7) | S1 |
| Repo section | A `## {repo} — {lookback_days} ngày qua` block; emitted only for repos with ≥1 item; repos ordered alphabetically (case-insensitive) | S1 |
| Item-type group | A `### {Label} ({count})` block within a repo; fixed order Issues → Discussions → Releases → Khác; emitted only if non-empty | S1 |
| Group label | `Issue mới` (issue) / `Discussion` (discussion) / `Release` (release) / `Khác` (unknown type) — per PROJECT_SPEC §4 wording | S1 |
| Item line | `- #{item_id} "{title}" — {summary} [link]({url})`; degrades gracefully when title/url/summary are empty | S1 |
| No-new-items doc | The non-empty Markdown returned for empty input: a title + "No new items in the last N days"; never an empty/ambiguous string | S1 |
| Khác bucket | Trailing `### Khác (N)` group for items whose `item_type` is not issue/discussion/release — ensures no item is dropped | S1 |
| lookback_days (param) | Plain int param to `render(...)`; the ONLY source of the window in the header — renderer never reads Config/state for it | S1 |
| SummarizedItem | Input model `SummarizedItem(raw: RawItem, summary: str)` from S4 `summarize_items()`; the only data the renderer consumes | S1 |
| GROUP_ORDER | Module constant `["issue", "discussion", "release"]` fixing item-type group emission order; `Khác` (unknown) always trails it | S3 |
| GROUP_LABELS | Module dict mapping group key → header label (`issue`→`Issue mới`, `discussion`→`Discussion`, `release`→`Release`, `__other__`→`Khác`) | S3 |
| `__other__` bucket key | Internal grouping key for any `item_type` not in GROUP_ORDER; renders under the `### Khác` trailing group; never dropped | S3 |
| MarkdownDigestRenderer | Concrete adapter class (`src/osspulse/render/renderer.py`) implementing the `DigestRenderer` Protocol structurally; `render()` delegates to the pure free `render()` function | S3 |
| `_build_item_line` | Module-private composable function building one item line with independent omit-branches for empty title/url/summary; never raises | S3 |
| dict-of-dict grouping | Determinism strategy: `dict[repo] -> dict[group_key] -> list[item]` using Python insertion order; repos sorted by `str.lower`, items kept in input order, NO `set` used | S3 |
| `_item_lines()` helper | Test helper (`tests/test_render_defensive.py`, `test_render_determinism.py`) filtering `result.splitlines()` to only lines starting with `- #`; isolates item-line assertions from the em-dash in repo headers | S4 |
| em-dash separator | U+2014 `—` used in `_build_item_line` before the summary segment (`— {summary}`) and in the repo header (`## {repo} — N ngày qua`); tests assert on item lines only when checking for absence (AC-5-017) | S4 |
