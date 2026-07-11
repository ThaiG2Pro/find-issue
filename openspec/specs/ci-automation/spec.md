# ci-automation Specification

## Purpose
TBD - created by archiving change v3-github-actions. Update Purpose after archive.
## Requirements
### Requirement: A committed GitHub Actions workflow runs osspulse on a daily UTC schedule
The repository SHALL contain a committed workflow at `.github/workflows/osspulse.yml` that runs
`osspulse run` on a schedule so the digest is produced on GitHub's runners with no local machine.
The workflow SHALL trigger `on.schedule` with the cron expression `0 1 * * *` (01:00 UTC = 08:00
in UTC+7) and SHALL also expose a `workflow_dispatch` trigger for manual runs. The workflow SHALL
document that GitHub Actions evaluates `schedule.cron` in UTC. The workflow SHALL install osspulse
from the checked-out repository (not from a published package) and invoke `osspulse run` against a
committed configuration. This change SHALL NOT modify any file under `src/`.

> ACs: AC-V3-002-001 [CONFIRMED], AC-V3-002-002 [CONFIRMED], AC-V3-002-006 [ASSUMED], AC-V3-002-008 [CONFIRMED]
> Business rules: BR-V3-002-001, BR-V3-002-004
> Integration: INT-V3-002-001 (consumes the osspulse run CLI contract from scheduler-cli)

#### Scenario: Workflow is scheduled at 01:00 UTC with a manual trigger (AC-V3-002-001) [CONFIRMED]
- **WHEN** `.github/workflows/osspulse.yml` is parsed as YAML
- **THEN** it is a valid workflow whose `on.schedule` contains exactly the cron `0 1 * * *`, it also
  declares `on.workflow_dispatch`, and a comment records that Actions cron is evaluated in UTC
  (08:00 UTC+7)

#### Scenario: The job runs osspulse run from source against a committed config (AC-V3-002-002) [CONFIRMED]
- **WHEN** the workflow job executes on `ubuntu-latest`
- **THEN** it checks out the repo, installs osspulse from the checked-out source (e.g. `uv sync` /
  `pip install .`, never `pip install osspulse` from PyPI), and runs `osspulse run` against a
  committed `config.toml` present in the runner working directory

#### Scenario: No file under src/ is modified by this change (AC-V3-002-008) [CONFIRMED]
- **WHEN** the change's diff is inspected
- **THEN** no file under `src/` is added, modified, or removed — the change touches only
  `.github/workflows/`, a committed config, docs, and `.gitignore`

#### Scenario: A missing committed config would abort before persistence (AC-V3-002-006) [ASSUMED]
- **WHEN** `osspulse run` cannot find a valid `config.toml` on the runner (config absent or invalid)
- **THEN** the run exits non-zero with `Error: <message>` (the existing CLI ConfigError contract),
  the workflow job fails, and the state-persistence step does NOT run — so no partial or empty state
  is committed

### Requirement: The workflow persists run state across stateless runners via git commit
Because a GitHub Actions runner is ephemeral, the workflow SHALL persist `.osspulse/state.json` back
into the repository after each run so the next scheduled run is idempotent and delta-aware. The
persistence step SHALL commit ONLY `.osspulse/state.json` with a commit message containing `[skip ci]`
and SHALL push it using the Actions-provided `GITHUB_TOKEN`. Because the state path is gitignored, the
step SHALL force-add it (`git add -f .osspulse/state.json`). When the state file is unchanged after a
run (e.g. a no-new-items run), the step SHALL detect the clean tree and complete successfully WITHOUT
creating an empty commit and WITHOUT failing the job. The job SHALL declare `permissions: contents: write`
and SHALL NOT request any broader permission.

> ACs: AC-V3-002-003 [CONFIRMED], AC-V3-002-004 [CONFIRMED], AC-V3-002-005 [ASSUMED], AC-V3-002-007 [CONFIRMED]
> Business rules: BR-V3-002-002, BR-V3-002-003, BR-V3-002-005
> Integration: INT-V3-002-002 (consumes state-store .osspulse/state.json)

#### Scenario: State is committed back with [skip ci] after a run that produced changes (AC-V3-002-003) [CONFIRMED]
- **WHEN** a run changes `.osspulse/state.json` (new items recorded as seen)
- **THEN** the workflow force-adds `.osspulse/state.json`, commits it with a message containing
  `[skip ci]`, and pushes with `GITHUB_TOKEN`, so the next scheduled run starts from the recorded
  seen-state and suppresses those items

#### Scenario: An unchanged state file produces no empty commit and no job failure (AC-V3-002-004) [CONFIRMED]
- **WHEN** a run leaves `.osspulse/state.json` byte-identical (e.g. a no-new-items run)
- **THEN** the persistence step detects a clean working tree, creates NO commit, pushes nothing, and
  the job still exits successfully (the "nothing to commit" case is a success, never a red run)

#### Scenario: The job grants only contents:write and does not loop (AC-V3-002-005) [ASSUMED]
- **WHEN** the workflow's `permissions` block and commit behavior are inspected
- **THEN** the job declares `permissions: contents: write` (and no broader scope), and the state
  push does not re-trigger the workflow — both because the commit message carries `[skip ci]` and
  because a push made with the default `GITHUB_TOKEN` does not fire `on: schedule`/`on: push`

#### Scenario: Overlapping manual and scheduled runs are serialized (AC-V3-002-007) [CONFIRMED]
- **WHEN** a `workflow_dispatch` run is started while a scheduled run is still in flight
- **THEN** a `concurrency` group prevents the two runs from racing the committed `state.json`
  (`cancel-in-progress: false` so the in-flight run completes and persists its state)

### Requirement: Required secrets are documented and never inlined or committed
The deployment SHALL document the GitHub repository Secrets an operator must configure and SHALL
never inline or commit any secret value. The documentation SHALL state that `GITHUB_TOKEN` is
automatically provided by GitHub Actions, and that `LLM_API_KEY` and `DISCORD_WEBHOOK_URL` must be
added as repository Secrets. The workflow SHALL reference every secret exclusively via
`${{ secrets.* }}` env bindings, and the committed CI `config.toml` SHALL contain no secret value.

> ACs: AC-V3-002-009 [CONFIRMED], AC-V3-002-010 [CONFIRMED], AC-V3-002-011 [CONFIRMED]
> Business rules: BR-V3-002-003
> Integration: INT-V3-002-003 (consumes the secretless-artifact rule from scheduler-cli BR-V2-002-001)

#### Scenario: Required secrets are documented (AC-V3-002-009) [CONFIRMED]
- **WHEN** the README (or a referenced deployment doc) is read
- **THEN** it lists the required GitHub repo Secrets — `LLM_API_KEY` and `DISCORD_WEBHOOK_URL` — and
  states that `GITHUB_TOKEN` is provided automatically by Actions (the operator does not create it)

#### Scenario: Secrets are referenced, never inlined (AC-V3-002-010) [CONFIRMED]
- **WHEN** the committed workflow YAML is inspected
- **THEN** `LLM_API_KEY` and `DISCORD_WEBHOOK_URL` (and the token) are supplied only via
  `${{ secrets.* }}` env bindings, and no raw secret value appears anywhere in the YAML

#### Scenario: The committed CI config contains no secret (AC-V3-002-011) [CONFIRMED]
- **WHEN** the committed `config.toml` used by the CI run is inspected
- **THEN** it contains only non-secret configuration (watchlist, lookback, provider name, env var
  NAMES) and no secret value — secrets are resolved at run time from the Actions env

