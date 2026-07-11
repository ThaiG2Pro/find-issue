# Proposal: V3-002 — GitHub Actions cron deployment (`v3-github-actions`)

> Type: **CR** · Rigor: **lite** · Scope: **tiny** · Ticket: **V3-002**

## Why

OSS Pulse today only runs when a human types `osspulse run` (locally or via OS cron on
their own machine — V2-002). PROJECT_SPEC §5 (V3) calls for a committed GitHub Actions
workflow so the digest is produced **"không cần mở laptop"** — the pipeline fires on a
schedule on GitHub's runners with zero local infrastructure. The blocker is that a CI
runner is **stateless**: the JSON state store (`.osspulse/state.json`) that makes the run
idempotent/delta-aware is thrown away when the runner is destroyed, so every scheduled run
would re-render everything. This CR ships the workflow **and** a state-persistence
mechanism (git-commit-back with `[skip ci]`).

## What Changes

- **NEW** committed `.github/workflows/osspulse.yml` — a scheduled GitHub Actions workflow:
  - `on.schedule.cron: "0 1 * * *"` (01:00 **UTC** = 08:00 **UTC+7**), plus `workflow_dispatch`
    for manual runs.
  - Installs osspulse from the checked-out repo and runs `osspulse run`.
  - After the run, **persists `.osspulse/state.json`** by committing it back to the repo with
    a `[skip ci]` message and pushing via the default `GITHUB_TOKEN`.
- **NEW** documented required GitHub repo Secrets (README + `.env.example` cross-reference):
  `LLM_API_KEY`, `DISCORD_WEBHOOK_URL`; `GITHUB_TOKEN` is auto-provided by Actions.
- A committed, secret-free CI config so the workflow has a `config.toml` to run against
  (both `.osspulse/` and `config.toml` are currently gitignored — see Risk R-1).
- **No changes to any file under `src/`** — this is pure infra/config. The existing
  `osspulse schedule --github-actions` generator (V2-002) is unchanged; this CR delivers a
  hardened, *committed, state-persisting* workflow that the generator's template does not
  produce (the template has no persistence step, no write permission, and installs a
  non-published `pip install osspulse`).

## Capabilities

- **New Capabilities**: `ci-automation` — the system's behavior of running itself on
  GitHub Actions and persisting state across stateless runs. (Distinct from `scheduler-cli`,
  which is the *CLI command that generates* schedule artifacts; this is the *committed
  deployment artifact* + its persistence contract.)
- **Modified Capabilities**: none. No existing requirement's behavior changes.

## Impact

- **Affected**: `.github/workflows/osspulse.yml` (new), README (docs), a committed CI config,
  `.gitignore` (may need a force-add for the state file, see R-1).
- **Runtime deps**: GitHub Actions default `GITHUB_TOKEN` + the repo Secrets store; the
  existing `osspulse run` CLI contract (exit 0 on success including the no-new-items case).
- **No src/ code, no new Python dependency, no test-suite change** (infra only; verified by
  QA via workflow-lint + a "no src/ diff" check).

## Non-Goals

- ❌ Redis / Upstash summary-cache on CI — that is a separate V4 item (the CR context calls it
  "#3"). This CR keeps the existing graceful no-cache degradation on the runner.
- ❌ Multi-repo build matrix / parallel per-repo jobs — a single job iterating the watchlist
  (the existing pipeline behavior) is the scope.
- ❌ Migrating state to Actions cache or remote object storage — git-commit-back is the chosen
  V3 mechanism; the other two options are noted (PROJECT_SPEC V3) but out of scope here.
- ❌ Any change to pipeline logic, summarizer, collector, or delivery code under `src/`.
- ❌ Notifying on CI failure (email/Slack of a red run) — nice-to-have, not this CR.

## Assumptions

- **[CONFIRMED]** Cron `0 1 * * *` (01:00 UTC) is the intended 08:00 UTC+7 slot; GitHub Actions
  evaluates `schedule.cron` in **UTC** (matches the analyst memory lesson from V2-002 — always
  spec the TZ). *Source: user scope item 1.*
- **[CONFIRMED]** State persistence uses **git commit `[skip ci]` + push via `GITHUB_TOKEN`**;
  the job declares `permissions: contents: write`. *Source: user scope item 1.*
- **[CONFIRMED]** `workflow_dispatch` manual trigger is in scope ("bonus if trivial" — it is a
  single line). *Source: user scope non-goals note.*
- **[ASSUMED]** Because both `.osspulse/` and `config.toml` are **gitignored**, the workflow
  force-adds the state file (`git add -f .osspulse/state.json`) and runs against a committed,
  secret-free CI config (`config.toml.example` copied to `config.toml` in the runner). This keeps
  local dev ignoring these paths while CI can still commit state. *Informed default; see R-1.*
- **[ASSUMED]** osspulse is **not published to PyPI**, so the workflow installs from the
  checked-out repo (`uv sync` / `pip install .`), not `pip install osspulse` as the V2-002
  generator template emits. *Source: repo has no published-package evidence; installs from source.*
- **[ASSUMED]** Only `.osspulse/state.json` is persisted (per exact scope). `etags.json` is **not**
  committed, so the ETag cache resets each CI run and the first fetch per endpoint is
  unconditional — correct, just slightly more rate-limit budget. Accepted for V3 (see E-7).
- **[ASSUMED]** A `concurrency` group serializes an overlapping manual + scheduled run so two
  runners never race the committed state file. *Informed default; the V2-002 fcntl lock does not
  span separate runners.*

## Edge Cases (scope=tiny → the categories that genuinely apply)

- **E-1 (state transition / data integrity)**: A run with **no new items** leaves `state.json`
  byte-identical → `git commit` would fail with "nothing to commit". The step MUST detect a clean
  tree and no-op with a **success** exit, never a failed job and never an empty commit.
- **E-2 (concurrency)**: A `workflow_dispatch` manual run fires while the scheduled run is still
  in flight → both push to the same branch and race `state.json`. Mitigated by a `concurrency`
  group (`cancel-in-progress: false` so the in-flight run finishes and persists).
- **E-3 (integration / infinite loop)**: The persistence push itself triggering another workflow
  run → mitigated by `[skip ci]` in the commit message AND the fact that pushes made with the
  default `GITHUB_TOKEN` do not re-trigger `on: push`/`on: schedule` workflows.
- **E-4 (permission)**: The default `GITHUB_TOKEN` lacks push rights → job must set
  `permissions: contents: write`; without it the push 403s and the job fails.
- **E-5 (data integrity / config)**: `config.toml` is gitignored so it is absent on the runner →
  `osspulse run` would fail `ConfigError`. Resolved by committing a secret-free CI config /
  copying `config.toml.example`.
- **E-6 (information disclosure)**: A secret (`LLM_API_KEY`, `DISCORD_WEBHOOK_URL`, token) ends up
  echoed in a log line or committed into the tree → forbidden; secrets only via `${{ secrets.* }}`
  env, never written to a committed file.
- **E-7 (rate limit / degradation)**: `etags.json` not persisted → each CI run re-fetches
  unconditionally on the first page per endpoint. Accepted (still within the 5000 req/hr token
  budget for a small watchlist); documented as a known limitation.
- **E-8 (integration)**: `osspulse run` exits non-zero (fatal `AuthError`/`ConfigError`) → the
  job fails BEFORE the persist step, so no partial/corrupt state is committed.

## Early Risk Flags (incl. STRIDE — feature touches secrets + repo write)

- **R-1 (Data integrity — the core trap)**: `.osspulse/` **and** `config.toml` are gitignored
  (`.gitignore` lines 12 & 14). The literal scope ("persist `.osspulse/state.json` via git
  commit") is impossible without a force-add and a committed CI config. This CR resolves it via
  `git add -f` + a committed secret-free config; architect must confirm this over the alternative
  (un-ignoring the paths, which would leak local dev state into commits).
- **R-2 (Information disclosure — STRIDE I)**: Committing files or logging near secrets risks
  leaking `LLM_API_KEY`/`DISCORD_WEBHOOK_URL`/token. Mitigation: secrets only as `${{ secrets.* }}`
  env; persist ONLY `.osspulse/state.json`; a "no secret substring committed" check.
- **R-3 (Elevation of privilege — STRIDE E)**: `permissions: contents: write` widens the default
  token scope. Mitigation: grant `contents: write` **only** (least privilege), no other scopes.
- **R-4 (Denial of service / loop — STRIDE D)**: A mis-configured persist step re-triggering the
  workflow could burn Actions minutes in a loop. Mitigation: `[skip ci]` + GITHUB_TOKEN-push
  non-triggering + `concurrency` group.
- **R-5 (Tampering — STRIDE T)**: The committed `state.json` is world-readable in a public repo,
  exposing which issue IDs have been seen. Low sensitivity (public repo issue numbers), accepted;
  noted so the operator using a private watchlist is aware.

Figma: N/A (CLI / CI infra — no UI).
