# Release Notes — delivery-6

**Date:** 2026-06-29
**Branch:** feature/6-delivery → feature/5-digest-renderer
**Type:** feature

---

## What Ships

S6 Delivery — the terminal sink that writes the rendered Markdown digest to a destination
chosen by config (`[output]` section). This completes the OSS Pulse V1 pipeline:
Config → Collector → State Store → Summarizer → Renderer → **Delivery**.

### New capabilities

- **File delivery (default):** atomic UTF-8 write via `tempfile.mkstemp(dir=target.parent)`
  → `os.fsync` → `os.replace`. A crash mid-write never leaves a partial file. Re-running
  overwrites byte-identically (idempotent).
- **Stdout delivery:** writes digest + one trailing newline to `sys.stdout`; clean for piping
  (`osspulse run | less`). Broken-pipe handled at the CLI top level — no stacktrace.
- **`[output]` config section:** `destination` (`"file"` | `"stdout"`, default `"file"`) +
  `output_path` (default `"./digest.md"`). Validated fail-fast at load time.
- **`DeliveryError`:** clear `Error: <message>` on stderr + exit 1 for every unwritable
  condition (missing parent dir, permission denied, target is a directory, disk full).
  Error message names the offending path.

### Modified

- `osspulse.ports.Delivery` Protocol: `send(digest: Digest)` → `deliver(content: str)` (D-1).
  No existing call sites were affected.
- `osspulse.models.Config`: gained `output_destination` and `output_path` fields.
- `osspulse.config.load_config`: gained `[output]` parse + validate step (step 9).
- `osspulse.cli`: adapter selection from config + `BrokenPipeError` / `DeliveryError`
  top-level handlers.

### ACs shipped

AC-6-001 through AC-6-020 (20/20). Tests: 245 pass, coverage 98.14%.

---

## Migration Checklist

No database migrations. No schema changes. No new external dependencies (stdlib only).

| Item | Status |
|------|--------|
| DB migration up() | N/A |
| DB migration down() | N/A |
| New env vars required | None |
| Config change required | Add `[output]` section to `config.toml` (optional — defaults apply) |
| Breaking changes | `Delivery.send(digest)` removed from Protocol — no known call sites |

---

## Rollback Plan

If delivery fails in production:

1. `git revert` the merge commit — reverts ports.py, models.py, config.py, cli.py, delivery/
2. The `[output]` config section is ignored by the previous version (unknown keys are
   skipped by `tomllib` + `load_config`), so config files with `[output]` remain safe.
3. Re-run `uv sync` to confirm no new dependencies were added (there are none).

No data loss risk — delivery only writes files; state store is untouched.

---

## Post-Deploy Smoke Test

```bash
# 1. File delivery (default)
osspulse run --config config.toml
cat ./digest.md   # should contain rendered Markdown

# 2. Stdout delivery
# Set destination = "stdout" in config.toml, then:
osspulse run --config config.toml | head -5   # clean output, no stacktrace

# 3. Missing parent dir → clean error
mkdir -p /tmp/test-delivery
osspulse run --config <(echo '[watchlist]
repos = ["a/b"]
[output]
destination = "file"
output_path = "/tmp/test-delivery/nope/digest.md"') 2>&1
# Expected: "Error: cannot write digest to ..." on stderr, exit 1

# 4. Invalid destination → config error at load
osspulse run --config <(echo '[watchlist]
repos = ["a/b"]
[output]
destination = "email"') 2>&1
# Expected: "Error: output.destination must be 'file' or 'stdout'..." on stderr, exit 1
```

---

## Deploy Strategy

**Direct deploy** (low risk — no DB, no migration, no infra change, single-operator CLI).

1. Merge `feature/6-delivery` → `feature/5-digest-renderer` (or main once full pipeline is wired).
2. `uv sync` on target machine.
3. Run post-deploy smoke test above.
4. Monitor: `cat ./digest.md` after first real run confirms output.
