## ADDED Requirements

### Requirement: A per-repo truncation notice is rendered when items were dropped
The renderer SHALL emit a per-repo truncation notice whenever items were dropped from that
repo by the pipeline's per-type cap (see scheduler-cli "truncates each item-type group per
repo"). The notice SHALL appear within that repo's `## {repo}` section as a line of the exact
form `⚠️ +{count} items not shown (limit: {N})`
where `{count}` is the aggregate number of items dropped for that repo and `{N}` is the
configured `max_items_per_type`. The notice SHALL appear once per repo section (for repos
with a non-zero dropped count) and SHALL NOT appear for repos where nothing was truncated —
so a digest produced with no truncation is byte-identical to the pre-change output. The
renderer SHALL receive the per-repo dropped counts and the cap as inputs; it SHALL remain a
pure transform (no I/O) and SHALL NOT reconstruct dropped items (they are gone before
rendering). When a repo's dropped count is absent or zero, no notice line is emitted.

> ACs: AC-V4-002-007 [CONFIRMED], AC-V4-002-012 [ASSUMED]
> Business rules: BR-V4-002-005
> Risk: RF-1 (determinism / idempotency)

#### Scenario: A repo with dropped items shows the truncation notice (AC-V4-002-007) [CONFIRMED]
- **WHEN** the renderer is given repo `alpha/a` with a dropped count of `5` and cap `N = 10`
- **THEN** the `## alpha/a` section contains exactly one line `⚠️ +5 items not shown (limit: 10)`

#### Scenario: A repo with no truncation shows no notice and output is unchanged (AC-V4-002-012) [ASSUMED]
- **WHEN** the renderer is given items with no repo having a dropped count (all zero/absent)
- **THEN** no `⚠️` notice line appears anywhere and the output is byte-identical to the pre-change renderer output for the same items
