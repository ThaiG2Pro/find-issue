---
description: Run the analyst role directly (SDLC S1 Requirements Intake + S2 Functional Spec). Spawns the one-shot analyst subagent with the active change's CPP baton to (re)produce the proposal + spec deltas, then relays its blocking questions/assumptions. Usage: /analyst <slug> [ticket <id>] · /analyst (resume active change) · /analyst redo S2
argument-hint: <slug> [ticket <id>] | (blank = active change) | redo S1|S2
---

# /analyst — direct role invocation (S1 / S2)

You are the **main session**. This command spawns the **analyst subagent** (one-shot) with the
active change's CPP baton, then relays its results to you. It is the direct entry to the role (D3):
use it to run requirements/spec work outside a full `/sdlc-full` drive, or to re-run S1/S2 on an
existing change. For the full gated pipeline use `/sdlc-full` instead.

Request: **$ARGUMENTS**

> ### 🚫 INVARIANT — you (the main session) do not write specs or code yourself
> You only resolve the baton, spawn the analyst, and relay its return. The **analyst subagent**
> writes `openspec/**` + `docs/knowledge/**`; no one writes code here. Enforced by the
> `agent_type`-keyed PreToolUse hooks (your calls carry no `agent_type` ⇒ orchestrator ⇒ read-only).

## What this does

1. **Resolve the change.** From `$ARGUMENTS` take the kebab-case slug + optional `ticket <id>`. If
   blank, load the active change from its `_state.json` (most-recent under `openspec/changes/`). If
   neither a slug nor an active change exists, this is a brand-new change — defer New Change Setup to
   the `sdlc-orchestration-core` skill (scaffold `<CHANGE_DIR>` + baton) **before** spawning.
2. **Spawn `analyst` via the Task tool** (`subagent_type: analyst`). Inject in the prompt: the
   change-name, `<CHANGE_DIR>` (`openspec/changes/<change>/`), the work type, and
   `_state.json.next_action.priority_reading` + `watch_items`. State the target phase (S1, S2, or
   both) — honor `redo S1|S2` from `$ARGUMENTS`.
3. **Relay the return.** The analyst cannot ask the user mid-run; it returns ≤5 blocking questions +
   risky `[ASSUMED]`s. **Present those to the user**, collect answers, and **re-spawn** the analyst
   with the answers in the prompt if anything material changed.

## Not a gate

This runs ONE role; it does **not** run `pipeline-guard.mjs`, the `spec-auditor` gate audit, or
advance `_state.json.gates`. To gate S2 and proceed to S3, the user runs `/sdlc-full … approve`
(which re-audits). Mention this when you relay the result so the user knows the SPEC LOCK gate is
still pending.

→ For New Change Setup, state/baton mechanics, and Kiro→Claude translations: **follow
`sdlc-orchestration-core`** (paths `.kiro/…` ⇒ `.claude/…`).
