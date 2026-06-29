# digest-renderer Specification

## Purpose
TBD - created by archiving change digest-renderer-5. Update Purpose after archive.
## Requirements
### Requirement: Render a list of SummarizedItem into a Markdown digest string
The Digest Renderer SHALL expose a pure function `render(items: list[SummarizedItem],
*, lookback_days: int) -> str` (behind a new `osspulse.ports.DigestRenderer` Protocol)
that transforms the summarized items into a single Markdown document and returns it as
a `str`. The function SHALL be a **pure transform**: it SHALL NOT perform any file,
network, LLM, or state I/O, and SHALL NOT import from `osspulse.github`,
`osspulse.state`, `osspulse.summarizer`, or `osspulse.cache`.

> ACs: AC-5-001 [CONFIRMED], AC-5-002 [CONFIRMED], AC-5-003 [CONFIRMED]
> Business rules: BR-5-001, BR-5-002
> Integration: INT-5-001

#### Scenario: A non-empty item list renders to a Markdown string (AC-5-001) [CONFIRMED]
- **WHEN** `render(items, lookback_days=7)` is called with a list containing at least one `SummarizedItem`
- **THEN** the return value is a non-empty `str` containing a `## {repo}` section for each repo present and a `- #{item_id}` line for each item

#### Scenario: The renderer performs no I/O (AC-5-002) [CONFIRMED]
- **WHEN** `render(items, lookback_days=7)` is called
- **THEN** no file is written, no network/LLM/Redis call is made, and no state is read or mutated — the result depends only on `items` and `lookback_days`

#### Scenario: The renderer imports no upstream pipeline modules (AC-5-003) [CONFIRMED]
- **WHEN** the renderer module is imported
- **THEN** it does NOT import `osspulse.github`, `osspulse.state`, `osspulse.summarizer`, or `osspulse.cache` (verified by static import inspection)

### Requirement: Deterministic output — output is a pure function of input
For a given `items` list and `lookback_days`, the renderer SHALL always produce the
**byte-for-byte identical** Markdown string. Repos SHALL be ordered alphabetically by
`repo` (case-insensitive, stable). Within a repo, item-type groups SHALL appear in the
fixed order **Issues → Discussions → Releases** (then any other types). Within a group,
items SHALL be rendered in **input order** (preserving the upstream ordering).

> ACs: AC-5-004 [CONFIRMED], AC-5-005 [CONFIRMED], AC-5-006 [CONFIRMED], AC-5-007 [CONFIRMED]
> Business rules: BR-5-003, BR-5-004
> Risk: RF-1 (determinism / idempotency — functional, not security)

#### Scenario: Re-rendering the same input yields identical output (AC-5-004) [CONFIRMED]
- **WHEN** `render(items, lookback_days=7)` is called twice with the same `items` list
- **THEN** both calls return strings that are exactly equal (idempotent rendering)

#### Scenario: Repos are ordered alphabetically regardless of input order (AC-5-005) [CONFIRMED]
- **WHEN** `items` contains repos `["zeta/b", "alpha/a"]` in that input order
- **THEN** the `## alpha/a` section appears before the `## zeta/b` section in the output

#### Scenario: Item-type groups appear in fixed Issues→Discussions→Releases order (AC-5-006) [CONFIRMED]
- **WHEN** a repo has items of types `release`, `issue`, and `discussion`
- **THEN** the output renders `### Issue mới` first, then `### Discussion`, then `### Release` for that repo

#### Scenario: Items within a group preserve input order (AC-5-007) [CONFIRMED]
- **WHEN** a repo's issues arrive in input order `[#123, #120]`
- **THEN** the rendered lines appear in that same order (`#123` before `#120`), not re-sorted

### Requirement: Empty input produces a meaningful "No new items" document
When `items` is an empty list, the renderer SHALL return a valid, short Markdown
document containing a top-level title and an explicit human-readable "No new items"
message. It SHALL NEVER return an empty string and SHALL NEVER produce ambiguous blank
output.

> ACs: AC-5-008 [CONFIRMED], AC-5-009 [CONFIRMED]
> Business rules: BR-5-005

#### Scenario: Empty list returns a non-empty "No new items" document (AC-5-008) [CONFIRMED]
- **WHEN** `render([], lookback_days=7)` is called
- **THEN** the return value is a non-empty `str` containing a title and a message indicating there are no new items (e.g. "No new items in the last 7 days"), and contains no `##` repo section

#### Scenario: Empty input never returns an empty or whitespace-only string (AC-5-009) [CONFIRMED]
- **WHEN** `render([], lookback_days=7)` is called
- **THEN** the result is not `""` and not whitespace-only (`result.strip()` is non-empty)

### Requirement: Only repos and groups that have items are rendered
The renderer SHALL emit a `## {repo}` section only for repos that have at least one
item, and a `### {Label} ({count})` group header only for item types that have at least
one item in that repo. It SHALL NEVER emit an empty repo section or an empty group.

> ACs: AC-5-010 [CONFIRMED], AC-5-011 [CONFIRMED]
> Business rules: BR-5-006

#### Scenario: A repo with no items produces no section (AC-5-010) [CONFIRMED]
- **WHEN** `items` contains entries only for `alpha/a` (none for `zeta/b`)
- **THEN** the output contains a `## alpha/a` section and NO `## zeta/b` section

#### Scenario: An item type with no items produces no group header (AC-5-011) [CONFIRMED]
- **WHEN** a repo has only `issue` items and no `discussion`/`release` items
- **THEN** the output for that repo contains a `### Issue mới (...)` header and NO `### Discussion` or `### Release` header

### Requirement: Per-item line format and section headers
Each item SHALL render as a single Markdown list line:
`- #{item_id} "{title}" — {summary} [link]({url})`. Each repo section header SHALL be
`## {repo} — {lookback_days} ngày qua`. Each group header SHALL be
`### {Label} ({count})` where `{count}` is the number of items in that group and
`{Label}` is `Issue mới` / `Discussion` / `Release` for issue / discussion / release.

> ACs: AC-5-012 [CONFIRMED], AC-5-013 [CONFIRMED], AC-5-014 [CONFIRMED]
> Business rules: BR-5-007, BR-5-008

#### Scenario: A normal item renders in the canonical line format (AC-5-012) [CONFIRMED]
- **WHEN** an issue has `item_id="123"`, `title="Fix bug"`, `summary="Handle null pointer."`, `url="https://gh/123"`
- **THEN** its line is exactly `- #123 "Fix bug" — Handle null pointer. [link](https://gh/123)`

#### Scenario: The repo header includes the lookback window (AC-5-013) [CONFIRMED]
- **WHEN** `render(items, lookback_days=7)` renders repo `alpha/a`
- **THEN** the section header is exactly `## alpha/a — 7 ngày qua`

#### Scenario: The group header shows the correct count (AC-5-014) [CONFIRMED]
- **WHEN** a repo has 3 issue items
- **THEN** its issue group header is exactly `### Issue mới (3)`

### Requirement: Defensive rendering of empty/dirty item fields
The renderer SHALL guard against empty-string `title`, `url`, and `summary`
(`RawItem.title`/`url` may be empty per the collector contract). When `title` is empty,
the line SHALL omit the quoted title (render `- #{item_id} — {summary} [link]({url})`).
When `url` is empty, the line SHALL omit the `[link](...)` suffix. When `summary` is
empty/whitespace-only, the line SHALL omit the `— {summary}` segment (no dangling
em-dash). The renderer SHALL NOT raise on any empty field.

> ACs: AC-5-015 [ASSUMED], AC-5-016 [ASSUMED], AC-5-017 [ASSUMED], AC-5-018 [CONFIRMED]
> Business rules: BR-5-009
> Risk: RF-2 (dirty-data resilience)

#### Scenario: Empty title omits the quoted title (AC-5-015) [ASSUMED]
- **WHEN** an item has empty `title`, `summary="A summary."`, `url="https://gh/1"`, `item_id="1"`
- **THEN** its line is `- #1 — A summary. [link](https://gh/1)` (no `""` quotes)

#### Scenario: Empty url omits the link suffix (AC-5-016) [ASSUMED]
- **WHEN** an item has empty `url`, `title="T"`, `summary="S."`, `item_id="1"`
- **THEN** its line is `- #1 "T" — S.` with no `[link]()` segment

#### Scenario: Empty summary omits the summary segment (AC-5-017) [ASSUMED]
- **WHEN** an item has empty/whitespace `summary`, `title="T"`, `url="https://gh/1"`, `item_id="1"`
- **THEN** its line is `- #1 "T" [link](https://gh/1)` with no dangling `—`

#### Scenario: No exception is raised on fully empty fields (AC-5-018) [CONFIRMED]
- **WHEN** an item has empty `title`, empty `body`, empty `url`, empty `summary`, `item_id="1"`
- **THEN** `render(...)` returns successfully and the item renders as at least `- #1` without raising

### Requirement: Unknown item types are bucketed, never dropped
The renderer SHALL render any item whose `item_type` is not one of
`issue`/`discussion`/`release` under a trailing `### Khác ({count})` ("Other") group
for its repo rather than dropping it silently. No input item SHALL ever be omitted from
the output (except via the documented empty-section rules, which only suppress *empty*
groups).

> ACs: AC-5-019 [ASSUMED], AC-5-020 [CONFIRMED]
> Business rules: BR-5-010

#### Scenario: An unknown item type is bucketed under "Khác" (AC-5-019) [ASSUMED]
- **WHEN** a repo has an item with `item_type="commit"` (unrecognized)
- **THEN** the output renders a `### Khác (1)` group containing that item's line, after the known-type groups

#### Scenario: Every input item appears exactly once in the output (AC-5-020) [CONFIRMED]
- **WHEN** `render(items, ...)` is called with N items across mixed repos and types
- **THEN** the output contains exactly N item lines (one per input item; none dropped, none duplicated)

