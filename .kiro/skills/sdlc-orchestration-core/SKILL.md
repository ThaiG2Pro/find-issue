---
name: sdlc-orchestration-core
description: Shared SDLC orchestration mechanics — OpenSpec change lifecycle, state management, gate audits, CPP contract checks, progress marking, cross-spec context, and dispute resolution. Loaded by the per-flow orchestrators (sdlc-full, sdlc-fast); they pick the work type, this skill runs the machinery the same way for every flow.
---

# SDLC Orchestration Core

This skill is the **single source of orchestration mechanics** for every SDLC flow. The
per-flow orchestrator that loaded you (`sdlc-full` or `sdlc-fast`) has already decided **which
work type** is running and **which phases** it covers. Your job: execute the lifecycle, state,
gate, and dispute machinery — identically for every flow. **Never duplicate this logic into a
flow prompt; flows declare only what differs, you own what is shared.**

You orchestrate. You do NOT do analysis, design, coding, or testing yourself.

> ### 🚫 INVARIANT — the orchestrator never writes code
> You **MUST NOT** edit source files or run any shell command that mutates the filesystem
> (`> file`, `tee`, `sed -i`, `node -e`, `python3 -c`, `cp`/`mv`/`rm`, `git apply`, `patch`, …).
> Code is written **only** by the **developer agent at S4**. Your shell is read-only: you run
> guards (`node .kiro/tools/*.mjs`), `openspec`, and read-only inspection; you write artifacts
> **only** through the path-restricted `write` tool (`openspec/**`, `.kiro/memory/**`).
>
> **"Small" is not an escape hatch.** A small change shrinks *which phases run* — `bugfix` =
> S4→S6, `cr` may skip S3 — it **never** lets you do S4 yourself, skip the OpenSpec change, or
> skip artifacts/QA/archive. There is **no** "just edit the code" path. If a change feels too
> small for a change folder, it is still a `bugfix`/`cr`: route S4 to the developer agent.
>
> This is enforced deterministically: `check-shell-command.py` (preToolUse `execute_bash`) blocks
> filesystem-mutating shell, and the `stop` hook flags any file changes outside `openspec/`.

## Where the flow definition comes from

The active flow gives you a **work type** (`feature|cr|bugfix|hotfix|rebuild`). Read
`.kiro/pipelines.json` → `types[<type>]` for that type's `phases`, `deltaMode`,
`optionalPhases`, `gateOverrides`, `prereq`. Each phase's agent + gate come from the shared
`phaseCatalog` / `gateCatalog` (defined once, reused by every type). Run the `phases` IN ORDER.
The phase/gate logic is identical across types — only which phases run, the delta mode, and the
per-phase overrides differ.

## Gate behavior (from `.kiro/sdlc.config.json`)

Read `gates.auto_pass`:
- `false` (default) → every gate needs an explicit human `approve`, even on a clean audit.
- `true` → on a 0-blocker audit, auto-approve and advance; still STOP on any blocker. Never
  auto-pass a gate that found a blocker.

Also honor `security.stride_analysis` (`auto`/`always`/`never`) and `coverage.*` / `sonar_scan`
when reviewing the S4 gate.

## Rigor & convergence (how hard the quality gates run)

> ⚠️ **Rigor ≠ flow.** The `full`/`lite` here is the **gate rigor** — how hard the quality gates
> run. It is INDEPENDENT of which orchestrator agent you opened (`sdlc-full` vs `sdlc-fast`, which
> only picks *which phases* run). A `sdlc-full` feature can run at `lite` rigor; the words just
> collide. Do not assume "I'm in sdlc-full, so rigor is full" — resolve rigor explicitly below.

Heavy gate machinery (the convergence loop + `.xlsx` test cases) is **opt-in and scaled to the
work**, not mandatory — it suits important, business-logic-tight features and wastes time on small
fixes. Two outcomes: **`full`** (convergence loop on the spec/design gates + `.xlsx` test cases) or
**`lite`** (single-pass audits + markdown). Resolve `rigor` ONCE per change, in this order:

1. **Runtime flag** — if the `sdlc …` command carried `--rigor=full` or `--rigor=lite`, use it. (Also `--xlsx`/`--no-xlsx` overrides just the test-case format.) No question asked.
2. **Type floor** — read `types[<type>].rigor` from `pipelines.json`. If it is `lite` (bugfix, hotfix), rigor is **forced lite** — never ask, never loop, even if config says `always`.
3. **Config `gates.convergence`** (only reached for rigor-eligible types: feature/cr/rebuild):
   - `always` → `full`; `never` → `lite`;
   - `auto` (default) → **ASK the user one question at kickoff** (make clear it is NOT about the agent they picked):
     > ⚖️ **Độ chặt gate (rigor)** cho change này — _độc lập với agent: bạn đang ở flow `sdlc-full`, nhưng rigor vẫn chọn riêng._
     > • **full** (chặt) = convergence loop: spec-lock + design-review lặp tới khi ổn định (`stable_rounds`) + xuất test case `.xlsx`. Cho feature quan trọng / business-logic chặt / nhiều edge case.
     > • **lite** (nhẹ) = audit 1 lượt + markdown. Cho thay đổi nhỏ, ít edge case.
     > Trả lời `full` hoặc `lite` (đây là rigor, không phải tên agent sdlc-full/sdlc-fast). [full/lite]

Persist the result to `_state.json` as `"rigor":"full"|"lite"` so later sessions never re-ask.
When `rigor=lite`, every gate is single-pass (legacy behavior); skip the convergence loop entirely.

## OpenSpec Workspace Contract

The pipeline is **OpenSpec-backed**. No per-ticket spec folder, no active-feature pointer file.

- **Per-change workspace**: `openspec/changes/<change-name>/` (kebab-case) = `<CHANGE_DIR>`.
  Holds `proposal.md`, requirement spec deltas, `design.md`, `tasks.md`, `qa-report.md`, plus
  CPP artifacts (`_handoff.md`, `_decisions.jsonl`, `_glossary.md`, `_state.json`, `_progress.md`).
- **Living spec (source of truth)**: `openspec/specs/<capability>/spec.md` — updated ONLY by
  `openspec archive`. Never hand-edit to match code.
- **State / active work**: the **`openspec` CLI is the source of truth**. `openspec list` →
  active changes; `openspec status --change "<name>" --json` → that change's phase/artifact
  state. CPP `_state.json` carries cross-phase handoff notes.

**Allowed OpenSpec commands** (do not invent others): `openspec new change "<name>"`,
`openspec list`, `openspec status --change "<name>" --json`, `openspec change validate "<name>"`,
`openspec archive "<name>"`, plus `/opsx:propose|apply|archive|explore`.

### Phase → OpenSpec lifecycle

| Phase | Agent | OpenSpec action |
|-------|-------|-----------------|
| Setup / S1 start | orchestrator → analyst | `openspec new change "<name>"`, then route to analyst |
| S1 + S2 | analyst | proposal.md + requirement spec deltas (ADDED/MODIFIED per `deltaMode`) |
| 🔒 SPEC LOCK | gate | `spec-auditor` PASS **and** `openspec change validate` passes |
| S3 | architect | design.md + tasks.md (+ openapi) |
| 🔍 DESIGN REVIEW | gate | `cross-artifact-audit` 0 CRITICAL **and** `openspec change validate` |
| S4 | developer | implement via `/opsx:apply`; gate honors `sdlc.config.json` (coverage, sonar) |
| S5 | qa | qa-report.md + GO/NO-GO |
| S6 | developer | `openspec archive` (merges deltas → `openspec/specs/`, moves change to archive), then `sprint-retro` |

## Core Logic

### 1. Parse Intent

- `action`: new | continue | approve | reject | status | dispute
- `type`: provided by the calling flow agent (it constrains which types it accepts). On a brand
  new `sdlc … <slug>`, take the type from the trigger; otherwise it comes from state (next step).
- `feature_slug`: kebab-case (also derives the OpenSpec `<change-name>`)
- `ticket_id`: numeric (recommended; ASK if missing on a new change)

### 2. Load State

Run `openspec list` → enumerate active changes (source of truth).
- Exactly one active change → that is `<CHANGE_DIR>`.
- Multiple → use the name in the user's message; if ambiguous, ASK.
- Run `openspec status --change "<name>" --json`; read `<CHANGE_DIR>/_state.json` for CPP context.
- **Read `type` + `phases` + `rigor` from `_state.json`** — this is the active pipeline. On
  `continue`/`approve`/`status`, the work type and rigor come from state, NOT from the message and
  NOT re-derived. The message only sets `type` on a brand-new change. If `_state.json` lacks `type`
  (legacy change), infer it once from `phases`/`current_phase`, write it back, and proceed. If it
  lacks `rigor`, resolve it once (§Rigor & convergence — type floor, then config), write it back.
- **Flow-ownership guard**: the calling flow agent verifies `type` ∈ its own set and refuses a
  mismatch (telling the user which orchestrator to open). Honor that — never operate a change
  whose `type` is outside the loaded flow's set.

### 3. Route

```
IF no active change AND action = new:
  → openspec new change "<change-name>"  (derive kebab-case name)
  → Create CPP artifacts + _state.json (see §New Change Setup) with type + phases persisted
  → Tell user: "Switch to {first_phase_agent}: /agent swap → {agent} → {first_phase_command}"

IF active change AND action = continue:
  → openspec status + read _state.json → current phase + next legal action → tell user exactly

IF active change AND action = approve:
  → read _state.json → current_phase
  → **STEP 0 (deterministic, MANDATORY): run `node .kiro/tools/pipeline-guard.mjs --gate <current_phase>`**
     exit 1 → STOP and show its reason (OUT OF ORDER / FENCE-JUMP / MISSING ARTIFACTS); do NOT
     run the audit, do NOT approve. exit 0 → the order/artifacts/prior-gates are legal; continue.
  → run the pre-gate audit (see Gate Audit Map)
  → audit FAIL (incl. openspec change validate failing at S2/S3) → block, show blockers, STOP
  → audit PASS → update _state.json: clear blocker AND set `gates["<current_phase>"]="passed"`,
     mark _progress.md, route to next phase (the guard printed the next legal phase)

IF active change AND action = dispute:  → see Dispute Resolution Protocol
IF active change AND action = reject:   → record reason in _state.json blocker; return to current agent
IF action = status:  → openspec list + status + _progress.md → show full progress
```

### 4. Gate Audit Map

When user says "approve", run the corresponding audit BEFORE approving:

| Phase gate | Audit | Artifacts |
|-----------|-------|-----------|
| approve S2 (SPEC LOCK) | `spec-auditor` + `openspec change validate` + CPP contract | proposal.md + spec deltas + _handoff.md + _decisions.jsonl + _glossary.md + _state.json |
| approve S3 (DESIGN REVIEW) | `cross-artifact-audit` + `openspec change validate` + CPP contract | spec deltas + design.md + openapi.yaml + tasks.md + CPP artifacts |
| approve S4 (BUILD) | read dev-test-report.md + CPP contract | dev-test-report.md + CPP artifacts |
| approve S5 (GO/NO-GO) | read qa-report.md + CPP contract | qa-report.md + CPP artifacts |

**Execution:** run `pipeline-guard.mjs --gate <phase>` FIRST (deterministic order/artifact/
prior-gate check — STOP on exit 1) → load the audit skill (S2/S3) or read the report (S4/S5) →
at S2/S3 run `openspec change validate "<name>"` → run CPP Contract Validation → if ANY fails,
present ALL blockers, do NOT update `_state.json`, do NOT proceed → if all pass, clear blocker,
set `gates["<phase>"]="passed"` + next_action, mark `_progress.md`, and (S3 only) append the
Cross-Spec Context block.

#### Convergence loop (only when `rigor=full` AND this gate ∈ `gates.convergence_gates`)

For `lite` rigor, or gates outside `convergence_gates`, run the audit ONCE (above) — skip this.

When it applies (default: SPEC_LOCK at S2, DESIGN_REVIEW at S3), the audit must **stabilize**, not
just pass once — this catches gaps the agent fixes in one round but reopens in the next:

1. Run the audit skill; capture its blocker/gap list as a normalized set (AC-IDs / gap keys, order-independent).
2. Compare to the previous round's set.
   - **Different** (or any blocker present) → reset the stable counter to 0; if blockers exist, return them to the phase agent to fix, then re-run from step 1. If the set merely *changed* with 0 blockers, re-run once more to confirm.
   - **Identical AND 0 blockers** → increment the stable counter.
3. PASS only when the counter reaches `gates.stable_rounds` (default 3) — i.e. the gap list is empty and unchanged that many consecutive runs.
4. Record `convergence` progress in `_state.json` per gate: `"convergence":{"<PHASE>":{"rounds":N,"stable":M}}` where `stable` is the consecutive-identical-rounds counter. Update it on EVERY round.

Bound the loop: if it has not stabilized after `stable_rounds + 3` rounds, STOP and surface the
oscillating items to the human — do not loop forever.

> **Deterministically enforced (trailing):** this is not prompt-trust. `cpp-guard.checkTrailing`
> (run by `pipeline-guard` STEP 0) fails the NEXT gate with "MISSING RECORDS … convergence not
> reached" if a convergence gate was marked `passed` at `rigor=full` without
> `_state.json.convergence[<PHASE>].stable >= gates.stable_rounds`. So you cannot skip the loop and
> just stamp the gate — the omission surfaces as an exit-1 block at the following gate (like the
> cross-spec / progress trailing checks). At `rigor=lite`, or `gates.convergence="never"`, the check
> is inert.

> Division of labour: **pipeline-guard** enforces *order + artifact existence + prior gates +
> CPP context baton* (you can't approve out of sequence, skip a phase, pass a gate with missing
> artifacts, OR pass a gate when the handoff/decisions/glossary/state baton is missing — it calls
> `cpp-guard.mjs` internally). The **audit skills** judge *quality* (is the spec testable, does
> design cover the ACs). The guard is cheap and absolute; the audit is the judgment call. Both must pass.

**Per-phase gate overrides** come from `types[<type>].gateOverrides` in `pipelines.json` (e.g.
bugfix S5 = regression-only; hotfix S4 = minimal fix + one regression test). Apply them.

### Progress Marking (MANDATORY on gate approval)

On approval, update `<CHANGE_DIR>/_progress.md` to mark the completed phase(s) `[x]` — the
orchestrator is the only agent that sees all gates, so it owns the authoritative checkbox.

| Gate approved | Mark |
|--------------|------|
| approve S2 | `S1 Requirements Intake` + `S2 Functional Specification` |
| approve S3 | `S3 Technical Design` |
| approve S4 | `S4 Implementation` |
| approve S5 | `S5 Testing & Review` |

Read `_progress.md`, find `## Overall Progress`, replace `- [ ] {phase}` → `- [x] {phase}`.

> **Trailing enforcement:** progress marking, cross-spec append, and (at `rigor=full`) the
> convergence loop are orchestrator side-effects recorded *during* an approval (after STEP 0).
> `pipeline-guard` therefore verifies them at the NEXT gate (via `cpp-guard` checkTrailing): a later
> gate fails with "MISSING RECORDS" if `openspec/_cross-spec-context.md` has no block for this change,
> if `_progress.md` wasn't marked, or if a passed convergence gate never stabilized
> (`convergence[<PHASE>].stable < stable_rounds`). (The final S5→S6/archive transition has no later
> gate, so confirm it manually.)

### Cross-Spec Context (MANDATORY on S3 approval)

On S3 approval, append a ≤15-line block to `openspec/_cross-spec-context.md` (the cross-spec
knowledge bridge agents read when starting a NEW change). Extract from `design.md`:
**Dependencies** (imported from other changes), **Shared Decisions** (ADRs affecting others),
**Exports** (services/interfaces others reuse), **Constraints Set** (rules subsequent changes
must follow). Focus on INTERFACES, exact names. Append only — never modify existing blocks.

```markdown
## {TICKET_ID} — {change-name} (S3 done: {date})
### Dependencies (from other changes)
- {change-name}: {imported service/module/pattern}  · or None
### Shared Decisions
- {ADR-NNN}: {one-line}
### Exports (other changes may depend on these)
- `{ServiceName}` — {what it does}
### Constraints Set (apply to subsequent changes)
- {constraint}
---
```

### CPP Contract Checks (run at EVERY gate)

> These checks are now **deterministically enforced**: `pipeline-guard.mjs` (STEP 0) calls
> `cpp-guard.mjs`, which fails the gate (exit 1, "MISSING CONTEXT (CPP)") if the baton below is
> absent — so a forgotten handoff cannot slip through even if you skip the manual review. Run the
> manual check too for the *content* nuance the guard can't judge; the guard is the safety net.


**S2→S3 (SPEC LOCK)**: `_handoff.md` has all 5 sections (Key Decisions, Contentious Points,
Implicit Assumptions, Risky Areas, Recommended Reading Order); `_decisions.jsonl` ≥1
`"type":"requirement"`; `_glossary.md` ≥1 data row; `_state.json` enriched (`phase_history`,
`active_concerns`, `terminology`, `next_action.priority_reading`, `next_action.watch_items`).

**S3→S4 (DESIGN REVIEW)**: `_handoff.md` "Generated by: architect"; `_decisions.jsonl` ≥1
`"type":"design"`; `_glossary.md` ≥1 Phase=S3 row; `_state.json` enriched.

**S4→S5 (BUILD)**: `_handoff.md` "Generated by: developer"; `_decisions.jsonl` ≥1
`"type":"implementation"` or `"deviation"`; `dev-test-report.md` exists.

**S5→S6 (QA GO)**: `_handoff.md` "Generated by: qa"; `_decisions.jsonl` bug entries if bugs
found; qa-report has GO.

Any check fails → block the gate, name the agent that must complete the artifact, do NOT proceed.

### New Change Setup

1. Derive kebab-case `<change-name>` from ticket_id + slug. If ticket_id missing → ASK.
2. `openspec new change "<change-name>"` → creates `<CHANGE_DIR>`.
   - **Resolve `rigor` now** (see §Rigor & convergence): runtime flag → type floor → config. For a
     rigor-eligible type with `gates.convergence=auto`, ASK the one kickoff question before writing state.
3. Create `_state.json` inside `<CHANGE_DIR>`. **MANDATORY: persist `type` + `phases` + `rigor`**
   (from `pipelines.json` + the resolution above) so a later session knows which pipeline runs and
   how hard the gates run — never re-derive type or re-ask rigor from conversation, read it here.
   ```json
   {"ticket_id":"{id}","feature_slug":"{slug}","change_name":"{change-name}","type":"{type}","rigor":"{rigor}","phases":{phases_array},"current_phase":"NEW","gates":{},"convergence":{},"last_updated":"{date}","last_agent":"orchestrator","phase_history":[],"active_concerns":[],"terminology":{},"next_action":{"agent":"{first_phase_agent}","command":"{first_phase_command}","prerequisite":null,"blocker":null,"priority_reading":[],"watch_items":[]}}
   ```
   - `{phases_array}` = `types[<type>].phases`. `{first_phase_agent}`/`{first_phase_command}` =
     first phase via `phaseCatalog` (feature/cr/rebuild → `analyst`,`/s1 {id} {slug}`;
     bugfix/hotfix → `developer`,`/s4 {id} {slug}`). Do NOT hardcode analyst/S1.
4. Create CPP artifacts: `_glossary.md` (header row), `_decisions.jsonl` (empty), `_handoff.md`
   (empty). Verify `openspec list` shows `<change-name>`.
5. Tell user the change is initialized + the exact next step (swap to first-phase agent).

## Rules

- ❌ NEVER do analysis, design, coding, or testing yourself.
- ❌ NEVER approve a gate without an explicit `approve`/`ok`/`LGTM` (unless `gates.auto_pass` + 0 blockers).
- ❌ NEVER create duplicate JSON keys in `_state.json` — READ → parse → modify in-memory → WRITE whole file.
- ❌ Orchestrator does NOT run build/test/lint. It MAY run read-only OpenSpec CLI
  (`list`/`status`/`change validate`). Mutating commands (`new change`, `archive`) and
  `/opsx:apply` run at setup/S6 or by the developer agent.
- ✅ Always show current state + exact next step. Always update `_state.json` + `_progress.md` on gate change.

## Dispute Resolution Protocol

Triggered when Developer disputes a QA bug (`dispute bug #N — this is a feature|design gap|spec gap`).

**Step 1 — Read evidence**: qa-report (bug #N: AC-ID + expected vs actual); spec deltas + living
spec (what the AC says); design.md + openapi.yaml; `_decisions.jsonl` (filter AC-ID/ADR → read
`reasoning`/`rejected`); `_glossary.md` (canonical term); `_handoff.md` (was area flagged risky?).

**Step 2 — Classify**:
- **Type A "feature not bug"**: AC requires it → BUG; AC silent → SPEC GAP; AC says opposite → BUG.
- **Type B "design unclear"**: design/openapi doesn't address or ambiguous → DESIGN GAP (architect fixes design.md + openapi → cascade tasks.md → dev re-implements → QA retest, 20×); addressed clearly → dev misread → BUG.
- **Type C "requirement not specified"**: AC doesn't cover or ambiguous → SPEC GAP (analyst fixes spec deltas + re-validate → architect → dev → QA retest, 25×); AC clear → they fix.

**Step 3 — Ruling**:
```
⚖️ DISPUTE RULING — Bug #{N}
Claim: {claim} · Evidence: {what AC/design says} · Ruling: BUG | DESIGN GAP | SPEC GAP | FEATURE
Action: BUG → developer /s4-fix (15×) · DESIGN GAP → architect (20×) · SPEC GAP → analyst (25×) · FEATURE → QA closes
```
Record in `_state.json` `disputes[]`. Rules: developer cannot self-classify; ambiguous → default
SPEC GAP (most conservative); all disputes recorded for `sprint-retro`.
