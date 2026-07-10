## Sketch — Gap Analysis

**No critical gaps found.** Sub-phase A verified against the live codebase; the change is confined to `pipeline.py` (filter) + `config.py`/`models.py` (config field). Key sketch findings that shape this design:

| Finding | Evidence | Design consequence |
|---------|----------|--------------------|
| `mark_seen(items)` is called **per-repo inside `_collect_all`**, at collect time | `src/osspulse/pipeline.py::_collect_all` | The seen-snapshot MUST be captured inside the same loop iteration, BEFORE that repo's `mark_seen` call |
| `is_seen` reads the **same `self._cached` dict** that `mark_seen` mutates in place | `src/osspulse/state/json_store.py:151-186` | A filter run *after* collection would observe every item as seen — this is exactly the R1 bug. Snapshot-before-write is structurally mandatory, not stylistic (BR-V2-001-001) |
| `StateError(Exception)` is **NOT** a subclass of `CollectorError` | `src/osspulse/state/errors.py` vs `src/osspulse/github/errors.py` | A `StateError` from `is_seen`/`load` propagates past `_collect_all`'s `except (InvalidRepoError, NetworkError, CollectorError)` untouched → AC-V2-001-009 satisfied with zero new handling |
| CLI already maps `StateError` **and** `ConfigError` → `Error: <msg>` exit 1 | `src/osspulse/cli.py:39-50` | AC-V2-001-009 and AC-V2-001-007 need no new CLI code |
| `[output]` section: fail-fast validation + `Config` field | `src/osspulse/config.py:109-130` | `[delta]` mirrors this 1:1; `_validate_lookback`'s `type(x) is not int` gives the bool-trap guard pattern verbatim (BR-V2-001-003) |

Minor (assumption, non-blocking): AC-V2-001-003 keeps the `StateStore` Protocol frozen — confirmed, `is_seen(repo, item_type, item_id) -> bool` already exists with the exact signature the filter needs.

## Context

V1 records every collected item as seen (`mark_seen`) but deliberately does **not** suppress already-seen items from the digest (original AC-7-011: two runs → byte-identical digest). V2 adds a cron scheduler, so re-running re-shows the same issues every time — violating the product principle "digest chỉ hiển thị cái mới so với lần trước". This change turns the already-recorded seen-state into a real **delta filter**.

Current pipeline (unchanged by this design except one insertion point):

```
run_pipeline → _collect_all (per-repo: fetch → mark_seen) → _summarize → render(once) → deliver(once)
```

Constraints:
- **Frozen contracts**: `StateStore` Protocol, `JsonFileStateStore.is_seen`/`mark_seen`, `RawItem`/`SummarizedItem`, collector, summarizer, renderer, delivery — none change (AC-V2-001-003, BR-V2-001-004).
- **Module boundary**: no stage module imports another; delta logic lives only in `pipeline.py` (AC-7-002, AC-V2-001-008/BR-V2-001-004).
- **No HTTP API, no DB**: internal stage contracts are typed dataclasses; V1 state is a JSON file. So this design has **no API Design content and no openapi.yaml** (see § API Design).

## Goals / Non-Goals

**Goals:**
- Suppress previously-seen items from the digest when `delta_enabled = true`, computed from a pre-`mark_seen` snapshot (AC-V2-001-001/004/005).
- Preserve the record-vs-render invariant: `mark_seen` still records ALL collected items regardless of `delta_enabled` (AC-V2-001-010, BR-V2-001-002).
- Config-gate via `[delta] enabled` (bool, default true), fail-fast validated (AC-V2-001-002/006/007, BR-V2-001-003).
- `delta_enabled = false` == byte-identical V1 behavior (AC-V2-001-006, EC-013).
- Empty-after-filter still delivers the "no new items" doc verbatim (AC-V2-001-008).

**Non-Goals:**
- Content-based delta / content hashing (BR-V2-001-004, EC-005) — identity-based only.
- Changing the `StateStore` Protocol or adding a `SeenStore` (AC-V2-001-003).
- Reordering the existing collect→mark_seen flow (would break AC-7-019 crash-safety).
- Per-repo / per-item-type delta toggles — one global switch.

## Architecture Overview

Delta is a **read-only partition** inserted into the existing per-repo collect loop. For each repo, immediately after `fetch_items` and **before** `mark_seen`, we compute which of the freshly-fetched items are new by reading `is_seen` against the not-yet-mutated state cache. `mark_seen(items)` then records the full fetched list unconditionally. The render-list accumulates only the `new` items when delta is on, or all items when delta is off.

```
for repo in watchlist:
    items = collector.fetch_items(repo, lookback_days)     # unchanged
    new, _seen = _partition_new(items, state)              # NEW: read-only, BEFORE mark_seen
    state.mark_seen(items)                                 # unchanged: records ALL (BR-V2-001-002)
    render_items.extend(new if config.delta_enabled else items)   # NEW: selection only
```

**Cross-spec dependencies (from `openspec list` + living specs):**
- `state-store-3` — `is_seen`/`mark_seen` frozen (INT-V2-001-001, INT-7-003). Reused as-is.
- `scheduler-cli-7` — this change MODIFIES its AC-7-011; AC-7-010/AC-7-019 preserved. `_collect_all` is the extension point.
- `digest-renderer-5` — `render([])` returns the no-new-items doc (AC-7-006), relied on by AC-V2-001-008. Unchanged.
- `delivery-6` — delivery never suppressed (AC-6-020). Unchanged.

**Layer placement:** `pipeline.py` (application orchestration) is the only layer touched for filter logic; `config.py`/`models.py` (config) gain the `[delta]` field. No domain, collector, or infra module changes.

## Decisions (ADRs)

### ADR-001 — Where the delta filter lives and how ordering is enforced

**Context:** R1 (HIGH) — if the seen-check runs after `mark_seen`, every item reads as seen and the digest is permanently empty. `is_seen` and `mark_seen` share the same `self._cached` dict (verified), so ordering is a correctness invariant, not a style choice (BR-V2-001-001/002).

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. `_partition_new(items, state)` helper called inline in `_collect_all`, before `mark_seen`** | Ordering enforced by call placement in one obvious spot; snapshot reads the same cache mark_seen will mutate → naturally "before"; no signature can be misused; smallest diff | Relies on the helper being called before `mark_seen` in the loop (mitigated: both are adjacent, 2 lines apart, guarded by AC-V2-001-010 count test) |
| **B. Capture a full seen-snapshot dict up front (all repos), pass to a post-collection filter** | Filter fully decoupled from collect loop | Requires materializing seen-state for all items before any collection; larger memory; duplicates state-store internals in pipeline; still must run before the loop's mark_seen → same ordering constraint, more moving parts |
| **C. Add `is_new`/snapshot method to StateStore Protocol** | Ordering encapsulated in the store | Violates AC-V2-001-003 (frozen Protocol) + BR-V2-001-004; expands adapter API; rejected at S1 (decisions.jsonl AC-V2-001-004) |

**Decision:** **Option A.** A module-private `_partition_new(items: list[RawItem], state: JsonFileStateStore) -> tuple[list[RawItem], list[RawItem]]` returning `(new, seen)`, called inline right after `fetch_items` and immediately before `state.mark_seen(items)`. It reads `state.is_seen(...)` only — no writes. The `mark_seen(items)` line is left exactly where V1 has it, so the collect→record ordering and crash-safety (AC-7-019) are unchanged. Selection of new-vs-all happens at `render_items.extend(...)`, keeping "which is recorded" (all) orthogonal to "which is rendered" (new).

**Consequences:** Minimal diff, ordering is locally obvious and pinned by the AC-V2-001-010 count-invariant test. `_partition_new` is pure/read-only, so it is trivially unit-testable in isolation. Does not decouple the filter into a separate pass (Option B) — accepted, because the per-repo loop is the only place items exist before `mark_seen`.

### ADR-002 — `[delta]` config parsing & validation

**Context:** `delta_enabled` is a bool from `[delta] enabled`, default true, fail-fast on non-bool (AC-V2-001-002/007, BR-V2-001-003). Bool-trap: `isinstance(True, int)` is `True`, so an `isinstance`-based check would let `1`/`0` through as bool.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. `_validate_delta(data)` helper + `type(v) is not bool` guard, mirroring `_validate_lookback`/`[output]`** | Consistent with existing config code; correct bool-trap handling; fail-fast at load (AC-V2-001-007) | One more small helper (negligible) |
| **B. Inline the check in `load_config` like `[output]`** | No new function | `[output]` is already inline and getting crowded; a named helper reads better and is unit-testable |
| **C. Coerce strings ("true"/"false") to bool** | Lenient | Violates BR-V2-001-003 fail-fast; hides typos; TOML already has a native bool type |

**Decision:** **Option A.** Add `_validate_delta(data: dict) -> bool` reading `data.get("delta", {})`, defaulting `enabled` to `True`, raising `ConfigError("delta.enabled must be a boolean")` when `type(value) is not bool` (with `# noqa: E721` like `_validate_lookback`). `Config` gains `delta_enabled: bool = True`. `load_config` calls it and passes `delta_enabled=` into the `Config(...)` return.

**Consequences:** Byte-for-byte consistent with the established config pattern; TOML `enabled = false` parses to a real bool, `enabled = "yes"`/`1` fails at load (AC-V2-001-007, EC-014). Default-true preserved when `[delta]` absent (AC-V2-001-002).

### ADR-003 — StateError handling (no new try/except)

**Context:** AC-V2-001-009 — a corrupt/unreadable state file must surface as `Error: <msg>` exit 1, and the filter must never be silently disabled. `is_seen` lazily calls `load()`, which raises `StateError`.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. Add nothing — let `StateError` propagate through `_collect_all` to the CLI** | `StateError` is not a `CollectorError`, so it already escapes the per-repo except; CLI already maps it to exit 1; zero new code; cannot accidentally swallow | Requires a test asserting no broad catch was added |
| **B. Wrap `_partition_new`/`is_seen` in try/except StateError and re-raise** | Explicit | Redundant (propagation already works); a mis-scoped except could swallow — the exact anti-pattern AC-009 forbids |

**Decision:** **Option A.** No new exception handling. Verified: `_collect_all`'s `except (InvalidRepoError, NetworkError, CollectorError)` does not match `StateError`, and `cli.py:39` already maps `StateError → Error: <msg> exit 1`. A regression test (AC-V2-001-009) asserts a `StateError` from the store propagates and the run exits 1.

**Consequences:** Satisfies AC-009 by *not* writing defensive code — the safest outcome. Developer gotcha (see Implementation Guide): do NOT add a `try/except` around `is_seen`/`_partition_new`.

### ADR-004 — Selection point: filter at accumulation vs at render

**Context:** Need to decide where `delta_enabled` gates the item set without touching `mark_seen`.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| **A. Select at `render_items.extend(new if delta else items)` inside the loop** | Recording (all) and rendering (new) are visibly separated at the point of divergence; no post-processing pass | Selection logic sits in the loop |
| **B. Always extend with `items`, then filter the accumulated list after the loop using a re-check** | Single selection site | Re-checking `is_seen` after `mark_seen` reads the mutated cache → the R1 bug; would need to carry the snapshot forward anyway |

**Decision:** **Option A.** Accumulate `new` (delta on) or `items` (delta off) at extend-time, using the `_partition_new` result already computed pre-`mark_seen`. Never re-query `is_seen` after `mark_seen`.

**Consequences:** The render-list is correct by construction; no second pass. Reinforces ADR-001's ordering guarantee.

## API Design

**N/A — OSS Pulse is a CLI tool with no HTTP API** (confirmed in project context: "No HTTP API — internal stage contracts are typed Python dataclasses"). This change adds no endpoints. Per the design rules, `openapi.yaml` is therefore **not produced** for this change (analogous to the Figma: N/A declaration). The only external-facing surface is the `[delta]` config key, specified below.

**Config surface (`config.toml`):**
```toml
[delta]
enabled = true   # bool, default true; false == V1 no-suppression
```

**Internal contract (unchanged, reused):** `JsonFileStateStore.is_seen(repo: str, item_type: str, item_id: str) -> bool` (INT-V2-001-001).

**New internal helper (module-private, not a public contract):**
`pipeline._partition_new(items: list[RawItem], state: JsonFileStateStore) -> tuple[list[RawItem], list[RawItem]]` → `(new, seen)`.

## DB Schema

**N/A — no database.** V1 state is a JSON file managed by `JsonFileStateStore`; its schema (`{"seen": {repo: {identity_key: first_seen_at}}}`) is **unchanged** by this design. Delta only *reads* it via `is_seen`. No migration.

## Error Mapping

| Condition | Exception | Origin | Surfaced as | AC |
|-----------|-----------|--------|-------------|-----|
| `[delta] enabled` non-boolean | `ConfigError` | `config._validate_delta` (load time) | `Error: delta.enabled must be a boolean` + exit 1 | AC-V2-001-007, EC-014 |
| Corrupt/unreadable state file | `StateError` | `JsonFileStateStore.load()` via `is_seen` | `Error: <msg>` + exit 1 (propagates, not swallowed) | AC-V2-001-009, EC-009 |
| Empty item_id | (none) | keyed safely as `"{item_type}:"` | no error; consistent across runs | EC-002 |
| Per-repo collector failure | `InvalidRepoError`/`NetworkError` | `_collect_all` | skip repo, continue (unchanged) | AC-7-004, EC-010 |

No new error class. `ConfigError` and `StateError` reuse existing CLI mappings (`cli.py:39-50`).

## Sequence Flows

**Flow 1 — delta enabled, mixed new + seen (AC-V2-001-004):**
```
run_pipeline(config)                      # config.delta_enabled = true
 └ _collect_all(config, collector, state)
     for repo:
       items = collector.fetch_items(repo, lookback_days)   # e.g. [#5(seen), #6(new)]
       new, seen = _partition_new(items, state)             # reads is_seen BEFORE mark_seen → new=[#6], seen=[#5]
       state.mark_seen(items)                                # records BOTH #5 and #6 (AC-V2-001-010)
       render_items.extend(new)                              # [#6]
 └ _summarize(config, render_items)        # only #6
 └ render(summarized, ...)                 # digest with #6
 └ deliver(digest)                          # exit 0
```

**Flow 2 — delta disabled (AC-V2-001-006, byte-identical V1):**
```
new, seen = _partition_new(items, state)   # computed but ignored
state.mark_seen(items)                      # records all (same as V1)
render_items.extend(items)                  # ALL items — no suppression
→ digest byte-identical to V1
```

**Flow 3 — empty-after-filter (AC-V2-001-005/008):**
```
every fetched item is seen → new = [] for every repo → render_items = []
render([]) → "No new items in the last N days" doc     # AC-7-006
deliver(doc)  → written/printed once, never skipped      # AC-V2-001-008, exit 0
```

**Flow 4 — corrupt state (AC-V2-001-009):**
```
_partition_new → state.is_seen(...) → load() raises StateError
 → NOT caught by _collect_all's CollectorError except
 → propagates to cli.run → Error: <msg>, exit 1
```

## Edge Cases

Covered by the 14 EC list in `proposal.md`; design-relevant ones:
- **EC-001** first run (empty state) → `_partition_new` returns all-new → all rendered.
- **EC-002** empty `item_id` → `is_seen` keys as `"{item_type}:"`, consistent → no crash.
- **EC-005** edited-but-same-id → still seen (identity-based, BR-V2-001-004) — **no content hash** (ADR-001/Non-Goals).
- **EC-008** seen-but-never-summarized → stays suppressed forever (accepted; "seen" tracks collection).
- **EC-010/011** repo skipped / rate-limit truncation → delta only sees successfully-collected items; `_partition_new` runs per successfully-fetched repo, orthogonal.
- **EC-013** `delta_enabled=false` → V1 byte-identical.

## Performance

- `_partition_new` adds one `is_seen` dict lookup per collected item — O(N) over items already held in memory, O(1) per lookup (`key in dict`). State is loaded once and cached (`self._cached`), so no extra I/O. Negligible vs the network/LLM cost that dominates a run.
- No new I/O, no new allocations beyond two lists partitioning an existing list.

## Security

No new attack surface (consistent with S1 STRIDE-skip). Delta only *reads* the existing local state file — no new network, no new secret, no new external input. No secrets touched by `_partition_new` or `_validate_delta`. STRIDE remains SKIPPED (feature touches none of auth/payment/PII/token/upload/admin; `stride_analysis=auto`).

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| R1 — seen-check after `mark_seen` → permanently empty digest | HIGH | ADR-001 inline `_partition_new` before `mark_seen`; AC-V2-001-010 count-invariant test; AC-V2-001-004 mixed test; developer gotcha documented |
| R2 — MODIFYING shipped AC-7-011 regresses V1 | MEDIUM | `delta_enabled=false` == V1 escape hatch (AC-V2-001-006); explicit byte-identical test (EC-013) |
| Bool-trap in config validation | LOW-MED | ADR-002 `type(x) is not bool` (not `isinstance`) mirroring `_validate_lookback` |
| StateError silently swallowed | MEDIUM | ADR-003 add NO try/except; test asserts propagation + exit 1 |
| Scope creep to content-based delta | LOW | BR-V2-001-004 + Non-Goals; ADR-001 rejects hashing |

## Implementation Guide

**Recommended order** (dependency-first: config → models → pipeline → tests):
1. `src/osspulse/models.py` — add `delta_enabled: bool = True` to `Config` (after `output_path`).
2. `src/osspulse/config.py` — add `_validate_delta(data)` (mirror `_validate_lookback` bool-trap), call it in `load_config`, pass `delta_enabled=` into the `Config(...)` return.
3. `src/osspulse/pipeline.py` — add `_partition_new(items, state)`; in `_collect_all`, insert the partition call between `fetch_items` and `mark_seen`; change `all_items.extend(...)` to select `new if config.delta_enabled else items`. Add `new`/`seen` counts to the run-summary log line (`collected=N seen=M new=N-M`).
4. Tests — `tests/test_config.py` ([delta] parse/default/invalid), `tests/test_pipeline.py` (first-run, mixed new+seen, empty-after-filter, delta-off byte-identical, mark_seen-count invariant, StateError propagation).

**Patterns to follow (with file paths):**
- Config validation + bool-trap: copy the shape of `config.py::_validate_lookback` (`type(value) is not int` + `# noqa: E721`) → use `type(value) is not bool`.
- Config field + `[section]` optional parse: copy the `[output]` block in `config.py:109-130`.
- Per-repo loop structure & logging: extend `pipeline.py::_collect_all` in place; keep the one-log-line-per-repo rule (AC-7-015) and never log raw exceptions.
- Test doubles: the collector/state are mocked per the project's "each external dep behind an interface, mocked in tests" rule — reuse existing `tests/test_pipeline.py` fakes.

**Gotchas:**
- ⚠️ **Order is load-bearing:** `_partition_new` MUST be called before `state.mark_seen(items)` in the loop. After `mark_seen`, `is_seen` reads the mutated cache and returns True for everything (R1). Do not move it.
- ⚠️ **Do NOT wrap `is_seen`/`_partition_new` in try/except** — `StateError` must propagate (ADR-003, AC-V2-001-009). A defensive catch would silently defeat delta.
- ⚠️ **`mark_seen(items)` records the full fetched list unconditionally** — never pass `new` to `mark_seen`. Recording is orthogonal to filtering (BR-V2-001-002, AC-V2-001-010).
- ⚠️ **No content hashing** — delta is identity-based (BR-V2-001-004); an edited issue stays suppressed by design (EC-005).
- ⚠️ **`delta_enabled=false` must be byte-identical to V1** — the only difference is the `extend` argument; do not add any other conditional behavior (AC-V2-001-006).
