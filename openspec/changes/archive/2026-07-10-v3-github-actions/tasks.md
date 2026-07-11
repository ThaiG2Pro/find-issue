# Tasks: V3-002 — `v3-github-actions`

> Scope: tiny · infra/config only · no `src/` changes.

- [x] 1. Add a committed, secret-free CI config for the runner to run against.
  File: `config.toml.example` (or a committed `config.toml` for CI)
  _Requirements: AC-V3-002-002, AC-V3-002-011_

- [x] 2. Un-ignore ONLY the CI state file path or document the `git add -f` approach so the
  workflow can commit `.osspulse/state.json` while local dev keeps ignoring `.osspulse/`.
  File: `.gitignore`
  _Requirements: AC-V3-002-003_

- [x] 3. Create the scheduled workflow: `on.schedule` cron `0 1 * * *` + `workflow_dispatch`,
  UTC comment, `concurrency` group, `permissions: contents: write`, checkout, install from
  source, run `osspulse run` with secrets bound via `${{ secrets.* }}` env.
  File: `.github/workflows/osspulse.yml`
  _Requirements: AC-V3-002-001, AC-V3-002-002, AC-V3-002-005, AC-V3-002-007, AC-V3-002-008, AC-V3-002-010_

- [x] 4. Add the state-persistence step: `git add -f .osspulse/state.json`, commit with
  `[skip ci]`, no-op cleanly when the tree is unchanged, push with `GITHUB_TOKEN`.
  File: `.github/workflows/osspulse.yml`
  _Requirements: AC-V3-002-003, AC-V3-002-004, AC-V3-002-006_

- [x] 5. Document required GitHub repo Secrets (`LLM_API_KEY`, `DISCORD_WEBHOOK_URL`;
  `GITHUB_TOKEN` auto-provided) and the "run without a laptop" deploy steps.
  File: `README.md`
  _Requirements: AC-V3-002-009_

- [x] 6. **CHECKPOINT (final)**: workflow lints as valid YAML/Actions schema; `git diff` shows
  zero `src/` changes; no secret substring appears in any committed file; ACs V3-002-001..011
  verified.
  _Requirements: AC-V3-002-001, AC-V3-002-002, AC-V3-002-003, AC-V3-002-004, AC-V3-002-005, AC-V3-002-006, AC-V3-002-007, AC-V3-002-008, AC-V3-002-009, AC-V3-002-010, AC-V3-002-011_
