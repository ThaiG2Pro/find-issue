# Release — V2-003 (v2-003-releases)
Date: 2026-07-06T16:31:20+07:00
Deploy strategy: direct

## Release Notes

**Features**

- GitHub Releases added as a first-class pipeline source. `osspulse run` now collects
  issues **and** releases per watched repo, summarizes both, and renders them in the
  digest under a `### Releases (N)` section.
  (AC-V2-003-001, AC-V2-003-002, AC-V2-003-003, AC-V2-003-004, AC-V2-003-005,
   AC-V2-003-006, AC-V2-003-007, AC-V2-003-008, AC-V2-003-009, AC-V2-003-010,
   AC-V2-003-011, AC-V2-003-012, AC-V2-003-013, AC-V2-003-014)

- Release identity: `repo + "release" + tag_name` — reuses the existing item-type-agnostic
  state-store key; delta suppression and idempotency work unchanged.
  (AC-V2-003-019, AC-V2-003-020, AC-V2-003-021)

- Draft releases (`published_at == null`) are excluded; prereleases (`prerelease == true`)
  are included. (AC-V2-003-003, AC-V2-003-004)

- Token never appears in log messages or error strings; `_validate_repo` path-traversal
  guard applied before every fetch. (AC-V2-003-015, AC-V2-003-016, AC-V2-003-017)

- Release fetch failure is isolated per-repo: if `fetch_releases` raises a
  `CollectorError` (network, 5xx), issues for that repo still process normally. Fatal
  errors (`AuthError`, `RateLimitError`) propagate to abort the run. (AC-V2-003-022)

- `GitHubClient` Protocol stays frozen — `fetch_releases` is an adapter-only method.
  No new `CollectorConfig` field. (AC-V2-003-018)

- README updated: one-liner, Privacy Disclosure, Usage, and Key Technical Decisions
  sections now mention Releases. (Proposal note — non-AC; done in S6 cleanup.)

**Bug fixes**
- None.

**Breaking changes**
- None. The pipeline is item-type-agnostic downstream of the collector; no config
  changes are required. Existing state files remain valid.

---

## Migration Checklist

No database or schema migrations. OSS Pulse V1 uses a plain JSON state file; the
existing state-store key format (`repo + item_type + item_id`) already accepts
`"release"` items without modification.

| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | N/A — no migrations | — | — | No | N/A |

---

## Rollback Plan

This is a pure Python source change (two modified files: `client.py`, `pipeline.py`).
No schema change, no new dependency, no config change.

1. **Revert the code**: `git revert <merge-commit>` — removes `fetch_releases` +
   `_map_release` from `client.py` and the inner release guard + concatenation from
   `pipeline.py`. Issues-only behavior is fully restored.
2. **No migration rollback needed** — state files are forward/backward compatible; any
   `"release"` entries already recorded by the new code are simply ignored by the
   reverted pipeline (the delta filter and state store are item-type-agnostic).
3. **Confirm recovery**: `uv run osspulse run` completes without error; `digest.md`
   contains only `### Issues` sections; exit code 0.

**If rejected after `openspec archive`**: do not hand-edit the living spec.
See §Archive → "If Rejected After Archive" playbook: `git revert <archive-commit>`
undoes code + spec fold atomically. Open a new `bugfix` pipeline for forward fixes.

---

## Post-Deploy Smoke Test

- [ ] `uv run osspulse run` exits 0 and writes `digest.md` with at least one
  `### Releases` section (or "no new releases" if none in the lookback window) → ✅
- [ ] `uv run osspulse --help` prints help without error → ✅
- [ ] `GITHUB_TOKEN="" uv run osspulse run` exits 1 with `Error: GITHUB_TOKEN is required` → ✅
- [ ] A repo with recent releases shows them grouped under `### Releases (N)` in the digest → ✅
- [ ] A repo with no releases in the lookback window produces no `### Releases` section → ✅
- [ ] Re-running immediately after a successful run produces an identical digest (delta
  suppression — no duplicate release items) → ✅
- [ ] 459/459 tests pass: `uv run pytest --cov=osspulse` → 96% coverage ✅

---

## Archive

- [ ] `openspec archive "v2-003-releases"` run — spec deltas merged into the living spec,
  change moved to `openspec/changes/archive/`
- [ ] `_state.json.deploy_status` initialized: `{"dev": "pending", "master": "pending"}` —
  updated out-of-band as each promotion completes
  (`state-set --set deploy_status.dev=pass`, etc.)

## If Rejected After Archive (Revert Playbook)

Archive runs **before** this reaches dev/master. A bug caught downstream does not mean
re-opening this archived change:

- **Forward-fixable** (bug found in dev/stg, or in master with no rollback needed): open
  a new `bugfix` (or `hotfix` if already in master) pipeline. Do not touch this archived
  change or hand-edit the living spec.
- **Real rollback** (deploy reverted):
  `git revert <archive-merge-commit>` — `openspec archive` is a plain-file commit, so
  reverting it undoes code AND spec fold atomically. Never hand-edit
  `openspec/specs/**` back to the old state — let `git revert` do both at once.
