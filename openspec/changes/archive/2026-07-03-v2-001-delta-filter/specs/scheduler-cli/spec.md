## ADDED Requirements

### Requirement: The run filters out previously-seen items when delta is enabled
The run SHALL suppress from the digest any collected item that was already recorded as seen on a
previous run, when `config.delta_enabled` is `true`. An item SHALL count as NEW if and only if
`state.is_seen(repo, item_type, item_id)` returns `false` at the instant BEFORE this run records
it via `mark_seen`. The run SHALL still call `mark_seen` on ALL collected items (new and
previously-seen alike) so `first_seen_at` history is preserved and idempotency is maintained; the
filter SHALL affect only WHICH items are summarized and rendered, never WHICH items are recorded.
This applies per collected item across the whole watchlist.

> ACs: AC-V2-001-001 [CONFIRMED], AC-V2-001-004 [CONFIRMED], AC-V2-001-005 [CONFIRMED], AC-V2-001-010 [CONFIRMED]
> Business rules: BR-V2-001-001, BR-V2-001-002
> Modifies: scheduler-cli AC-7-011 (see MODIFIED Requirements)

#### Scenario: First run shows all items (empty prior state) (AC-V2-001-001) [CONFIRMED]
- **WHEN** `osspulse run` executes with `delta_enabled = true` against an empty/missing state file and a repo returns 3 new issues
- **THEN** all 3 issues are rendered (nothing was previously seen) and all 3 are recorded via `mark_seen`

#### Scenario: Item is NEW iff not seen before this run's mark_seen (AC-V2-001-004) [CONFIRMED]
- **WHEN** a repo returns issue #6 (never seen) and issue #5 (recorded as seen on a prior run), with `delta_enabled = true`
- **THEN** only #6 is passed to the summarizer/renderer, while BOTH #5 and #6 are recorded via `mark_seen` (the seen-snapshot is taken before `mark_seen`, so #6 — first seen this run — still appears)

#### Scenario: Second run with no new activity suppresses everything (AC-V2-001-005) [CONFIRMED]
- **WHEN** a run collects the exact same issues a previous run already recorded as seen, with `delta_enabled = true`
- **THEN** the filtered list is empty, `render([])` returns the "no new items in the last N days" document, that document is delivered, and the command exits 0

#### Scenario: mark_seen is called for every collected item regardless of filtering or delta_enabled (AC-V2-001-010) [CONFIRMED]
- **WHEN** a run collects N items across the watchlist, of which M are already previously-seen (0 ≤ M ≤ N), for BOTH `delta_enabled = true` and `delta_enabled = false`
- **THEN** `mark_seen` is invoked exactly N times (once per collected item) in both configurations — the count of recorded items equals the count of collected items and is independent of `delta_enabled` and of how many items the filter suppresses; only the number of items passed to summarize/render differs (N when `false`, N−M when `true`). This is the direct guard against a filter-before-`mark_seen` reorder (R1): any ordering bug that skips recording a filtered item makes this count drop below N and fails the test.

### Requirement: Delta suppression is config-gated and defaults to enabled
The run SHALL read a `[delta]` config section whose `enabled` field (boolean, default `true`)
determines whether the delta filter is applied. `config.py` SHALL parse and validate the
`[delta]` section at load time and SHALL fail fast with a `ConfigError` on an invalid value
(non-boolean), never at run time. When the section is absent the run SHALL default to
`delta_enabled = true`. When `delta_enabled` is `false` the run SHALL behave exactly as V1 (no
suppression). The `Config` dataclass SHALL gain a `delta_enabled: bool` field.

> ACs: AC-V2-001-002 [CONFIRMED], AC-V2-001-006 [CONFIRMED], AC-V2-001-007 [CONFIRMED]
> Business rules: BR-V2-001-003
> Integration: INT-V2-001-001 (consumes state-store is_seen)

#### Scenario: delta defaults to enabled when the section is absent (AC-V2-001-002) [CONFIRMED]
- **WHEN** a config file has no `[delta]` section
- **THEN** `load_config` returns a `Config` with `delta_enabled = true`

#### Scenario: delta_enabled=false reproduces V1 behavior (AC-V2-001-006) [CONFIRMED]
- **WHEN** the config sets `[delta] enabled = false` and a run collects issues already recorded as seen
- **THEN** all collected items are rendered (no suppression) and the digest is byte-identical to a V1 run over the same items

#### Scenario: An invalid delta.enabled value fails config validation (AC-V2-001-007) [CONFIRMED]
- **WHEN** the config has `[delta]` with `enabled = "yes"` (or any non-boolean)
- **THEN** `load_config` raises `ConfigError` with a clear message before the pipeline runs

### Requirement: Delta operates only in the pipeline and reuses the frozen state helpers
The delta filter SHALL live entirely in `osspulse.pipeline` and SHALL reuse
`JsonFileStateStore.is_seen` unchanged. This change SHALL NOT alter the `StateStore` Protocol, add
methods to it, or change the signatures of `is_seen`/`mark_seen`. No pipeline stage module SHALL
import another stage module (the existing AC-7-002 boundary is preserved).

> ACs: AC-V2-001-003 [ASSUMED], AC-V2-001-008 [CONFIRMED], AC-V2-001-009 [CONFIRMED]
> Business rules: BR-V2-001-004
> Integration: INT-V2-001-001

#### Scenario: State Store Protocol and helpers are unchanged (AC-V2-001-003) [ASSUMED]
- **WHEN** the delta feature is added
- **THEN** `osspulse.ports.StateStore` still declares exactly `load() -> dict` and `save(state: dict) -> None`, and `is_seen`/`mark_seen` keep their existing signatures — the filter calls `is_seen` from `pipeline.py` only

#### Scenario: Empty-after-filter still delivers the no-new-items doc, never suppresses delivery (AC-V2-001-008) [CONFIRMED]
- **WHEN** every collected item is previously-seen and `delta_enabled = true`
- **THEN** delivery still runs exactly once (the "no new items" document is written to file / printed to stdout); the run never skips delivery and never produces an empty file

#### Scenario: A corrupt or unreadable state file surfaces as a run error, never silently disables the filter (AC-V2-001-009) [CONFIRMED]
- **WHEN** `delta_enabled = true` and the state file is corrupt or unreadable so `JsonFileStateStore.load()` raises `StateError` (AC-3-009)
- **THEN** the run surfaces the error as `Error: <message>` on stderr and exits 1; the run SHALL NOT swallow the error, SHALL NOT silently treat all items as new, and SHALL NOT proceed with the filter disabled

## MODIFIED Requirements

### Requirement: The run records collected items as seen for idempotency
The run SHALL record each collected item in the State Store via `mark_seen` so re-runs are
idempotent and the recorded state drives the V2 delta filter. State writes SHALL be atomic and
SHALL preserve a write-once `first_seen_at`. When `config.delta_enabled` is `true` (the V2
default), the run SHALL filter already-seen items out of the digest so a re-run over unchanged
activity renders the "no new items" document; when `delta_enabled` is `false` the run SHALL NOT
suppress seen items (preserving the original V1 behavior). Recording seen state SHALL remain
decoupled from summarization outcome.

> ACs: AC-7-010 [CONFIRMED], AC-7-011 [CONFIRMED], AC-7-019 [CONFIRMED]
> Business rules: BR-7-003, BR-7-011, BR-V2-001-001
> Integration: INT-7-003

#### Scenario: Collected items are marked seen (AC-7-010) [CONFIRMED]
- **WHEN** a run collects N items across the watchlist
- **THEN** each item is recorded via `mark_seen` and the state file is written atomically, and re-running preserves each item's original `first_seen_at`

#### Scenario: V2 delta suppresses previously-seen items on re-run (AC-7-011) [CONFIRMED]
- **WHEN** a run is executed twice with no new GitHub activity (the same issues are returned both times) and `delta_enabled = true`
- **THEN** the first run renders the items and records them seen, and the second run renders the "no new items in the last N days" document (previously-seen items are suppressed) — this replaces the V1 behavior where both runs rendered identical items

#### Scenario: Marking seen is decoupled from summarization outcome (AC-7-019) [CONFIRMED]
- **WHEN** an item is collected and marked seen but its summarization later fails and it is skipped
- **THEN** the item remains recorded as seen in the state file (collection, not summarization, is what "seen" records) and the run continues

## Business Rules

- **BR-V2-001-001**: An item counts as NEW for a run iff `state.is_seen(repo, item_type, item_id)` returns `false` at the instant BEFORE this run's `mark_seen` — i.e. delta membership is a pre-`mark_seen` snapshot. The seen-snapshot SHALL be captured before any of this run's items are recorded, so an item first-seen-this-run still appears in the digest. (A4, decisions.jsonl AC-V2-001-004.)
- **BR-V2-001-002**: The delta filter SHALL change only WHICH items are summarized/rendered, never WHICH items are recorded via `mark_seen`. `mark_seen` SHALL record every collected item (new and previously-seen alike) so `first_seen_at` history and idempotency are preserved regardless of `delta_enabled`. The recorded-item count SHALL equal the collected-item count in both `delta_enabled` states (verified by AC-V2-001-010). (Preserves AC-7-010, AC-7-019.)
- **BR-V2-001-003**: `[delta] enabled` SHALL be validated as a strict boolean at config-load time using a bool-trap-safe check (`type(value) is not bool`, mirroring `config.py::_validate_lookback`'s `type(value) is not int` guard); any non-boolean value (e.g. `"yes"`, `1`) SHALL raise `ConfigError` before the pipeline runs. Absent `[delta]` section SHALL default `delta_enabled = true`.
- **BR-V2-001-004**: Delta is identity-based — keyed on `repo + item_type + item_id`, never on item content. An item edited between runs but retaining the same identity SHALL stay suppressed as previously-seen (EC-005). The delta filter SHALL live entirely in `osspulse.pipeline`, reuse `JsonFileStateStore.is_seen` unchanged, and add no method to the `StateStore` Protocol (preserves AC-7-002 module-boundary and the frozen state-store contract).

## Integration Points

- **INT-V2-001-001**: Consumes `JsonFileStateStore.is_seen(repo, item_type, item_id) -> bool` (state-store-3), unchanged. Delta reuses this frozen helper from `pipeline.py`; a `StateError` raised by `load()` (AC-3-009) SHALL surface as a run error (AC-V2-001-009), never be swallowed.

## _Structured Extract

```yaml
ticket_id: V2-001
change_name: v2-001-delta-filter
capability: scheduler-cli
delta_mode: MIXED   # ADDED delta reqs + MODIFIED AC-7-011
requirements:
  added: 3
  modified: 1
acceptance_criteria:
  total: 10
  confirmed: 9
  assumed: 1
  missing: 0
  unclear: 0
  ids: [AC-V2-001-001, AC-V2-001-002, AC-V2-001-003, AC-V2-001-004, AC-V2-001-005, AC-V2-001-006, AC-V2-001-007, AC-V2-001-008, AC-V2-001-009, AC-V2-001-010]
  modified_living_acs: [AC-7-010, AC-7-011, AC-7-019]   # AC-7-011 behavior flipped; AC-7-010/019 preserved
coverage:
  happy_path: [AC-V2-001-001, AC-V2-001-002, AC-V2-001-004, AC-V2-001-005, AC-V2-001-006, AC-V2-001-008, AC-V2-001-010]
  error_path: [AC-V2-001-003, AC-V2-001-007, AC-V2-001-009]
business_rules:
  total: 4
  ids: [BR-V2-001-001, BR-V2-001-002, BR-V2-001-003, BR-V2-001-004]
integration_points:
  total: 1
  ids: [INT-V2-001-001]
decisions: [AC-V2-001-002, AC-V2-001-004, "MODIFIED:scheduler-cli AC-7-011"]
edge_cases: 14
risk_flags: [R1, R2, R3]
stride_gate: SKIPPED   # no new attack surface; stride_analysis=auto, no auth/payment/PII/token/upload/admin
figma: N/A
```
