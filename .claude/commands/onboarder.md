---
description: Run the onboarder role directly (one-time project context setup). Spawns the one-shot onboarder subagent to scan the repo, draft the .claude/context/ contract (6 files), mirror a digest into openspec/config.yaml, and run the completeness gate — then relays a Facts-to-commit table for your sign-off. Run this FIRST on a new project. Usage: /onboarder · /onboarder update
argument-hint: (blank = detect mode) | update
---

# /onboarder — direct role invocation (project context setup)

You are the **main session**. This command spawns the **onboarder subagent** (one-shot) to establish
the project context contract every SDLC role reads, then relays a sign-off table. Run this **first**
on a freshly-`init`'d project, or with `update` when context has drifted.

Request: **$ARGUMENTS**

> ### 🚫 INVARIANT — you (the main session) confirm facts; you do not silently commit them
> You spawn the onboarder and **own the sign-off**: the subagent never finalizes context on its own.
> It writes `.claude/context/**`, `context/**`, `openspec/config.yaml` (drafts), and returns a
> Facts-to-commit table + UNKNOWN list; **you get explicit user confirmation** before treating
> context as final. No code is written. Enforced by the `agent_type`-keyed PreToolUse hooks.

## What this does

1. **Spawn `onboarder` via the Task tool** (`subagent_type: onboarder`). Pass the mode hint from
   `$ARGUMENTS` (`update` ⇒ preserve human-written fields; blank ⇒ let it detect
   EXISTING/UPDATE/GREENFIELD). No CPP baton is needed — this runs before any change.
2. **Relay the return + own sign-off.** The onboarder returns: the **mode**, the **Detection Table**
   (or greenfield decisions), the **Facts-to-commit** table (`Field | Value | Source | Confidence`),
   every `UNKNOWN — needs owner input`, the `context-check.mjs` checklist, and the suggested
   doc→role routing. **Present these and ask the user to confirm** ("Confirm these facts (yes / edit
   <field> / no)"). For each UNKNOWN, get the owner's value, then re-spawn (or apply via a focused
   re-run) so the context-check gate passes clean.
3. **Next step after sign-off.** Tell the user: open `/sdlc-full <slug> ticket <id>`
   (feature/cr/rebuild) or `/sdlc-fast bugfix <slug>` for a localized fix.

## Notes

- The completeness gate is `node .claude/tools/context-check.mjs` (run by the subagent). It must
  exit 0 (no remaining `<!-- TODO`, no unsubstituted `{{TOKEN}}`, no shallow fields) before context
  is final — relay any ❌ items so the user can supply them.
- On Claude there is no per-agent JSON `resources[]` to wire — context is referenced statically by
  path and `@import`ed in `CLAUDE.md`. Doc→role routing is advisory (a table in the return).

→ For project-setup conventions: **follow the onboarder agent + `sdlc-orchestration-core`**
(`.kiro/…` ⇒ `.claude/…`).
