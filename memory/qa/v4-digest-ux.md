## 2026-07-13 — v4-digest-ux: truncation alert byte-identical guard pattern

When a renderer gains optional kw params with `None` defaults for a "no-op when absent"
contract, verify THREE forms: `None`, empty dict `{}`, and inner dict with all-zero values
(`{'repo': {}}`). All three must be byte-identical to baseline. The renderer guard
`if dropped_counts and max_items_per_type is not None:` correctly handles all three because
empty dict is falsy and `{}` short-circuits before summing. One test covers None, one covers
empty — add a zero-value-inner test to be thorough.

## 2026-07-13 — v4-digest-ux: parser-renderer coupling gotcha (in-adapter re-parse)

When an adapter re-parses rendered Markdown (ADR-003 pattern), document the coupling as a
"change-both-together" gotcha in the handoff. The safety net (zero-items fallback to plain
text) is correct but must not be treated as an excuse to skip the paired update. Add a test
that runs the parser against live renderer output (`test_parses_items_from_section`) — this
acts as a format-drift tripwire.

## 2026-07-13 — v4-digest-ux: test replacement pattern for fallback-triggered scenarios

When a delivery adapter adds a zero-items fallback (plain-text if no parseable items), any
pre-existing test that used section-level content (no `- #` item lines) will now trigger the
fallback instead of the embed path. Replace such tests with content that actually has parseable
item lines. The tell: test used 11 sections but got plain-text post. New test: 10 item lines +
1 header = 11 embeds → 2 requests.
