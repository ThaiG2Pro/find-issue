---
description: Run the QA role directly (SDLC S5 Quality Assurance). Spawns the one-shot qa subagent with the active change's CPP baton to design scenarios from ACs, run tests + review + security + smoke, classify bugs with RCA, decide GO/NO-GO, and write qa-report.md. Usage: /qa <slug> · /qa (resume active change)
argument-hint: <slug> | (blank = active change)
---

# /qa — direct role invocation (S5)

You are the **main session**. This command spawns the **qa subagent** (one-shot) with the active
change's CPP baton, then relays its GO/NO-GO verdict + bug list. Direct entry to the role (D3): run
verification outside a full `/sdlc-full` drive, or re-run S5 after a fix. For the full gated pipeline
use `/sdlc-full`.

Request: **$ARGUMENTS**

> ### 🚫 INVARIANT — you (the main session) do not fix code; QA never writes product code
> You resolve the baton, spawn QA, and relay. The **qa subagent** may write tests
> (`test/**`, `tests/**`, `e2e/**`, `spec/**`, `__tests__/**`) + its report (`openspec/**`) but does
> **not** write/fix product code — bugs route back to `/developer` (S4-FIX). Enforced by the
> `agent_type`-keyed PreToolUse hooks.

## What this does

1. **Resolve the change** from `$ARGUMENTS` slug or the active `_state.json`. **Prerequisite:** S4
   built (`gates["S4"]="passed"`, dev-test-report.md present) — if not, warn and offer `/developer`.
2. **Spawn `qa` via the Task tool** (`subagent_type: qa`). Inject: change-name, `<CHANGE_DIR>`, work
   type, `_state.json.testcase_export` (xlsx|md → the test-case artifact is a gate prerequisite),
   and `_state.json.next_action.priority_reading` + `watch_items`. QA runs independently (does not
   trust the dev report): tests + code review + security audit + integration smoke; classifies bugs
   (R4) with RCA (R5); decides GO/NO-GO.
3. **Relay the return.** Present the GO/NO-GO, the bug list (severity + RCA), and the test-case
   artifact status. On NO-GO, route bugs to `/developer fix bug #N`.

## Not a gate

Runs ONE role; does **not** run `pipeline-guard.mjs` or advance `_state.json.gates`. The GO/NO-GO
gate (read qa-report.md + test-case artifact check + CPP contract validation) and approval are run by
`/sdlc-full … approve` / `/sdlc-fast … approve`. Say so when relaying. Disputes go through
`/sdlc-full dispute bug #N — <claim>`.

→ For state/baton mechanics, gate audit map + Kiro→Claude translations: **follow
`sdlc-orchestration-core`** (`.kiro/…` ⇒ `.claude/…`).
