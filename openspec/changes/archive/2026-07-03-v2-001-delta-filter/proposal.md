## Why

V1 records every collected issue as "seen" in the State Store but **deliberately does not
suppress** already-seen items from the digest (scheduler-cli AC-7-011: two runs produce a
byte-identical digest). For a tool the operator runs repeatedly (V2 adds cron), that means
re-reading the same issues every run — directly violating the product principle "digest chỉ
hiển thị cái mới so với lần trước" (PROJECT_SPEC §3 Nhóm C [P2], §5 V2 "Delta thật"). This
change turns the already-recorded seen-state into a real **delta filter**: a run shows only
issues that are new since the previous run.

This is the lowest-risk V2 slice: the infrastructure already exists
(`JsonFileStateStore.is_seen` / `mark_seen` shipped in state-store-3), so it touches no GitHub
API, no LLM, and no new external dependency — the change is confined to the pipeline
orchestrator plus one config field.

Figma: N/A (CLI tool, no UI)

## What Changes

- Add a config-driven **delta filter** to `run_pipeline`: after collecting a repo's items and
  BEFORE they are summarized/rendered, suppress items that were already seen on a **previous**
  run, so the digest shows only new issues.
- Delta is computed from a **pre-`mark_seen` snapshot**: an item counts as NEW iff
  `state.is_seen(...)` returns `false` at the instant *before* this run records it. `mark_seen`
  continues to record **all** collected items unchanged (idempotency history preserved).
- Add a `[delta]` config section with `enabled` (bool, default `true`), parsed and validated at
  config-load time (mirrors the delivery-6 `[output]` pattern). `Config` gains an
  `delta_enabled` field.
- **BREAKING (behavioral, spec-level)**: `scheduler-cli` **AC-7-011** is MODIFIED — with delta
  enabled, a second run over the same issues renders the "no new items" document instead of
  repeating them. `AC-7-010` (all collected items still `mark_seen`) is unchanged.
- When the filter suppresses everything, the pipeline delivers the S5 "No new items in the last
  N days" document verbatim (never suppresses delivery).

## Capabilities

### New Capabilities
- None. (Delta is orchestration logic in `pipeline.py`; it introduces no new pipeline stage and
  no new port.)

### Modified Capabilities
- **scheduler-cli** — the `run_pipeline` orchestration gains the delta filter step and its
  seen-suppression behavior. AC-7-011 changes from "does not filter seen items" to
  "suppresses previously-seen items when delta is enabled". This is the delta feature's home per
  the cross-spec constraint "filter logic lives in pipeline.py only".

> Config parsing for the new `[delta]` section is an implementation detail of `config.py`
> (S1 Config); it changes no existing config *requirement* behavior (existing keys keep their
> defaults), so it is captured in the scheduler-cli delta requirements rather than a separate
> config capability delta. The architect confirms this placement at S3.

## Impact

- **Code**: `src/osspulse/pipeline.py` (new filter step + wiring), `src/osspulse/config.py`
  (parse/validate `[delta]`), `src/osspulse/models.py` (`Config.delta_enabled` field).
- **Frozen contracts (unchanged)**: `StateStore` Protocol, `JsonFileStateStore.is_seen`/
  `mark_seen`, `RawItem`/`SummarizedItem`, the collector, summarizer, renderer, delivery — none
  change. Delta reuses `is_seen` as-is.
- **Tests**: `tests/test_pipeline.py` (delta on/off, first-run vs second-run, partial-new,
  empty-after-filter), `tests/test_config.py` (`[delta]` parsing + validation).
- **Docs**: README config schema gains the `[delta]` section + a note that re-runs suppress
  previously-seen items.

## Assumptions

- **A1 [ASSUMED]**: Delta filter lives entirely in `pipeline.py`; the `StateStore` Protocol and
  `JsonFileStateStore` public helpers stay unchanged. Source: cross-spec-context §3 constraint,
  state-store AC-3-018.
- **A2 [CONFIRMED]**: Delta is config-gated via a new `[delta]` section, `enabled` bool default
  `true` (user decision, clarification round). Rejected: always-on (too rigid), `--full` flag
  only (prefer declarative config consistent with `[output]`).
- **A3 [ASSUMED]**: When every collected item is already-seen, the pipeline passes an empty list
  to `render()`, which returns the "No new items in the last N days" doc, delivered verbatim —
  delivery is never suppressed. Source: AC-7-006, AC-6-020.
- **A4 [CONFIRMED]**: Membership is a **pre-`mark_seen` snapshot** — an item is NEW iff
  `is_seen()==false` before this run's `mark_seen`; `mark_seen` still records all items (user
  decision). Rejected: filter-before-mark_seen (breaks AC-7-019 ordering), `first_seen_at` vs
  `run_started_at` (second-resolution boundary + adapter API expansion).
- **A5 [ASSUMED]**: With `delta_enabled = false`, behavior is exactly V1 (no suppression;
  AC-7-011's original byte-identical guarantee holds). Source: opt-out semantics of option C.

## Edge Cases

### Input boundary
- **EC-001**: First-ever run (empty/missing state file) → nothing is "previously seen" → all
  collected items appear in the digest. Expected: identical to V1 first run.
- **EC-002**: Item with empty `item_id` (valid per collector contract) → `is_seen` keys it
  safely as `"issue:"`; delta must not crash and must treat it consistently across runs.

### State transition
- **EC-003**: Run 1 collects issue #5 (new → shown, marked seen). Run 2 with no new activity →
  #5 is now previously-seen → suppressed → "no new items" doc. Expected: MODIFIED AC-7-011.
- **EC-004**: Run 1 shows #5. Run 2 collects #5 (seen) + #6 (new) → only #6 shown. Expected:
  partial-new digest with just the new item.
- **EC-005**: An issue's `body` is edited between runs (same `item_id`). Delta keys on
  `repo+item_type+item_id` (NOT content) → the edited issue is STILL suppressed as seen.
  Expected: [ASSUMED] delta is identity-based, not content-based (content-hash re-summarization
  is a summarizer concern, out of scope here).

### Concurrency
- **EC-006**: Two `osspulse run` invocations overlap on the same state file. Out of scope —
  V1/V2 is single-operator, single-process (PROJECT_SPEC: no multi-tenant); documented as a
  non-goal, not defended against.

### Data integrity
- **EC-007**: State file recorded an item that GitHub no longer returns (issue deleted). Delta
  never re-surfaces it (nothing to filter); no error. Expected: benign, no crash.
- **EC-008**: Item marked seen in a previous run but its summarization failed that run (skipped
  from digest). On a later run it is already-seen → suppressed → it never appears in any digest.
  Expected: [ASSUMED] acceptable — "seen" tracks collection, not successful summarization
  (AC-7-019). Flagged as a known trade-off.

### Permission
- **EC-009**: State file unreadable/corrupt → `JsonFileStateStore.load()` raises `StateError`
  (AC-3-009). Delta must let it surface as `Error: <msg>` exit 1, never silently disable the
  filter. Expected: reuse existing StateError contract, no new handling.

### Integration failure
- **EC-010**: A repo is skipped by per-repo isolation (AC-7-004, e.g. 404). Its items are never
  collected, never marked seen, never filtered — delta only operates on successfully collected
  items. Expected: delta is per-item over collected items, orthogonal to repo isolation.
- **EC-011**: Rate limit terminates collection mid-watchlist (AC-7-017). Delta applies to the
  partial set collected so far; already-collected repos still filter correctly. Expected: no
  interaction bug.

### UI/UX (digest output)
- **EC-012**: All repos have only previously-seen items → each repo contributes zero items →
  empty combined list → single "No new items in the last N days" doc (no empty `## repo`
  sections, per renderer AC-5-010). Expected: one clean no-new-items doc.

### Business rule
- **EC-013**: `delta_enabled = false` → filter is bypassed entirely; digest shows all collected
  items exactly like V1 (original AC-7-011 byte-identical guarantee).
- **EC-014**: `[delta] enabled` set to a non-bool (e.g. `"yes"`, `1`) → `load_config` raises
  `ConfigError` at load time (fail fast), not at run time. Expected: mirrors `[output]`
  validation (AC-6-012).

## Early Risk Flags

- **R1 (correctness, HIGH)**: Ordering bug — if `is_seen` is checked AFTER `mark_seen`, every
  item looks seen and the digest is permanently empty. Mitigation: A4 snapshot-before-mark_seen
  is a normative AC with an explicit test (EC-001/EC-003).
- **R2 (regression, MEDIUM)**: MODIFYING AC-7-011 changes a shipped V1 guarantee. Mitigation:
  keep AC-7-010 intact, gate the new behavior behind `delta_enabled` (default true), and add an
  explicit `delta_enabled=false` == V1 test (EC-013).
- **R3 (silent scope drift, LOW)**: EC-005/EC-008 (edited-but-seen, seen-but-never-summarized)
  are deliberate identity-based trade-offs, not bugs — documented so QA doesn't file them.
- **Security**: no new attack surface. Delta reads the existing local state file only — no new
  network, no new secret, no new external input. STRIDE skipped (`stride_analysis=auto`, feature
  touches none of auth/payment/PII/token/upload/admin).

## Non-Goals

- ❌ Content-based delta (re-showing an issue because its body changed). Delta is identity-based
  (`repo+item_type+item_id`); content-hash lives in the summarizer cache, out of scope.
- ❌ Per-repo or per-item-type delta toggles. One global `[delta] enabled` switch only.
- ❌ A "what changed on an already-seen issue" diff (new comments, state change). V2-001 is
  new-vs-seen suppression only.
- ❌ Changing the State Store Protocol, adding a `SeenStore`, or moving to SQLite. Reuses
  `is_seen` as-is.
- ❌ Delta for Discussions/Releases — those sources don't exist yet (separate V2 changes).
- ❌ Concurrency/locking for overlapping runs (single-operator tool).
