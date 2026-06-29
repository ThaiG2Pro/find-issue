## Sketch — Gap Analysis

**No critical gaps found.** All 20 ACs (13 CONFIRMED + 7 ASSUMED-locked via Decision Lock), 10 BRs, 1 INT, and 15 edge cases map to concrete design elements below. The 7 `[ASSUMED]` items are locked V1 design decisions (each covered by an AC), not spec blockers.

Sketch (validated against `_handoff.md` §4 risky areas + cross-spec id 2/4):

- **Components**: 1 new port `DigestRenderer` (`ports.py`) + 1 new adapter package `src/osspulse/render/` (concrete renderer + composable line builder). No API endpoints (CLI tool), no DB tables, no migrations, no new dependency (stdlib only).
- **Flows**: (1) group→sort→render; (2) empty-input doc; (3) per-item line build with independent empty-field branches; (4) unknown-type bucketing.
- **Pattern reuse (search-first)**: mirrors the `summarizer/` adapter — concrete class implementing a structural `Protocol`, adapter-only logic, strict import-isolation (`AC-4-021` → `AC-5-003`), frozen models consumed read-only. Adopt, don't reinvent.

Non-code micro-decisions resolved by ADRs below (not gaps): function-vs-port relationship (ADR-002), grouping data structure for determinism (ADR-003), `Khác` ordering (ADR-004), no-openapi (ADR-005).

Cross-spec check: no conflict with collector/state/summarizer exports. `RawItem` empty-field constraint (cross-spec id 2) is absorbed into AC-5-015..018. No import of `osspulse.github`/`state`/`summarizer`/`cache` (cross-spec id 4 constraint → AC-5-003).

---

## Context

**Background.** OSS Pulse pipeline: Config → Collector → State Store → Summarizer → **Renderer (S5)** → Delivery → CLI. S4 (`LiteLLMSummarizer.summarize_items()`) exports `list[SummarizedItem]`. S5 turns that list into a single readable Markdown digest a user can consume in < 2 minutes (PROJECT_SPEC §4), and S6 writes the returned string to a file/stdout.

**Current state.** `src/osspulse/render/` exists with an empty `__init__.py`. `osspulse.models` defines frozen `SummarizedItem(raw: RawItem, summary: str)` and `RawItem(repo, item_type, item_id, title, body, url, created_at)`. `osspulse.ports` defines `GitHubClient`/`LLMClient`/`StateStore`/`SummaryCache`/`Delivery` Protocols. No renderer exists yet.

**Constraints (locked at S2):**
- Pure transform: `render(items, *, lookback_days) -> str` — no file/network/LLM/state I/O (AC-5-002, BR-5-001/002).
- No import of `osspulse.github`/`state`/`summarizer`/`cache` (AC-5-003, cross-spec id 4).
- `Digest` model untouched; `lookback_days` is a keyword-only `int` (the only window source), NOT a Config import (AC-5-003/005, A-C3/A-C5).
- Deterministic: `output = f(input)` — byte-for-byte identical (AC-5-004, BR-5-003/004).
- One new port only, single `render()` method — no I/O methods (that is S6).

**Stakeholders.** S4 (upstream producer), S6 Delivery + S7 CLI (downstream consumers of the returned string), S5 QA (must add a STATIC import-isolation test for AC-5-003).

## Goals / Non-Goals

**Goals:**
- A pure, deterministic `render(list[SummarizedItem], *, lookback_days: int) -> str` producing the Markdown digest (AC-5-001..014).
- Defensive line rendering that never raises on empty `title`/`url`/`summary` (AC-5-015..018).
- Unknown `item_type` bucketed under `### Khác`, never dropped; every input item appears exactly once (AC-5-019/020).
- Exposed behind a new `DigestRenderer` Protocol, consistent with the ports/adapters pattern (AC-5-010 port shape, INT-5-001).
- Trivially testable without mocks (pure function), idempotent (PROJECT_SPEC §7).

**Non-Goals:**
- ❌ Writing to file/stdout or choosing an output path (S6 Delivery).
- ❌ Using/modifying the `Digest` model.
- ❌ Any I/O, network, LLM, or state access; any import of upstream pipeline modules.
- ❌ Dedup / delta filtering (State Store's job — BR-5-010).
- ❌ Markdown escaping in V1 (A-A4 locked; field text rendered as-is).
- ❌ Rendering discussion/release *content* in V1 (layout reserves their order at zero cost).

## Architecture Overview

**Style:** ports/adapters (hexagonal-lite), consistent with `architecture.md` and the 3 prior changes. The renderer is a pure domain-adjacent transform with no infrastructure.

**Cross-spec dependencies (reuse, do not redesign):**
- `project-foundation`: `osspulse.models.SummarizedItem`/`RawItem` (frozen, read-only); `osspulse.ports` (add ONE Protocol).
- `github-collector-2`: `RawItem.title`/`url`/`body` may be empty strings — guard, never assume non-null (constraint absorbed into AC-5-015..018).
- `summarizer-llm-4`: import-isolation precedent (`AC-4-021`); adapter-only-helpers-off-Protocol pattern; produces the `list[SummarizedItem]` input via `summarize_items()`.

**New elements:**

| Element | Location | Role |
|---------|----------|------|
| `DigestRenderer(Protocol)` | `src/osspulse/ports.py` | Role-named port: `render(self, items: list[SummarizedItem], *, lookback_days: int) -> str` |
| `MarkdownDigestRenderer` | `src/osspulse/render/renderer.py` | Concrete adapter implementing the port (structurally) |
| `render(...)` module function | `src/osspulse/render/renderer.py` | Pure free function holding the logic; the class delegates to it |
| `_build_item_line(...)`, `_group_key`, label/order constants | `src/osspulse/render/renderer.py` | Module-private composable helpers |
| package exports | `src/osspulse/render/__init__.py` | `render`, `MarkdownDigestRenderer` |

**Layer rule honored:** adapter depends on core models + the port only; imports nothing from sibling adapters (`github`/`state`/`summarizer`/`cache`) and no I/O libs — stdlib only.

## Decisions (ADRs)

### ADR-001: Renderer is a pure free function behind a thin Protocol adapter (no `Digest` coupling)

**Context.** S5 must transform `list[SummarizedItem]` to a Markdown `str`. The port must be exposed consistently (A-C10) but the user explicitly rejected `Digest`-model coupling and I/O (Q1=A).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Pure free function `render()` + thin `MarkdownDigestRenderer` class delegating to it | Logic is mockless-testable as a plain function; class satisfies the port for DI/wiring; mirrors `summarize_items` adapter style | Two public names (function + class) for one behavior |
| B. Class-only adapter with logic in the method | Single public surface | Forces callers/tests to instantiate to test a pure transform; less idiomatic for a no-state function |
| C. Function only, no port/class | Simplest | Breaks the ports/adapters convention (A-C10, architecture.md "every dependency behind a port"); S6/S7 wiring loses the role-named seam |

**Decision.** **Option A.** A pure `render()` free function carries all logic; `MarkdownDigestRenderer.render(...)` delegates one line to it. This keeps the transform mockless-testable (QA tests the function directly) while preserving the role-named port for wiring (INT-5-001). Matches the summarizer precedent (logic in adapter, exposed via a structural Protocol). `Digest` is untouched.

**Consequences.** `render/__init__.py` exports both `render` and `MarkdownDigestRenderer`. The port stays a single `render()` method — no I/O methods (resists S6 drift). QA's static import test inspects `render/renderer.py`.

### ADR-002: `DigestRenderer` Protocol = single `render()` method, structural (no subclassing)

**Context.** Need a port consistent with `GitHubClient`/`LLMClient`/`Delivery` (A-C10, conventions.md "interfaces named by role, defined as Protocol").

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. `Protocol` with one method `render(...)`; adapter implements structurally | Matches all existing ports; no inheritance coupling; mockless | none material |
| B. ABC base class the adapter subclasses | Explicit | Diverges from existing `Protocol` ports; adds inheritance |
| C. Add `render` onto an existing port (e.g. `Delivery`) | Fewer types | Conflates S5 transform with S6 delivery; violates BR-5-002 + INT-5-001 ("one new port, no existing Protocol changed") |

**Decision.** **Option A.** Add `class DigestRenderer(Protocol): def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str: ...` to `ports.py`. `ports.py` must import `SummarizedItem` (currently imports `Digest, RawItem`) — add `SummarizedItem` to that import. No existing Protocol changed.

**Consequences.** `ports.py` gains one import + one Protocol. The `keyword-only` `*` marker is part of the contract (lookback_days cannot be passed positionally) — keeps the call site self-documenting and matches `summarize_items` keyword discipline.

### ADR-003: Deterministic grouping via ordered dict + stable case-insensitive sort

**Context.** Determinism is the core functional risk (RF-1). Python `dict` preserves insertion order, but grouping naively from input could leak input order into repo ordering; `set` iteration order is unstable. Must yield byte-for-byte identical output regardless of input order of repos (AC-5-004/005), with fixed group order (AC-5-006) and input order within a group (AC-5-007).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Group into `dict[repo] -> dict[item_type] -> list]` preserving append order; emit repos via `sorted(keys, key=str.lower)`; emit groups via a fixed ordered constant list; items in stored append order | Single pass to group, explicit sort only where required; no set/dict-order leakage; input order preserved within group | must remember to sort only repos, never items |
| B. Sort the whole item list by `(repo.lower(), type_rank, input_index)` then itertools.groupby | One sort | Requires carrying an explicit input index to keep within-group input order stable; groupby on unsorted-by-type needs pre-sort — easy to accidentally re-sort items |
| C. Collect repos/types into `set`s then sort | — | `set` ordering is a determinism trap (the exact RF-1 risk flagged); rejected outright |

**Decision.** **Option A.** Build `OrderedDict`-semantics via plain `dict` (Python 3.13 guarantees insertion order). Repo emission order = `sorted(grouped.keys(), key=str.lower)` (BR-5-003, stable, case-insensitive; two casings remain distinct repos — EC-010). Group emission order = a module constant `GROUP_ORDER = ["issue", "discussion", "release"]` then `"Khác"` (BR-5-004, AC-5-006). Items within a group are emitted in the order they were appended (= input order; AC-5-007). **No `set` anywhere.**

**Consequences.** Order-independence is testable by shuffling input (EC-007) → identical output. The "sort repos, never items" rule is a documented gotcha in the Implementation Guide. Counts (`### Label (N)`) come from `len(group_list)` reflecting literal input incl. duplicates (BR-5-010, EC-009).

### ADR-004: Unknown `item_type` → trailing `### Khác` group after the three known groups

**Context.** Items with `item_type ∉ {issue, discussion, release}` must never be dropped (AC-5-019/020, BR-5-010).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. One `Khác` bucket holding ALL unknown types, rendered last in each repo, items in input order | Simple, single trailing group; matches glossary "Khác bucket"; no item lost | mixes distinct unknown types under one label (acceptable for V1; A-A7) |
| B. One `### Khác` sub-group per distinct unknown type | Finer granularity | Needs deterministic ordering of unknown labels (more sort surface); over-engineered for V1 issues-only |
| C. Drop unknown types | — | Violates AC-5-020 (never drop); rejected |

**Decision.** **Option A.** All unknown types collapse into a single trailing `### Khác ({count})` group per repo, after issue→discussion→release, items in input order. Known group keys map to labels via `GROUP_LABELS`; anything else routes to the `Khác` bucket.

**Consequences.** EC-014 (all three known + one unknown) renders Issues→Discussions→Releases→Khác. A V2 change may split unknown types if needed; deferred.

### ADR-005: No `openapi.yaml` for this change (CLI-only, no inbound HTTP API)

**Context.** R5 mandates a separate `openapi.yaml` *if the change has an API*. This change exposes no HTTP API — the only contract is an internal Python function signature.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Omit `openapi.yaml`; document the Python contract in §API Design | Accurate; matches precedent (collector ADR-007, state ADR-004, summarizer) | deviates from R5's literal "separate file" |
| B. Author a stub `openapi.yaml` | Satisfies R5 literally | Fabricates an HTTP surface that does not exist; misleading |

**Decision.** **Option A** — a deliberate, ADR-justified deviation from R5/R9. **Rule cited:** R5 (`openapi.yaml` MUST be a separate file) and R9 (API path convention). **Reason:** OSS Pulse is a CLI tool with no HTTP API (conventions.md: "N/A — no HTTP API"; project.md "No HTTP API"). **Spec evidence:** proposal.md Impact "no HTTP API"; INT-5-001 defines the seam as a Python Protocol, not an endpoint. **Precedent:** github-collector-2 ADR-007, state-store-3 ADR-004 set this exact exception for CLI-only changes. The §API Design section documents the internal contract instead.

**Consequences.** Sub-phase C produces no `openapi.yaml`; the cross-artifact-audit endpoint check is N/A (0 endpoints in design = 0 paths). DESIGN REVIEW notes this deviation.

## API Design

**No HTTP API** (see ADR-005). The contract is the internal pipeline seam:

**Port** (`osspulse.ports`):
```python
class DigestRenderer(Protocol):
    def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str: ...
```

**Adapter + free function** (`osspulse.render`):
```python
def render(items: list[SummarizedItem], *, lookback_days: int) -> str: ...
class MarkdownDigestRenderer:  # implements DigestRenderer structurally
    def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str:
        return render(items, lookback_days=lookback_days)
```

**Output contract (Markdown shape):**
- Top title line: `# OSS Pulse Digest` (stable; present in both empty and non-empty docs).
- Empty input: title + blank line + `No new items in the last {lookback_days} days` (AC-5-008/009); no `##` section.
- Per repo (alphabetical, case-insensitive): `## {repo} — {lookback_days} ngày qua` (AC-5-013).
- Per non-empty group (fixed order): `### {Label} ({count})` where Label ∈ {`Issue mới`, `Discussion`, `Release`, `Khác`} (AC-5-014, BR-5-008).
- Per item: `- #{item_id} "{title}" — {summary} [link]({url})`, with empty-field degradation (AC-5-012, AC-5-015..017).

**Consumed by:** S6 Delivery (writes the returned string), S7 CLI (wires S4→S5→S6). **Reads from input only:** `raw.repo`, `raw.item_type`, `raw.item_id`, `raw.title`, `raw.url`, `summary` (INT-5-001).

## DB Schema

**N/A — no database.** The renderer holds no state and persists nothing (BR-5-001/002). V1 uses no DB (stack.md). No tables, no migrations.

## Error Mapping

The renderer **does not raise** on data conditions — defensive rendering is the contract (BR-5-009, AC-5-018). There is no error-to-exit-code mapping here (that belongs to S7 CLI).

| Condition | Behavior | AC / BR |
|-----------|----------|---------|
| Empty input list | Return non-empty "No new items" doc; result is never `""`/whitespace-only (`result.strip()` non-empty) | AC-5-008, AC-5-009, BR-5-005 |
| Empty `title` | Omit quoted-title segment; no raise | AC-5-015, BR-5-009 |
| Empty `url` | Omit `[link](...)` segment; no raise | AC-5-016, BR-5-009 |
| Empty/whitespace `summary` | Omit `— {summary}` segment; no dangling em-dash; no raise | AC-5-017, BR-5-009 |
| All fields empty except `item_id` | Render at least `- #{item_id}`; no raise | AC-5-018 |
| Unknown `item_type` | Route to `### Khác`; never drop; no raise | AC-5-019/020, BR-5-010 |
| Markdown-special / non-ASCII text | Render as-is (no escaping V1); no raise | A-A4, EC-005 |

The only programming-error surface (not a runtime data error) is a type contract violation by the caller (e.g. passing a non-`SummarizedItem`); that is out of scope — callers honor the typed signature.

## Sequence Flows

**Flow 1 — non-empty render (happy path):**
```
caller -> render(items, lookback_days=7)
  group: for item in items: grouped[repo][type_or_other].append(item)   # input order preserved
  emit "# OSS Pulse Digest"
  for repo in sorted(grouped, key=str.lower):                           # AC-5-005
    emit "## {repo} — 7 ngày qua"                                       # AC-5-013
    for gkey in GROUP_ORDER + ["__other__"]:                            # AC-5-006/ADR-004
      g = grouped[repo].get(gkey)
      if g:                                                             # AC-5-011 (skip empty)
        emit "### {LABEL[gkey]} ({len(g)})"                             # AC-5-014
        for it in g: emit _build_item_line(it)                          # AC-5-007/012
  return "\n".join(lines)                                               # deterministic
```

**Flow 2 — empty input:**
```
render([], lookback_days=7) -> "# OSS Pulse Digest\n\nNo new items in the last 7 days\n"  # AC-5-008/009
```

**Flow 3 — line builder (`_build_item_line`), composable branches:**
```
parts = [f"- #{item_id}"]
if title:   parts.append(f'"{title}"')          # AC-5-015 omit if empty
if summary.strip(): parts.append(f"— {summary}") # AC-5-017 omit if empty/whitespace
if url:     parts.append(f"[link]({url})")       # AC-5-016 omit if empty
return " ".join(parts)                            # never raises (AC-5-018)
```
(Exact joining/spacing finalized in build so AC-5-012 byte-matches `- #123 "Fix bug" — Handle null pointer. [link](https://gh/123)`.)

## Edge Cases

All 15 spec edge cases handled by the flows above:

| EC | Handling |
|----|----------|
| EC-001 empty list | Flow 2 — "No new items" doc |
| EC-002 all-empty fields | Flow 3 — `- #{item_id}` only, no raise (AC-5-018) |
| EC-003 empty title/url/summary | Flow 3 independent branches (AC-5-015/016/017) |
| EC-004 10k items | Single-pass group + join; no truncation; returns one string |
| EC-005 markdown/non-ASCII | Rendered as-is (A-A4) |
| EC-006 double render | Pure function → identical (AC-5-004) |
| EC-007 shuffled repos | `sorted(key=str.lower)` → identical (AC-5-005) |
| EC-008 within-group order | Append order preserved (AC-5-007) |
| EC-009 duplicate item_id | Both appended + rendered; count reflects both (BR-5-010) |
| EC-010 casing differs | Sorted by lowercased key; distinct repos stay distinct sections |
| EC-011 unknown type | `Khác` bucket (ADR-004) |
| EC-012 import inspection | No upstream imports (AC-5-003) — STATIC test flagged for QA |
| EC-013 lookback only window | `lookback_days` param flows to header; no Config/state read |
| EC-014 all types + unknown | Issues→Discussions→Releases→Khác (ADR-004) |
| EC-015 repo with zero items | Not in `grouped` → no `##` section (AC-5-010) |

## Performance

- Complexity: O(N) grouping + O(R log R) repo sort (R = distinct repos, R ≪ N). Single string build via list-join (avoids quadratic concatenation).
- EC-004 (10k items): trivially in-memory; no streaming needed in V1. Output is one string (no truncation — readability tuning is a separate future concern, not a render crash).
- No I/O, no network, no allocation hotspots beyond the line list. No caching needed (pure + cheap).

## Security

**STRIDE: NOT triggered** (confirmed at S2; `security.stride_analysis=auto`). Rationale: pure in-memory transform — no authentication, no network egress, no secrets, no file/DB writes, no privilege boundary, no untrusted-input parsing that crosses a trust boundary (input is already-collected pipeline data).

- **No new attack surface.** No data egress (unlike S4, which sends title+body to the LLM — N/A here).
- **No secrets.** The renderer never sees tokens/keys; nothing to log-leak.
- **Injection.** No SQL/shell/HTML sink. Markdown is rendered as-is for *local, trusted* human reading (A-A4); defensive Markdown escaping is noted as future hardening, not a V1 control — and is a *readability*, not security, concern for a single-operator local tool.
- The single residual risk is **functional (RF-1, determinism)**, mitigated by ADR-003 + the determinism ACs, not by a security control.

No Critical/High threats → no DESIGN-REVIEW security blocker.

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| RF-1: non-deterministic output (set/dict-order leakage, unstable sort) breaks idempotency | High (functional) | ADR-003: no `set`; `sorted(key=str.lower)`; fixed `GROUP_ORDER`; append-order within group. QA asserts byte-equality on double render (EC-006) + order-independence on shuffled input (EC-007). |
| RF-2: crash on empty/dirty fields | Medium | Flow 3 composable branches; AC-5-018 "never raises"; QA tests every empty-field permutation. |
| Import-isolation regression (someone imports upstream module later) | Medium | AC-5-003 STATIC import test (inspect `render/renderer.py` imports) — flagged for S5 QA. Mirrors summarizer AC-4-021. |
| Port drift toward I/O methods (S6 leakage) | Low | ADR-002: port frozen at single `render()`; documented gotcha. |
| Line-format byte-mismatch (spacing) on empty-field combos | Low | AC-5-012/015/016/017 exact-string scenarios pin the bytes; build verified against them. |

## Implementation Guide

**Recommended order** (foundational → domain → adapter → exports → tests):
1. `ports.py` — add `SummarizedItem` to the models import; add `DigestRenderer(Protocol)` with the single `render()` method (ADR-002).
2. `render/renderer.py` — constants `GROUP_ORDER`, `GROUP_LABELS` (incl. `Khác`); `_build_item_line()` (Flow 3); `render()` free function (Flows 1+2); `MarkdownDigestRenderer` class delegating to `render()` (ADR-001).
3. `render/__init__.py` — export `render`, `MarkdownDigestRenderer`.
4. Tests — unit tests per AC (happy, determinism, empty-field, Khác, empty-input) + the STATIC import-isolation test.

**Patterns to follow (with file paths):**
- Adapter/Protocol style → mirror `src/osspulse/summarizer/client.py` (`LiteLLMSummarizer` implements `LLMClient` structurally) and `src/osspulse/summarizer/__init__.py` (package exports).
- Frozen models, read-only → `src/osspulse/models.py` (`SummarizedItem`/`RawItem`).
- Port shape → `src/osspulse/ports.py` (role-named, single-purpose Protocols).
- Import-isolation precedent → summarizer `AC-4-021` and its module docstring note.

**Gotchas:**
- **Sort repos, NEVER items.** Items within a group keep input order (AC-5-007). Only repo keys are sorted, only by `str.lower` (BR-5-003).
- **No `set` anywhere** — it is the exact determinism trap (RF-1). Use the dict-of-dict grouping (ADR-003).
- **Keyword-only `lookback_days`** — keep the `*` in the signature; it is part of the contract (A-C3).
- **`render/__init__.py` is currently empty** — replace, don't append a second definition.
- **`ports.py` import line** currently is `from osspulse.models import Digest, RawItem` — add `SummarizedItem`; do NOT remove `Digest`/`RawItem` (used by other ports).
- **Empty-field spacing** — build `_build_item_line` by joining present segments with single spaces so AC-5-012/015/016/017 byte-match exactly; add a test per scenario.
- **`summary` check uses `.strip()`** for the omit branch (AC-5-017 "empty/whitespace"), but the rendered text is the original `summary` (no trimming of internal content beyond the segment-omit decision).
- **No Markdown escaping** (A-A4) — render `title`/`summary` verbatim.
