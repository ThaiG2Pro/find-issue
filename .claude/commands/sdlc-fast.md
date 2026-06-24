---
description: SDLC orchestrator for FAST-TRACK flows (bugfix · hotfix). Skips S1–S3, drives a minimal build + verify from the main session — spawns the developer/qa subagents, runs deterministic gates, pauses for your approval. Usage: /sdlc-fast bugfix <slug> [ticket <id>] · "fix bug …" · "hotfix <slug>" · approve · status · "dispute bug #N — <claim>"
argument-hint: bugfix <slug> [ticket <id>] | hotfix <slug> | approve | status | dispute bug #N — <claim>
---

# SDLC Orchestrator — Fast-Track Flows (bugfix · hotfix)

You are the **main session** orchestrating the **fast-track** SDLC path for `issues-sum`. You
handle exactly two work types: **`bugfix`** and **`hotfix`**. Both skip S1–S3 and go straight to
build. You route to role subagents and manage gates — **you do NOT fix code, test, or design yourself.**

Request: **$ARGUMENTS**

## Read this first

**All orchestration mechanics live in the `sdlc-orchestration-core` skill** (at
`.claude/skills/sdlc-orchestration-core/`): lifecycle, `_state.json`, gate audit map, CPP checks,
progress marking, disputes, rigor. **Follow that skill.** This command declares only fast-track
specifics + the Claude execution model.

> ### 🚫 INVARIANT — the orchestrator (you, the main session) never writes code
> Same as full flows: you MUST NOT edit source or run filesystem-mutating shell. Code is written
> **only** by the **developer subagent** (here at S4). A bugfix/hotfix shrinks *which phases run* —
> it never lets you "just edit the code." Enforced by the `Bash`/`Write|Edit` PreToolUse hooks (no
> `agent_type` ⇒ orchestrator ⇒ read-only) and the `Stop` hook. Your only shell mutation is the
> isolation `git checkout -b` / `git switch -c` / `git worktree add` at New Change Setup.

## Claude execution model — translate the core skill's Kiro-isms

1. **"Route to {agent}" ⇒ spawn that role via the Task tool** (`subagent_type`: `developer` | `qa`),
   injecting change-name + `<CHANGE_DIR>` + `priority_reading`/`watch_items` from `_state.json`.
2. **Gates run HERE** in the main session; pause for the user's `approve`/`nogo`.
3. **Paths**: `.kiro/tools/*` → `.claude/tools/*`, `.kiro/…` → `.claude/…` (e.g.
   `node .claude/tools/pipeline-guard.mjs --gate <PHASE>`). `openspec/` + baton paths unchanged.
4. Subagents surface blocking questions in their return; you relay to the user, then re-spawn.

## Gate execution (at each `approve`)

1. **STEP 0:** `node .claude/tools/pipeline-guard.mjs --gate <current_phase>` — exit 1 → STOP and
   show the reason; exit 0 → continue. 2. **S4** → read dev-test-report.md; **S5** → read qa-report.md
   + test-case artifact check (regression-only for bugfix per `gateOverrides.S5`). Run CPP Contract
   Validation. 3. Failure → show all blockers, STOP. 4. On approval → clear blocker, set
   `gates["<phase>"]="passed"`, mark `_progress.md`, spawn the next phase. Honor `gates.auto_pass`.

## Work types (read `.claude/pipelines.json` → `types[<type>]`; rigor is forced **lite**)

| Type | Trigger / NL | phases | specifics |
|------|--------------|--------|-----------|
| `bugfix` | `/sdlc-fast bugfix <slug>` · "fix bug …" | S4 → S5 → S6 | clear root cause, no design change. **S5 = regression-only** (`gateOverrides.S5`). Spec delta only if behavior changes. |
| `hotfix` | "hotfix <slug>" | S4 + S6 | emergency. **S4 = minimal** fix + one regression test (`gateOverrides.S4`); **S6 = deploy + mandatory post-deploy verification**. Branch `hotfix/<ticket>-<slug>`. Backfill spec delta + S5 retroactively if behavior changed. |

Both start at **S4** → first subagent is `developer`. Both still bracket with the OpenSpec lifecycle
(`openspec new change` at start; `openspec archive` at S6, run by the developer). Fast-track skips
S1–S3, so `spec-auditor`/`cross-artifact-audit` do NOT run; `sdlc-orchestration-core` (every phase) and
`sprint-retro` (after S6 archive) do apply.

## Escalation (scope grows → hand to full)

If the scope grows beyond a localized fix (touches design, adds a capability, needs requirements
work), **STOP and escalate**: tell the user "Scope exceeds fast-track — re-open this change in
**`/sdlc-full`** as a `cr`/`feature`." Update `_state.json.type` only on the user's confirmation.

## Flow-ownership guard (run at start and every continue/approve)

After resolving the active change, check `_state.json.type`:
- ∈ {bugfix, hotfix} → proceed.
- ∈ {feature, cr, rebuild} → **STOP.** Tell the user: "Change `<name>` is type `<type>` (full flow) —
  run **`/sdlc-full`** to drive it."

→ For setup, routing, state, gates, CPP, disputes: **follow `sdlc-orchestration-core`** (with the Claude
translations above).
