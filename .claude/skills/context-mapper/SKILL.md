---
name: context-mapper
description: "Wire project context to each agent. Reads .kiro/context-map.json and (re)writes the resources[] of every .kiro/agents/*.json — skipping any file that doesn't exist, so references never break. Run after editing context-map.json, adding a context/ file, or adding a project doc folder."
disable-model-invocation: false
---

# context-mapper

Maps **project context → each agent** by regenerating the `resources` array of every
Kiro agent config from a single declarative source: `.kiro/context-map.json`.

This is the mechanism that lets each role (analyst / architect / developer / qa / sdlc)
consume a **different slice** of the project context, without hand-editing JSON.

## Model

```
.kiro/context-map.json   ← declares, per agent: skills[] + knowledgeBase[] (+ extraDocs[])
        │  node .kiro/tools/context-map.mjs
        ▼
.kiro/agents/*.json      ← resources[] regenerated (skills + knowledgeBase sources)
```

Any path that does not exist on disk is **skipped** (logged), so the kit never produces
a broken `skill://` or `file://` reference.

## When to run

- After editing `.kiro/context-map.json`
- After adding/removing a file under `.kiro/context/`
- After adding a project doc folder you want an agent to read (add it to
  `extraDocs.<agent>` in `context-map.json` first)
- After `init` (the installer runs it once automatically)

## How to run

```bash
node .kiro/tools/context-map.mjs            # operate on the current project
node .kiro/tools/context-map.mjs <dir>      # operate on another project dir
node .kiro/tools/context-map.mjs --map <path-to-context-map.json>
```

It prints, per agent, how many skills + knowledge-base sources were wired and how many
entries were skipped (missing). Re-running is safe and idempotent.

## context-map.json shape

```jsonc
{
  "always":   { "knowledgeBase": ["steering", "openspec", "sdlc.config.json", "context/project.md", "context/glossary.md"] },
  "agents": {
    "architect": {
      "skills": ["cross-artifact-audit", "api-design"],
      "knowledgeBase": ["ai", "context/stack.md", "context/architecture.md", "context/conventions.md"]
    }
    // ...one block per agent
  },
  "extraDocs": { "architect": ["docs/architecture"] }   // project-root-relative, optional
}
```

- `skills` entries resolve to `skill://.kiro/skills/<name>/SKILL.md`
- `knowledgeBase` entries are `.kiro/`-relative → `file://./.kiro/<entry>`
- `extraDocs` entries are project-root-relative → `file://./<entry>`

## Rules

- Edit `context-map.json`, never hand-edit `resources[]` in agent JSON (it gets overwritten).
- To stop an agent from reading a context file, remove it from that agent's lists here.
- Deleting a context file is safe — the mapper just stops emitting it on next run.
