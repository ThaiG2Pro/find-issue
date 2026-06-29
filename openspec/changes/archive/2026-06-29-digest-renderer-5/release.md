# Release — 5 (digest-renderer-5)
Date: 2026-06-29
Deploy strategy: direct (pure additive module, no service restart required)

## Release Notes

**Features**

- Add `DigestRenderer` port (`Protocol`) to `osspulse.ports` with a keyword-only
  `render(items, *, lookback_days: int) -> str` contract
  (AC-5-001, AC-5-002, AC-5-003)
- Add `src/osspulse/render/renderer.py` — pure, deterministic Markdown digest renderer:
  - Repos emitted alphabetically (case-insensitive); items preserve input order
    (AC-5-005, AC-5-006, AC-5-007)
  - Fixed group order: Issues → Discussions → Releases → Khác (AC-5-006)
  - Byte-for-byte deterministic: same input → identical output on every call (AC-5-004)
  - Empty-input path returns a non-empty "No new items in the last N days" document
    (AC-5-008, AC-5-009)
  - Repos with no items produce no `##` section; empty item-type groups produce no
    `###` header (AC-5-010, AC-5-011)
  - Canonical item line format with U+2014 em-dash:
    `- #{id} "{title}" — {summary} [link]({url})` (AC-5-012, AC-5-013, AC-5-014)
  - Graceful degradation for empty title / url / summary — segments omitted, never
    empty quotes or broken links, never raises (AC-5-015, AC-5-016, AC-5-017, AC-5-018)
  - Unknown `item_type` routed to trailing `### Khác` bucket — no item ever dropped
    (AC-5-019, AC-5-020)
  - `MarkdownDigestRenderer` adapter class delegates to the pure free function
- Export `render` + `MarkdownDigestRenderer` from `src/osspulse/render/__init__.py`
- 56 new tests (220 total); 100% line coverage on `osspulse.render` (49/49 stmts)

**Bug fixes**

- None (new module, no prior implementation)

**Breaking changes**

- None. This is a pure additive change:
  - New port added to `ports.py` (no existing port modified)
  - New package `src/osspulse/render/` (previously empty `__init__.py`)
  - No existing API, schema, config, or CLI surface changed

### What does NOT ship in this change (important)

The renderer is **not yet wired into the CLI pipeline**. As of this release:

- `pipeline.py` does not call `render()` or `MarkdownDigestRenderer`
- `cli.py` does not produce a rendered digest to the user
- The `osspulse run` command does not yet produce a digest to stdout/file

Wiring the renderer into the pipeline (S5 Delivery / S7 CLI orchestration) is a
**separate follow-on change**. This change delivers the renderer module + port so
that wiring change has a stable, tested, fully-covered foundation to depend on.
The port contract the wiring change must honor: `render(items, *, lookback_days=int)`
(keyword-only — `lookback_days` cannot be passed positionally).

## Migration Checklist

| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| — | No DB migrations | N/A | N/A | No | N/A |

This change adds only Python source files. No schema change, no config key added,
no new dependency, no environment variable required.

## Rollback Plan

1. Revert the feature-branch merge (`git revert -m 1 <merge-commit>` on `main`, or
   simply delete the merge if it has not been pushed to a shared branch yet).
2. No migration rollback needed — there is no schema or data change to undo.
3. Confirm rollback: run `pytest -q` — the renderer test files
   (`tests/test_render_*.py`) should be gone or the suite should pass at the
   pre-merge count. Import `from osspulse.render import render, MarkdownDigestRenderer`
   should fail (module no longer present).

Since the renderer is not yet wired into the CLI, a rollback has zero user-visible
impact on `osspulse run` behavior.

## Post-Deploy Smoke Test

- [ ] `pytest -q` → 220 passed (or the count at the time of the release), 0 failed
- [ ] `python -c "from osspulse.render import render, MarkdownDigestRenderer; print('OK')"` → prints `OK`
- [ ] `python -c "from osspulse.ports import DigestRenderer; print('OK')"` → prints `OK`
- [ ] `python -m ruff check src/osspulse/render/` → exit 0, no output
- [ ] Import isolation check: `python -c "import ast, pathlib; src=pathlib.Path('src/osspulse/render/renderer.py').read_text(); tree=ast.parse(src); bad=[n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith('osspulse.') and not n.module.startswith('osspulse.models')]; assert bad==[], bad; print('isolation OK')"` → prints `isolation OK`

No HTTP endpoint, no service restart, no config change — smoke is pure import + pytest.

## Archive

- [x] `openspec archive digest-renderer-5` run — spec deltas merged into the living spec,
  change moved to `openspec/changes/archive/digest-renderer-5/`
