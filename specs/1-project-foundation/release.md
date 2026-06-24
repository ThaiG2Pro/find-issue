# Release — osspulse v0.1.0
Date: 2026-06-22
Spec: 1-project-foundation
QA Decision: GO (2026-06-21, 0 Critical/High bugs)

---

## Release Notes

**osspulse v0.1.0** — Project Foundation

First release. Establishes the technical skeleton for the OSS Pulse CLI tool.

### Features

| AC-ID | Description |
|-------|-------------|
| AC-1-001 – AC-1-006 | Domain models: `Config`, `WatchedRepo`, `RawItem`, `SummarizedItem`, `Digest` as frozen dataclasses |
| AC-1-007 – AC-1-025 | `load_config()` — reads `config.toml` + env vars, validates all fields, raises `ConfigError` with clear messages |
| AC-1-026 – AC-1-034 | `osspulse run` CLI stub — validates config, exits cleanly, propagates all errors to stderr without tracebacks |
| AC-1-035 – AC-1-033 | Port interfaces (Protocol stubs): `GitHubClient`, `LLMClient`, `StateStore`, `SummaryCache`, `Delivery` |

### What this release does NOT include (by design — Scope B)
- No GitHub API adapter
- No LLM summarization
- No state store / cache implementation
- No digest rendering or delivery

---

## Migration Checklist

N/A — no database, no migrations.

---

## Dependency Review

- `uv pip check` → 63 packages, 0 conflicts ✅
- `pip-audit` not available in dev environment — **recommend running before tagging**:
  ```
  uv add --dev pip-audit
  uv run pip-audit
  ```
- All deps pinned via `uv.lock` ✅

Key runtime deps:
| Package | Version constraint | Purpose |
|---------|-------------------|---------|
| typer | >=0.12 | CLI framework |
| python-dotenv | >=1.0 | .env loading |
| httpx | >=0.27 | HTTP client (future adapters) |
| litellm | >=1.40 | LLM client (future adapters) |
| redis | >=5.0 | Cache (future adapters) |

---

## Smoke Test Plan (post-deploy)

Run after installing the package:

```bash
# 1. Help screen (exit 0, "run" command listed)
osspulse --help

# 2. Valid config → stub message (exit 0)
GITHUB_TOKEN=ghp_test osspulse run --config config.example.toml

# 3. Missing token → clean error, no traceback (exit 1)
osspulse run --config config.example.toml
# Expected: Error: GITHUB_TOKEN is required

# 4. Missing config file → clean error, no traceback (exit 1)
osspulse run --config /nonexistent.toml
# Expected: Error: cannot read /nonexistent.toml: file not found
```

All 4 scenarios must produce expected output with no Python tracebacks.

---

## Rollback Plan

This is a PyPI package release (or GitHub release tag). No infrastructure changes.

**If rollback needed**:
1. `pip install osspulse==<previous_version>` (or `uv add osspulse==<previous_version>`)
2. If no previous version exists (first release): `pip uninstall osspulse`
3. No data migration to undo — stateless CLI tool.

---

## Deploy Strategy

Direct release (no canary needed — CLI tool, no server):

1. Ensure CI gate passes on `main`:
   ```bash
   git push origin main
   # CI: ruff check + ruff format --check + pytest --cov-fail-under=80 → must be green
   ```

2. (Recommended) Run pip-audit:
   ```bash
   uv add --dev pip-audit && uv run pip-audit
   ```

3. Tag the release:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. Build and publish (if PyPI):
   ```bash
   uv build
   uv publish
   ```

5. Verify install from PyPI:
   ```bash
   pip install osspulse==0.1.0
   osspulse --help
   ```

6. Monitor for 30 min — check GitHub Issues for install/runtime errors.
