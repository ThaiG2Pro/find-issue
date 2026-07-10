# Release — V2-001 (v2-001-delta-filter)
Date: 2026-07-03
Deploy strategy: direct (CLI tool — no HTTP service, no blue-green/canary required)

## Release Notes

**Features**

- **Delta filter: suppress previously-seen items on re-run** (AC-V2-001-001, AC-V2-001-004,
  AC-V2-001-005, AC-V2-001-010)
  By default (`[delta] enabled = true`), each run now filters out issues, discussions, and
  releases already recorded as seen on a previous run. Only new-since-last-run items appear in
  the digest. First-seen-this-run items always appear (seen-snapshot is taken before `mark_seen`
  writes, so new items are never accidentally suppressed).

- **`[delta]` config section** (AC-V2-001-002, AC-V2-001-007)
  New optional `[delta]` section in `config.toml`. `enabled = true` (default) activates delta
  suppression; `enabled = false` restores V1 behavior (all collected items always rendered).
  Non-boolean values (`"yes"`, `1`, etc.) raise `ConfigError` at startup — fail-fast, never
  silently accepted.

- **Empty-after-filter delivers "no new items" doc** (AC-V2-001-005, AC-V2-001-008)
  When every collected item is previously-seen, the pipeline passes an empty list to the
  renderer, which produces the standard "no new items" document. Delivery is never suppressed.

- **StateError on corrupt state surfaces as exit 1** (AC-V2-001-009)
  A corrupt or unreadable state file raises `StateError` → `Error: <msg>` on stderr, exit 1.
  The run never silently proceeds with the filter disabled.

- **StateStore Protocol unchanged** (AC-V2-001-003)
  `osspulse.ports.StateStore` still declares only `load`/`save`. `is_seen`/`mark_seen` remain
  adapter-only helpers on `JsonFileStateStore`. **Third-party `StateStore` adapters do not need
  any changes.**

- **Run-summary log extended** (AC-V2-001-010)
  Log line now includes `seen=M new=N-M` counts alongside `collected=N`, making it easy to
  diagnose unexpected suppression in logs.

**Bug fixes**
- None (this is a feature release).

**Breaking changes**
- **AC-7-011 behavior changed**: with `delta_enabled = true` (the new default), a second run
  over the same GitHub activity now renders the "no new items" document instead of re-rendering
  all issues. This is the intended V2 behavior. To preserve V1 behavior for existing users, add
  `[delta] enabled = false` to `config.toml` before upgrading.

**Dependency changes**
- None. No new packages added.

## Migration Checklist
| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | N/A — no database | — | — | — | — |

The state file schema (`{"version":1,"seen":{repo:{key:first_seen_at}}}`) is **unchanged**.
Delta only reads via `is_seen`; `mark_seen` behaviour is identical. No migration required.

## Rollback Plan
1. Revert the deploy by checking out or rolling back to the previous release commit
   (`git revert <archive-merge-commit>` — this undoes both the code and the spec fold atomically).
2. No migration rollback needed — state file schema is unchanged; existing `.osspulse/state.json`
   files are fully compatible with both V1 and V2.
3. Confirm rollback by running `uv run pytest -q` on the reverted code (all pre-delta tests
   should pass, delta tests should not exist on that commit).

**If a forward fix is preferred** (bug found in dev/stg/master but deploy not reverted):
open a new `bugfix` pipeline. Do not hand-edit the living spec or reopen this archived change.

## Post-Deploy Smoke Test
- [ ] `osspulse run --config config.toml` with `[delta]` absent → run completes, digest
      produced, no `ConfigError`. Confirms default `delta_enabled=true` is accepted.
- [ ] `osspulse run --config config.toml` with `[delta] enabled = false` → run completes,
      all items rendered (V1 behavior). Confirms escape hatch works.
- [ ] `osspulse run --config config.toml` with `[delta] enabled = "yes"` →
      `Error: delta.enabled must be a boolean`, exit 1. Confirms bool-trap guard.
- [ ] Run twice with same repo activity and `delta_enabled = true` → first run renders items,
      second run renders "no new items" doc. Confirms delta suppression end-to-end
      (requires a real GitHub token).
- [ ] State file exists after first run at `state_path` location; `seen` bucket populated for
      all collected items. Confirms `mark_seen` records the full list regardless of filter.
- [ ] R1 tripwire regression: `uv run pytest tests/test_pipeline.py::test_delta_mixed_new_and_seen_snapshot_before_mark_seen tests/test_pipeline.py::test_delta_mark_seen_count_invariant_both_modes -v` → both green.

**Note (SHALLOW_TC-001 future improvement):** the post-deploy two-run smoke test above is the
only practical way to verify the byte-identical guarantee end-to-end (real token required).

## Archive
- [ ] `openspec archive "v2-001-delta-filter"` run — spec deltas merged into the living spec,
      change moved to `openspec/changes/archive/`
- [ ] `_state.json.deploy_status` initialized: `{"dev":"pending","master":"pending"}` — updated
      out-of-band as each real promotion completes via
      `node .kiro/tools/state-set.mjs --change v2-001-delta-filter --set deploy_status.<env>=pass`.
      Not a gate — a breadcrumb only.

## If Rejected After Archive (Revert Playbook)
- **Forward-fixable** (bug found before master or in master without reverted deploy): open a new
  `bugfix` or `hotfix` pipeline. Do not touch this archived change or hand-edit `openspec/specs/`.
- **Real rollback** (deploy reverted): `git revert <archive-merge-commit>` — undoes code AND
  spec fold atomically. Never hand-edit `openspec/specs/scheduler-cli/spec.md` back manually.
