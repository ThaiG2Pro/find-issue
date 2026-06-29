# Digest Renderer Specification (delta — change digest-renderer-5)

## ADDED Requirements

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

## Edge Cases

### Input Boundary
- EC-001: `items == []` (empty list) → Expected: return a non-empty "No new items in the last {N} days" Markdown doc with a title, no `##` sections (AC-5-008/009).
- EC-002: single item with all-empty fields except `item_id` → Expected: renders `- #{item_id}` without raising (AC-5-018).
- EC-003: empty `title` → Expected: omit quoted title (AC-5-015). Empty `url` → omit link (AC-5-016). Empty `summary` → omit summary segment (AC-5-017).
- EC-004: very large input (e.g. 10k items across many repos) → Expected: renders without error; output is a single string (no truncation in V1 — readability tuning is a separate concern, not a render crash).
- EC-005: `title`/`summary` containing Markdown-special chars (`*`, `_`, `[`, backtick) or non-ASCII/emoji → Expected: rendered as-is (no escaping in V1, A-A4); no crash.

### State Transition / Determinism
- EC-006: render the same `items` twice → Expected: byte-for-byte identical output (AC-5-004, idempotent).
- EC-007: same items supplied in a different list order (repos shuffled) → Expected: identical output because repos are sorted alphabetically (AC-5-005).
- EC-008: within-group input order differs → Expected: output preserves the given input order within each group (AC-5-007) — determinism is per the *given* input order.

### Data Integrity
- EC-009: two items with the same `item_id` in the same repo+type (duplicate id) → Expected: both lines rendered (renderer does NOT dedupe — dedup is the State Store's job; renderer faithfully renders what it is given); count reflects both.
- EC-010: items for a repo whose `repo` string casing differs (`Alpha/A` vs `alpha/a`) → Expected: case-insensitive sort for ordering; the two distinct repo strings render as two distinct `##` sections (renderer does not normalize identity).
- EC-011: an `item_type` outside issue/discussion/release → Expected: bucketed under `### Khác` (AC-5-019); never dropped (AC-5-020).

### Integration Contract
- EC-012: importing the renderer module → Expected: no import of `osspulse.github`/`state`/`summarizer`/`cache` (AC-5-003) — enforced statically.
- EC-013: caller passes `lookback_days` as the only window source → Expected: header reflects it; renderer never reads Config/state for the window (AC-5-013, pure).

### Business Rule / Readability
- EC-014: a repo has items of all three known types + one unknown type → Expected: groups render in order Issues → Discussions → Releases → Khác, each with correct count.
- EC-015: a repo has zero items (no entries for it in `items`) → Expected: no `##` section emitted for it (AC-5-010).

## Early Risk Flags
- **STRIDE: NOT triggered.** Pure in-memory transform; no auth/PII/tokens/upload/admin/
  network/file surface. See proposal.md → "Early Risk Flags".
- **RF-1 (functional, not security): determinism / idempotency.** A non-deterministic
  renderer would break the project's idempotency principle (PROJECT_SPEC §7). Mitigated
  by the determinism Requirement (AC-5-004..007), NOT by a security control.
- **RF-2 (dirty-data resilience): empty/dirty fields.** `RawItem.title`/`url`/`body`
  may be empty (cross-spec id 2 constraint). Mitigated by the defensive-rendering
  Requirement (AC-5-015..018) — the renderer must never raise on dirty input.

## Business Rules

- **BR-5-001**: The renderer's only input is `list[SummarizedItem]` plus a keyword-only
  `lookback_days: int`. It SHALL NOT accept, read, or import any other source (Config,
  state, GitHub, LLM, cache).
- **BR-5-002**: The renderer SHALL return a `str`. It SHALL NOT write files, stdout, or
  any other output sink — destination selection is S6 Delivery's responsibility.
- **BR-5-003**: Repos SHALL be ordered alphabetically by `repo` using a
  case-insensitive, stable sort. Two `repo` strings that differ only by case are
  distinct repos (no identity normalization) but are ordered by their lowercased form.
- **BR-5-004**: Item-type groups within a repo SHALL appear in the fixed order
  `issue` → `discussion` → `release` → (any unknown type). Items within a group SHALL
  retain the order they appear in the input list.
- **BR-5-005**: An empty input list SHALL produce a non-empty Markdown document with a
  top-level title and a "No new items in the last {lookback_days} days" message, and no
  `##` repo section. The result SHALL NOT be empty or whitespace-only.
- **BR-5-006**: A `##` repo section SHALL be emitted only for repos with ≥1 item; a
  `### {Label} ({count})` group SHALL be emitted only for item types with ≥1 item in
  that repo. Empty sections/groups SHALL NOT appear.
- **BR-5-007**: The canonical item line SHALL be
  `- #{item_id} "{title}" — {summary} [link]({url})`. The repo header SHALL be
  `## {repo} — {lookback_days} ngày qua`. The group header SHALL be
  `### {Label} ({count})`.
- **BR-5-008**: Group labels SHALL be: `issue` → `Issue mới`, `discussion` →
  `Discussion`, `release` → `Release`, unknown → `Khác` (per PROJECT_SPEC §4; A-A6/A-A7
  locked).
- **BR-5-009**: Empty/whitespace fields degrade the line, never raise: empty `title` →
  omit the quoted title segment; empty `url` → omit the `[link](...)` segment; empty/
  whitespace `summary` → omit the `— {summary}` segment. `item_id` is always rendered.
  Field text is rendered **as-is** (no Markdown escaping in V1; A-A4 locked).
- **BR-5-010**: The renderer SHALL NOT deduplicate items — duplicate `item_id`s are
  both rendered (dedup is the State Store's responsibility). Every input item appears
  exactly once; counts reflect the literal input.

## Integration Points

- **INT-5-001**: The renderer consumes `osspulse.models.SummarizedItem`
  (`raw: RawItem`, `summary: str`) as produced by S4
  `LiteLLMSummarizer.summarize_items()` (cross-spec id 4). It reads `raw.repo`,
  `raw.item_type`, `raw.item_id`, `raw.title`, `raw.url`, and `summary` only. The
  returned Markdown `str` is consumed downstream by S6 Delivery. The new
  `osspulse.ports.DigestRenderer` Protocol is the integration seam (one new port; no
  existing Protocol changed).

## Decision Lock (S2 — [ASSUMED] items resolved as design decisions)

The following S1 `[ASSUMED]` items are **locked as design decisions** for V1 (no
stakeholder blocker; each is a low-risk, reversible formatting choice fully covered by
an AC). They remain `[ASSUMED]` tags on their ACs to signal "analyst design decision,
not stakeholder-confirmed", per R3.

- A-A1 → **LOCKED**: empty `title` omits the quoted-title segment (AC-5-015).
- A-A2 → **LOCKED**: empty `url` omits the `[link](...)` segment (AC-5-016).
- A-A3 → **LOCKED**: empty/whitespace `summary` omits the `— summary` segment (AC-5-017).
- A-A4 → **LOCKED**: no Markdown escaping in V1; field text rendered as-is (BR-5-009, EC-005).
- A-A5 → **LOCKED**: `#` item-id prefix is correct for V1 (issues-only); V2 generalization deferred.
- A-A6 → **LOCKED**: group labels `Issue mới` / `Discussion` / `Release` (BR-5-008).
- A-A7 → **LOCKED**: unknown `item_type` → `### Khác` bucket, never dropped (AC-5-019, BR-5-010).

## _Structured Extract

```yaml
change: digest-renderer-5
ticket_id: "5"
capability: digest-renderer
delta_mode: ADDED
phase: S2
rigor: full
figma: "N/A (CLI tool, no UI)"
stride: not_triggered  # pure in-memory transform; security.stride_analysis=auto, no sensitive surface

interface:
  port: "osspulse.ports.DigestRenderer (NEW)"
  signature: "render(items: list[SummarizedItem], *, lookback_days: int) -> str"
  adapter_location: "src/osspulse/render/"
  purity: "pure transform — no I/O, no state, no upstream imports"
  forbidden_imports: ["osspulse.github", "osspulse.state", "osspulse.summarizer", "osspulse.cache"]
  models_changed: false   # Digest model untouched; SummarizedItem consumed read-only
  ports_added: ["DigestRenderer"]
  ports_changed: []

counts:
  requirements: 8
  acceptance_criteria: 20
  business_rules: 10
  integration_points: 1
  edge_cases: 15
  ac_confirmed: 13
  ac_assumed: 7
  ac_missing: 0
  ac_unclear: 0

requirements:
  - id: R1
    title: "Render list[SummarizedItem] into a Markdown digest string"
    acs: [AC-5-001, AC-5-002, AC-5-003]
    brs: [BR-5-001, BR-5-002]
    int: [INT-5-001]
  - id: R2
    title: "Deterministic output — output is a pure function of input"
    acs: [AC-5-004, AC-5-005, AC-5-006, AC-5-007]
    brs: [BR-5-003, BR-5-004]
    risk: [RF-1]
  - id: R3
    title: "Empty input produces a meaningful 'No new items' document"
    acs: [AC-5-008, AC-5-009]
    brs: [BR-5-005]
  - id: R4
    title: "Only repos and groups that have items are rendered"
    acs: [AC-5-010, AC-5-011]
    brs: [BR-5-006]
  - id: R5
    title: "Per-item line format and section headers"
    acs: [AC-5-012, AC-5-013, AC-5-014]
    brs: [BR-5-007, BR-5-008]
  - id: R6
    title: "Defensive rendering of empty/dirty item fields"
    acs: [AC-5-015, AC-5-016, AC-5-017, AC-5-018]
    brs: [BR-5-009]
    risk: [RF-2]
  - id: R7
    title: "Unknown item types are bucketed, never dropped"
    acs: [AC-5-019, AC-5-020]
    brs: [BR-5-010]

acceptance_criteria:
  AC-5-001: CONFIRMED
  AC-5-002: CONFIRMED
  AC-5-003: CONFIRMED
  AC-5-004: CONFIRMED
  AC-5-005: CONFIRMED
  AC-5-006: CONFIRMED
  AC-5-007: CONFIRMED
  AC-5-008: CONFIRMED
  AC-5-009: CONFIRMED
  AC-5-010: CONFIRMED
  AC-5-011: CONFIRMED
  AC-5-012: CONFIRMED
  AC-5-013: CONFIRMED
  AC-5-014: CONFIRMED
  AC-5-015: ASSUMED
  AC-5-016: ASSUMED
  AC-5-017: ASSUMED
  AC-5-018: CONFIRMED
  AC-5-019: ASSUMED
  AC-5-020: CONFIRMED

happy_error_coverage:
  user_story: "As a user, I receive a readable Markdown digest of summarized items"
  happy_path: [AC-5-001, AC-5-004, AC-5-005, AC-5-006, AC-5-007, AC-5-012, AC-5-013, AC-5-014]
  error_or_edge_path: [AC-5-008, AC-5-009, AC-5-015, AC-5-016, AC-5-017, AC-5-018, AC-5-019]
  note: "8 happy + 7 error/edge ACs — exceeds R8 (≥3 happy + ≥3 error)"

depends_on:
  - "summarizer-llm-4: SummarizedItem + LiteLLMSummarizer.summarize_items()"
  - "github-collector-2: RawItem (title/url/body may be empty strings)"
  - "project-foundation: osspulse.models, osspulse.ports"

consumed_by:
  - "S6 Delivery: writes the returned Markdown string to file/stdout (V1)"
  - "S7 CLI: wires S4 -> S5 -> S6"

next_phase: S3
next_owner: architect
```

