## 2026-07-13 — v4-digest-ux: in-adapter parse test must use item-line content, not plain body

When the delivery adapter's embed mode relies on in-adapter Markdown re-parse (ADR-003 pattern),
the test sample content **must contain actual `- #id "title" — summary [link](url)` item lines**
to trigger the Option-A embed path. A sample with only free-form body text yields zero parsed
items → falls back to plain-text → embed assertions fail silently (wrong path tested).

Lesson: always build embed-mode test fixtures from live renderer output (or a faithful replica),
not from ad-hoc "Some text here" bodies.

## 2026-07-13 — v4-digest-ux: batching test must account for header embeds

The v4-001 batching test used "11 sections" to get 11 embeds. With Option-A, sections that have
no parseable item lines yield zero items → zero-items fallback → plain text, not embeds. The
correct test for the 10-item + 1-header = 11 embed case needs **10 item lines in one section**
plus the header embed = 11 total → 2 batches. Always count header embeds when designing
batching tests for Option-A delivery.

## 2026-07-13 — v4-digest-ux: dropped_counts nested dict works better than flat dict

`dict[str, dict[str, int]]` (repo → item_type → count) is more flexible than `dict[str, int]`
(repo → total). The renderer sums it for the alert. Future features (per-type breakdown in the
alert) cost nothing to add. At `scope=tiny`, the nested shape has no downside.
