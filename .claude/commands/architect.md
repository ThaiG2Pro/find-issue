---
description: Run the architect role directly (SDLC S3 Technical Design). Spawns the one-shot architect subagent with the active change's CPP baton to (re)produce design.md + openapi.yaml + tasks.md, then relays its ADR option sets / blocking design choices. Usage: /architect <slug> · /architect (resume active change)
argument-hint: <slug> | (blank = active change) | redo S3
---

# /architect — direct role invocation (S3)

You are the **main session**. This command spawns the **architect subagent** (one-shot) with the
active change's CPP baton, then relays its results. Direct entry to the role (D3): run technical
design outside a full `/sdlc-full` drive, or re-run S3. For the full gated pipeline use `/sdlc-full`.

Request: **$ARGUMENTS**

> ### 🚫 INVARIANT — you (the main session) do not design or write code yourself
> You resolve the baton, spawn the architect, and relay. The **architect subagent** writes
> `openspec/**` + `docs/**` (design.md, openapi.yaml, tasks.md); no one writes code here. Enforced by
> the `agent_type`-keyed PreToolUse hooks (no `agent_type` ⇒ orchestrator ⇒ read-only).

## What this does

1. **Resolve the change** from `$ARGUMENTS` slug or the active `_state.json`. **Prerequisite:** the
   spec deltas must be locked (S2 passed) — if `_state.json.gates["S2"] != "passed"`, warn the user
   that design on un-locked specs is rework-prone and ask whether to proceed or run `/analyst` first.
2. **Spawn `architect` via the Task tool** (`subagent_type: architect`). Inject: change-name,
   `<CHANGE_DIR>`, work type, and `_state.json.next_action.priority_reading` + `watch_items`. For a
   `cr` whose `design_required=false`, note design may be skipped (the architect confirms via gap
   analysis).
3. **Relay the return.** The architect surfaces ADR option sets + `[UNCLEAR]` design choices it could
   not decide alone. **Present those to the user**, collect decisions, **re-spawn** if a choice
   changes the design.

## Not a gate

Runs ONE role; does **not** run `pipeline-guard.mjs`, the `cross-artifact-audit` (0 CRITICAL) gate
audit, or advance `_state.json.gates`. To gate S3 → S4 the user runs `/sdlc-full … approve`. Say so
when relaying — the DESIGN REVIEW gate is still pending.

→ For state/baton mechanics + Kiro→Claude translations: **follow `sdlc-orchestration-core`**
(`.kiro/…` ⇒ `.claude/…`).
