## Sketch — Gap Analysis

**No critical gaps found.** All 11 ACs (AC-V3-002-001..011) are CONFIRMED/ASSUMED with a
resolved decision in `_decisions.jsonl`; the analyst's R-1 gitignore trap already has an agreed
resolution (force-add + committed secret-free CI config). This is a pure infra change — a single
committed workflow file plus a committed CI config and README docs. **No `src/` changes**
(AC-V3-002-008). No API surface → **no `openapi.yaml`** (deliberate; this is a CLI/CI change).

Sketch (single artifact + supporting files):
- `.github/workflows/osspulse.yml` — the scheduled workflow (all runtime ACs).
- `config.toml` committed to repo root (secret-free) — so `osspulse run` has config on CI (AC-002/011).
- `.gitignore` — unchanged; state file reached via `git add -f` (AC-003, R-1 resolution).
- `README.md` — required-secrets doc (AC-009).

## Context

`osspulse run` is stateless-hostile on a CI runner: the runner is ephemeral, and the JSON state
store (`.osspulse/state.json`) that gives the pipeline idempotency/delta-awareness is destroyed
when the runner is torn down. Both `.osspulse/` and `config.toml` are **gitignored**
(`.gitignore` lines 12 & 14), so the literal ask "persist state.json via git commit" is impossible
without a force-add and a committed CI config. The existing V2-002 generator
(`src/osspulse/schedule/workflow.py`) is NOT reused as-is: its template installs `pip install
osspulse` (not on PyPI), has no write permission, and has no persistence step — this CR must
differ on all three. This CR hand-authors a hardened, committed, state-persisting workflow.

## Goals / Non-Goals

**Goals:**
- A committed daily workflow (cron `0 1 * * *` UTC = 08:00 UTC+7) + `workflow_dispatch`.
- Install osspulse from checked-out source; run `osspulse run` against a committed secret-free config.
- Persist ONLY `.osspulse/state.json` via `git add -f` + commit `[skip ci]` + push `GITHUB_TOKEN`,
  no-op cleanly on an unchanged tree, least-privilege `contents: write`, no workflow loop.

**Non-Goals:** _(unchanged — per proposal §Non-Goals)_ Redis/Actions-cache/remote-storage for
state, per-repo matrix, CI-failure notification, any `src/` logic change.

## Decisions

### ADR-001 — State persistence = git commit-back with a clean-tree guard and force-add

**Context.** The runner is stateless; `.osspulse/state.json` is gitignored; a no-new-items run
leaves the file byte-identical, and `git commit` on a clean tree exits non-zero (would redden the
job). The push must not re-trigger the workflow (loop / DoS risk R-4).

**Decision (single reasonable approach — scope=tiny, no options table).** Persist inline in the
job with this exact sequence, gated on `success()` after the run step:

```bash
git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -f .osspulse/state.json                      # force-add: path is gitignored (AC-003)
if git diff --cached --quiet; then                   # clean-tree guard (AC-004)
  echo "state unchanged — nothing to persist"        # success exit, no empty commit
else
  git commit -m "chore(osspulse): persist state [skip ci]"   # [skip ci] marker (AC-005)
  git push
fi
```

Why: `git add -f` keeps `.gitignore` intact (rejected: un-ignoring the paths — leaks local dev
state/config into every commit, per handoff §2 WATCH). `git diff --cached --quiet` branches on the
STAGED diff so an unchanged run no-ops with exit 0 (rejected: `commit --allow-empty` — pollutes
history). `[skip ci]` **plus** the fact that a push authored by the default `GITHUB_TOKEN` does not
fire `on: schedule`/`on: push` gives two independent loop guards (AC-005).

**Consequences.** `permissions: contents: write` (only) is required or the push 403s (AC-005,
least privilege). `etags.json` is NOT persisted → ETag cache resets each CI run, first fetch per
endpoint unconditional — accepted for V3 (E-7). A `concurrency` group
(`group: osspulse-digest`, `cancel-in-progress: false`) serializes an overlapping manual +
scheduled run so two runners never race the committed file (AC-007); the V2-002 `fcntl` lock is
per-machine and does not span runners.

## Architecture Overview

Single workflow, single job on `ubuntu-latest`. Linear steps: checkout → setup Python 3.13 →
setup `uv` → `uv pip install -e .` (install from source) → `osspulse run` (secrets bound via
`${{ secrets.* }}` env) → persist step (ADR-001). Depends on: the `osspulse run` CLI contract
(exit 0 on success incl. no-new-items) and the committed `config.toml`.

**Workflow skeleton** (`.github/workflows/osspulse.yml`):

```yaml
name: osspulse-digest

on:
  schedule:
    - cron: "0 1 * * *"      # 01:00 UTC = 08:00 UTC+7 — Actions cron is UTC (AC-001)
  workflow_dispatch:          # manual trigger (AC-001)

concurrency:
  group: osspulse-digest      # serialize overlapping manual + scheduled runs (AC-007)
  cancel-in-progress: false   # let the in-flight run finish and persist

permissions:
  contents: write             # least privilege — only for the state commit-back (AC-005)

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v5
      - name: Install osspulse from source
        run: uv pip install --system -e .        # NOT pip install osspulse (not on PyPI, AC-002)
      - name: Run osspulse
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: osspulse run --config config.toml     # committed secret-free config (AC-002/011/006)
      - name: Persist state
        run: |                                     # ADR-001 exact sequence (AC-003/004/005)
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -f .osspulse/state.json
          if git diff --cached --quiet; then
            echo "state unchanged — nothing to persist"
          else
            git commit -m "chore(osspulse): persist state [skip ci]"
            git push
          fi
```

## API Design

_(unchanged — no HTTP/CLI API added; this is a committed CI artifact. No `openapi.yaml`.)_

## DB Schema

_(unchanged — no datastore; `.osspulse/state.json` is the existing JSON state store, format owned
by S3 state-store, not modified here.)_

## Error Mapping

Reuses the existing CLI error contract (config §conventions): `osspulse run` exits non-zero with
`Error: <message>` on `ConfigError`/`AuthError`. On the runner this fails the job **before** the
persist step (persist is gated on run success), so no partial/empty state is committed (AC-006,
E-8). A missing/invalid committed `config.toml` → `ConfigError` → job fails, no persist (AC-006).

## Sequence Flows

Scheduled/manual trigger → checkout → install-from-source → `osspulse run` (fetch → summarize →
render → deliver) → persist: `git add -f` → staged-diff check → (changed) commit `[skip ci]` +
push / (unchanged) no-op exit 0. Push by `GITHUB_TOKEN` does not re-trigger → no loop.

## Edge Cases

Per proposal §Edge Cases: E-1 unchanged state no-op (AC-004, ADR-001 guard) · E-2 concurrency
serialize (AC-007) · E-3/E-4 loop + permission (AC-005) · E-5 committed config (AC-002/011) ·
E-6 secrets only via `${{ secrets.* }}` (AC-010/011) · E-7 etags not persisted (accepted) ·
E-8 fatal run fails before persist (AC-006).

## Performance

_(unchanged — single daily job, single-repo watchlist within the 5000 req/hr token budget; etag
reset adds at most one unconditional first-page fetch per endpoint per run, E-7.)_

## Security

- **STRIDE I (disclosure, R-2):** secrets referenced ONLY via `${{ secrets.* }}` env bindings;
  committed `config.toml` holds env-var NAMES + non-secret watchlist config, never a value
  (AC-010/011). Persist commits ONLY `.osspulse/state.json` — never a secret-bearing file.
- **STRIDE E (privilege, R-3):** `permissions: contents: write` only, no broader scope (AC-005).
- **STRIDE D (loop/DoS, R-4):** `[skip ci]` + GITHUB_TOKEN-push-non-triggering + concurrency group.
- **STRIDE T (tampering, R-5):** committed `state.json` exposes seen issue IDs in a public repo —
  low sensitivity, accepted; noted for private-watchlist operators.

## Risk Assessment

- [R-1 gitignore trap] → `git add -f` + committed secret-free config; do NOT un-ignore (ADR-001).
- [AC-004 clean-tree commit fails] → `git diff --cached --quiet` guard before commit.
- [Workflow loop] → `[skip ci]` + GITHUB_TOKEN push non-triggering (two independent guards).
- [Secret leak] → `${{ secrets.* }}` only; a no-secret-substring check at the final checkpoint.

## Implementation Guide

**Recommended order** (matches tasks.md 1→6):
1. Commit a secret-free `config.toml` at repo root (copy from `config.example.toml`; env-var names
   only) — AC-002/011.
2. `.gitignore` unchanged — document the `git add -f` approach (do NOT un-ignore) — AC-003, R-1.
3. Author `.github/workflows/osspulse.yml` header + steps up to `osspulse run` — AC-001/002/005/007/008/010.
4. Add the persist step verbatim from ADR-001 — AC-003/004/005/006.
5. README required-secrets section (`LLM_API_KEY`, `DISCORD_WEBHOOK_URL`; `GITHUB_TOKEN` auto) — AC-009.
6. Final checkpoint: workflow lints as valid Actions YAML; `git diff` shows zero `src/` changes;
   no secret substring in any committed file; ACs V3-002-001..011 verified.

**Patterns to follow.**
- Contrast, do not import, `src/osspulse/schedule/workflow.py` — this CR differs on install source
  (`uv pip install -e .` not `pip install osspulse`), write permission, and the persistence step.
- Use `name: osspulse-digest` (distinct from the generator's `osspulse-run`) so the two artifacts
  don't collide.

**Gotchas.**
- `git diff --cached --quiet` (staged), not `git diff --quiet` (unstaged) — the force-add stages
  the file, so an unstaged check would always see "clean" and never commit.
- `uv pip install --system -e .` needs `--system` on the runner (no active venv).
- The persist step must run only after a successful `osspulse run` — never persist partial state.
