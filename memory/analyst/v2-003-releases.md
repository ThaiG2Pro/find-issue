## 2026-07-06 — v2-003-releases: when the pipeline was built item_type-agnostic, a "new source" feature is collector-only — do NOT write a no-op renderer delta
The kickoff task for adding a new content source (Releases) listed a digest-renderer MODIFIED delta as
an output. But the renderer, state store, delta filter and summarizer had all been built
`item_type`-agnostic in prior changes: the renderer already shipped `"release"` in `GROUP_ORDER` with a
`Release` label (living AC-5-006/AC-5-011), the state store keys on `repo+item_type+item_id`, the
v2-001 delta filter filters any type, and the summarizer caps input at 8000 chars for any item. So the
real spec delta collapsed to the Collector (fetch+map the new source) plus ONE pipeline-wiring line.
Lesson: before accepting a per-stage delta list from the kickoff note, READ the living spec + the actual
stage code to see which stages are already generic. Writing a MODIFIED renderer delta here would either
be a no-op (rejected by `openspec validate`, which requires a MODIFIED requirement to differ) or would
restate existing behavior as if new — both wrong. Document the deliberate omission as a Non-Goal + a
BR + a decisions.jsonl "rejected" line so the gate/architect understand it was intentional, not missed.

## 2026-07-06 — v2-003-releases: a source whose "inclusion" field differs from the API's "ordering" field breaks early-stop pagination
Issues collection early-stops created-desc when an item's `created_at` < cutoff, which is correct
because `created_at` is BOTH the ordering key and the inclusion key. Releases broke that coupling: the
`/releases` endpoint orders by `created_at` but the natural inclusion field is `published_at` (a release
can be created long before it is published). So created-desc early-stop can stop before reaching a
recently-published-but-old-created release and silently drop it. Whenever a new paginated source's
inclusion predicate is a DIFFERENT field than the sort field, flag the early-stop-vs-full-page-filter
tradeoff explicitly (here RISK-002, deferred to the architect) rather than copying the issue path's
early-stop blindly. Generalizes to any "list newest-by-X, but I care about Y" collector.
