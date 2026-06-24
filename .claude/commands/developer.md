---
description: Run the developer role directly (SDLC S4 Build · S4-FIX · S6 Release). Spawns the one-shot developer subagent — the ONLY role that writes code — with the active change's CPP baton to implement per design/tasks, write AC-tagged tests, and produce dev-test-report.md. Usage: /developer <slug> · /developer (resume) · /developer fix bug #N · /developer release
argument-hint: <slug> | (blank = active change) | fix bug #N | release
---

# /developer — direct role invocation (S4 / S4-FIX / S6)

You are the **main session**. This command spawns the **developer subagent** (one-shot) with the
active change's CPP baton, then relays its results. Direct entry to the role (D3): run a build/fix/
release segment outside a full `/sdlc-full` drive. For the full gated pipeline use `/sdlc-full`.

Request: **$ARGUMENTS**

> ### 🚫 INVARIANT — only the spawned developer subagent writes code; you still cannot
> The **developer subagent** is the one role allowed to write `src/**`, `tests/**`, and config —
> precisely because its calls carry `agent_type: developer`. **You, the main session, remain
> read-only for code**: you resolve the baton, spawn the developer, and relay. Do NOT "just edit the
> file yourself" because this is the dev command — your calls carry no `agent_type` and the
> PreToolUse/`Stop` hooks will block/flag them. Code writes happen *inside the subagent*, never here.

## What this does

1. **Resolve the change + segment** from `$ARGUMENTS`: a slug, or `fix bug #N` (S4-FIX, reads the QA
   bug list), or `release` (S6), else the active `_state.json` (S4). **Prerequisite for S4:** design
   locked (`gates["S3"]="passed"`) — if not, warn and offer to run `/architect` first.
2. **Spawn `developer` via the Task tool** (`subagent_type: developer`). Inject: change-name,
   `<CHANGE_DIR>`, work type, the target segment (S4 / S4-FIX bug #N / S6), and
   `_state.json.next_action.priority_reading` + `watch_items`. The developer does ONE checkpoint
   segment per run (coverage ≥80%, test names carry AC-IDs, never mock the DB); on `release` it
   writes release.md and runs `openspec archive`.
3. **Relay the return.** The developer returns its dev-test-report (or release notes) + any blocking
   ambiguity it had to assume. Present blockers to the user; re-spawn the next segment as needed.

## Not a gate

Runs ONE role/segment; does **not** run `pipeline-guard.mjs` or advance `_state.json.gates`. The
BUILD gate (read dev-test-report.md, CPP contract validation) and approval are run by `/sdlc-full …
approve` / `/sdlc-fast … approve`. Say so when relaying.

→ For state/baton mechanics, checkpoint/segment rules + Kiro→Claude translations: **follow
`sdlc-orchestration-core`** (`.kiro/…` ⇒ `.claude/…`).
