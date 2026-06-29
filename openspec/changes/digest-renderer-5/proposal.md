# Proposal: Digest Renderer (S5) — ticket 5

## Why
The pipeline (Config → Collector → State Store → Summarizer → **Renderer** → Deliver)
needs a stage that turns the summarized items into a **single, readable Markdown
document** a user can consume in **< 2 minutes** (PROJECT_SPEC §4 experience
principle, §5 V1 "Xuất digest ra Markdown file (và/hoặc stdout)"). This change builds
the **S5 Digest Renderer**: it receives `list[SummarizedItem]` (the output of S4
`LiteLLMSummarizer.summarize_items()`), groups them per repo and per item type, and
returns a **deterministic Markdown string**.

The defining constraint is that the renderer is a **pure transform**:
`output = f(input)`. It performs **no I/O**, holds **no state**, and imports nothing
from `github/`, `state/`, `summarizer/`, or `cache/` (PROJECT_SPEC §6/§7 boundaries,
architecture.md "core depends on port interfaces only"). This keeps it trivially
idempotent (PROJECT_SPEC §7 "Idempotent: chạy lại không tạo digest trùng") and
testable without any mock — the cheapest, most reliable stage in the pipeline.

## What Changes
- **NEW** capability `digest-renderer`: a pure function/adapter
  `render(items: list[SummarizedItem], *, lookback_days: int) -> str` that produces a
  Markdown digest string. Exposed behind a **new `DigestRenderer` port** in
  `osspulse.ports` (role-named interface, consistent with `GitHubClient`/`LLMClient`/
  `StateStore`/`Delivery`), with a concrete adapter in `src/osspulse/render/`.
- **NEW** deterministic layout:
  - Repos sorted **alphabetically** (case-insensitive, stable) → each becomes a
    `## {org/repo} — {lookback_days} ngày qua` section.
  - Within a repo, items grouped by `item_type` in fixed order **Issues → Discussions
    → Releases**; each non-empty group gets a `### {Label} ({count})` header.
  - Within a group, items are rendered in **input order** (preserves the upstream
    newest-first ordering from the collector/summarizer).
  - Each line: `- #{item_id} "{title}" — {summary} [link]({url})`.
- **NEW** empty-input contract: an empty `list[SummarizedItem]` returns a valid, short
  Markdown document with a top title + an explicit **"No new items"** message — never
  an empty string, never an ambiguous blank file.
- **NEW** "only repos with items appear" rule: a repo with zero items is simply absent;
  the renderer NEVER emits an empty `##` repo section or an empty `###` group.
- Consumes the existing `SummarizedItem(raw: RawItem, summary: str)` domain model
  (models.py) — input only; the `Digest` model is **not** used or changed.

## Capabilities
- **New Capabilities**: `digest-renderer` →
  `openspec/changes/digest-renderer-5/specs/digest-renderer/spec.md`
- **Modified Capabilities**: none. `models.py` is unchanged (`Digest` left untouched —
  the renderer works directly with `list[SummarizedItem]`, NOT the `Digest` model).
  `ports.py` gains ONE new Protocol (`DigestRenderer`); existing Protocols are not
  touched. `github-collector`, `state-store`, `summarizer` capabilities are NOT
  touched — S5 receives `SummarizedItem` only through pipeline data.

## Impact
- **Code**: new `src/osspulse/render/` adapter (pure renderer). New `DigestRenderer`
  Protocol in `ports.py`. `models.py` unchanged; `config.py` unchanged (no output
  path here — file/stdout destination belongs to S6 Delivery).
- **Consumers**: S6 Delivery consumes the returned Markdown **string** and writes it to
  a file / stdout (V1). S7 CLI wires S4 output → S5 → S6.
- **External**: none. The renderer makes no network/filesystem/LLM calls. Tests need
  no mocks (pure function).
- **Security/Privacy**: no new data egress, no secrets, no auth, no file writes — the
  renderer only transforms in-memory data to a string. STRIDE threat model does NOT
  trigger for this change (see Early Risk Flags).
- **No** DB, no queue/broker, no HTTP API, no delivery logic, no discussions/releases
  content sources (those are V2; the layout reserves their section order at zero cost).

Figma: N/A (CLI tool, no UI).

## Assumptions

### [CONFIRMED]
- A-C1 [CONFIRMED]: Renderer input is `list[SummarizedItem]` only (mixed repos), the output of S4 `LiteLLMSummarizer.summarize_items()` — Source: cross-spec id 4 exports, project.md hard boundary, user clarification Q1=A.
- A-C2 [CONFIRMED]: Renderer is a **pure** transform — no I/O, no state, no file writes; file/stdout destination is S6's concern — Source: user clarification Q1=A, PROJECT_SPEC §7 idempotent, architecture.md.
- A-C3 [CONFIRMED]: Renderer signature is `render(items: list[SummarizedItem], *, lookback_days: int) -> str`; `lookback_days` is a plain int param (NOT a Config/state import) — Source: user clarification Q2=A.
- A-C4 [CONFIRMED]: Renderer MUST NOT import from `osspulse.github`, `osspulse.state`, `osspulse.summarizer`, or `osspulse.cache` — Source: architecture.md S2≠S4 boundary, summarizer AC-4-021 pattern, PROJECT_SPEC §6.
- A-C5 [CONFIRMED]: The `Digest` model in models.py is NOT used or modified — renderer works directly with `list[SummarizedItem]` — Source: user clarification Q1=A.
- A-C6 [CONFIRMED]: Empty input → return a Markdown doc containing a title + an explicit "No new items" message (never empty string, never ambiguous) — Source: user clarification Q2=A.
- A-C7 [CONFIRMED]: Only repos that have items get a `##` section; a repo/group with zero items is absent (no empty sections) — Source: user clarification Q2=A.
- A-C8 [CONFIRMED]: Output is deterministic — `output = f(input)`; repos sorted alphabetically (case-insensitive), item types in fixed Issues→Discussions→Releases order, items within a group in input order — Source: user clarification Q3=A.
- A-C9 [CONFIRMED]: Line format `- #{item_id} "{title}" — {summary} [link]({url})`; section header `## {repo} — {lookback_days} ngày qua`; group header `### {Label} ({count})` — Source: PROJECT_SPEC §4, user clarification Q3=A.
- A-C10 [CONFIRMED]: Renderer is exposed behind a new `DigestRenderer` port (role-named interface) with a concrete adapter, consistent with the project's ports/adapters pattern — Source: architecture.md ports & adapters, conventions.md interface naming, state watch-item.
- A-C11 [CONFIRMED]: V1 renders issues; the layout reserves Discussions/Releases section order for V2 but no V1 content source exists for them — Source: PROJECT_SPEC §5/§6 (S5 V1).
- A-C12 [CONFIRMED]: `RawItem.title`/`body`/`url` may be empty strings — the renderer must guard against this, never assume non-null — Source: cross-spec id 2 constraint.

### [ASSUMED]
- A-A1 [ASSUMED]: When `RawItem.title` is empty, the line renders `#{item_id}` with NO quoted title (i.e. `- #{item_id} — {summary} [link]({url})`) rather than rendering empty quotes `""` — design choice (avoids ambiguous empty quotes); PROJECT_SPEC silent on empty titles. **Confirm acceptable.**
- A-A2 [ASSUMED]: When `RawItem.url` is empty, the `[link]({url})` suffix is omitted entirely rather than rendering a broken `[link]()` — design choice (no dead links); PROJECT_SPEC silent.
- A-A3 [ASSUMED]: When `summary` is empty/whitespace-only, the line renders the title + link but omits the `— {summary}` segment (no dangling em-dash) — design choice; an empty summary shouldn't produce `"title" — . [link]`.
- A-A4 [ASSUMED]: Markdown-special characters in `title`/`summary` are rendered **as-is** in V1 (no defensive escaping). Output targets human reading; the digest is trusted local content. Defensive escaping is a noted future hardening, not a V1 requirement — design choice; PROJECT_SPEC §4 shows raw text. **Confirm: no escaping in V1.**
- A-A5 [ASSUMED]: The `#` item-id prefix is issue-style and correct for V1 (issues-only). For V2 discussions/releases the prefix may differ; that generalization is deferred to the V2 change — design choice; PROJECT_SPEC §4 shows `#12345` for issues.
- A-A6 [ASSUMED]: Group labels are `Issue mới` (Issues), `Discussion` (Discussions), `Release` (Releases), matching PROJECT_SPEC §4 wording — design choice from the spec's example. **Confirm labels.**
- A-A7 [ASSUMED]: An unknown/unexpected `item_type` (not issue/discussion/release) is rendered under a trailing `### Khác ({count})` ("Other") group rather than dropped silently — design choice (never lose an item); PROJECT_SPEC silent. **Confirm: bucket unknown types vs. drop.**

## Edge Cases
(Full enumerated list with expected behavior lives in
`specs/digest-renderer/spec.md` → "Edge Cases". Summary: ≥12 cases across input
boundary, state transition, data integrity, ordering/determinism, integration-contract,
and business-rule/readability categories — covering empty input, single empty repo,
empty title/body/url/summary, duplicate item ids, mixed repos out of order, mixed item
types, unknown item type, non-ASCII/markdown-special text, large input, and idempotent
double-render.)

## Early Risk Flags
**STRIDE threat model: NOT triggered for this change.** `.kiro/sdlc.config.json`
sets `security.stride_analysis: "auto"` — STRIDE runs only when a feature touches
auth / payment / PII / tokens / upload / admin. The Digest Renderer is a **pure
in-memory transform**: no authentication, no network egress, no secrets, no file/DB
writes, no user input parsing, no privilege boundary. There is no new attack surface.
The single residual risk is **functional, not security**: if the renderer is not
deterministic the digest could differ between identical runs (breaks the idempotency
principle) — this is mitigated by the explicit determinism ACs (sort + fixed group
order + input-order preservation), not by a security control.

## Non-Goals
- ❌ NOT writing the Markdown to a file or stdout, and NOT choosing the output path —
  that is S6 Delivery (the renderer returns a string only; user clarification Q1=A).
- ❌ NOT using or modifying the `Digest` model — the renderer works directly with
  `list[SummarizedItem]` (user clarification Q1=A).
- ❌ NOT performing any I/O, network, LLM, or state access — pure transform only.
- ❌ NOT importing from `osspulse.github` / `state` / `summarizer` / `cache`.
- ❌ NOT collecting or summarizing content — S5 consumes `SummarizedItem` from
  pipeline data only (hard architectural boundary).
- ❌ NOT rendering discussions/releases **content** in V1 (issues only); the layout
  reserves their section order for V2 at zero cost.
- ❌ NOT the meta-summary "tình hình repo tuần qua" — V3.
- ❌ NOT delta/"only-new-since-last-time" filtering — that is the State Store + V2
  delta concern; S5 renders exactly the items it is given.
- ❌ NOT a message queue/broker, DB server, or web framework (V1 over-engineering ban).
