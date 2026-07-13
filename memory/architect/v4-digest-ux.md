# architect memory — v4-digest-ux

## 2026-07-13 — v4-digest-ux: a frozen string-seam port turns "adapter needs richer data" into a settled decision, not an ADR debate
When the delivery/render port is a frozen string seam (`deliver(content: str)`) AND the CR
forbids importing upstream modules, the analyst's "widened-seam vs in-adapter-parse" question
is already answered: only in-adapter parse is compliant. Don't stage it as a genuine 2-way ADR
trade-off — state the constraint, show the widened-seam option is *foreclosed* (not merely
worse), and reuse the prior "payload-shape CR stays inside the adapter" lesson. The rendered
Markdown almost always already carries every field the adapter needs (header line = repo/meta,
group header = type, item line = title/summary); the only real risk is parser↔renderer format
coupling, mitigated by a mandatory zero-parsed-items fallback to the old path.

## 2026-07-13 — v4-digest-ux: "surface counts to a pure transform" = additive kw param with None default, never a new payload type
A pure renderer/transform that must emit something about data it no longer has (dropped/
truncated items) needs the aggregate passed IN. At tiny scope the right shape is an additive
keyword param defaulting to `None`/empty — it keeps every existing call byte-identical (the
determinism/no-op invariant) and the transform pure. A dedicated metadata dataclass is
over-engineering for a 1–2 field payload. Watch the KEY: the count dict must key on the exact
same identity the transform groups by, or the surfaced line silently vanishes.

## 2026-07-13 — v4-digest-ux: truncation-before-cost must be a SEPARATE pipeline step, and it inverts the color-determinism trap
Two reusable points from bundling truncation + a re-color into one CR: (1) a "cap volume before
the expensive call (LLM)" requirement must be its own step placed between collect and the
expensive stage — not a branch inside the collector — so "record full set → truncate → pay only
for survivors" is structural (echoes v2-001 ordering-is-correctness); keep the survivor set by
FILTERING the original list, not re-sorting it, to preserve input order for a byte-identical
no-op. (2) When a later CR revisits an earlier hash-based color (v4-001 `hashlib` palette), a
fixed lookup map is strictly simpler and kills the PYTHONHASHSEED determinism concern entirely —
prefer a fixed enum/dict over any hash when the key space is small and closed.
