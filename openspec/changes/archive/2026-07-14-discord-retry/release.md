# Release — 001 (discord-retry)
Date: 2026-07-14
Deploy strategy: direct

## Release Notes

**Features**
- `DiscordDelivery` retries transient POST failures (429, 5xx, TimeoutException, RequestError)
  with exponential backoff before raising `DeliveryError` (AC-001-001, AC-001-002, AC-001-003,
  AC-001-005, AC-001-007, AC-001-008, AC-001-009)
- `max_retries` (default `3`), `backoff_base` (default `1.0`), and injectable `sleep` callable
  added to `DiscordDelivery.__init__` — no required config changes, all backwards-compatible
  (AC-001-001, AC-001-011)
- `Retry-After` header honoured: wait = `max(Retry-After, backoff_base * 2**attempt)` when
  numeric; gracefully ignored when missing/malformed (AC-001-006, AC-001-005b)
- Non-transient 4xx (400, 401, 403, 404) still fail immediately — no sleep, no retry
  (AC-001-004)
- Retry budget is **per POST**: each split message and each embed batch retries independently;
  already-delivered messages are never rolled back (AC-001-009)
- `max_retries=0` reproduces single-attempt / pre-change behaviour (AC-001-011)

**Bug fixes**
- None

**Breaking changes**
- None. New `__init__` parameters (`max_retries`, `backoff_base`, `sleep`) are keyword-only
  with defaults; existing callers require no change.

## Migration Checklist

No DB migrations. No schema changes. No config-file changes required.

| Order | Item | Done? | Notes |
|-------|------|-------|-------|
| — | No migrations | n/a | CLI-only change, no DB |

## Rollback Plan

CLI-only change — no DB migration, no data at risk.

1. `git revert <archive-merge-commit>` — reverts both the code change and the living-spec fold
   atomically (do NOT hand-edit `openspec/specs/delivery/spec.md`).
2. Re-install / re-run `uv sync` if the reverted commit touched `pyproject.toml` (it does not
   in this change).
3. Confirm rollback: `pytest tests/delivery/ -q` should reproduce pre-change single-attempt
   behaviour.

## Post-Deploy Smoke Test

- [ ] `osspulse run` completes with a valid webhook URL → digest delivered, exit 0
- [ ] `osspulse run` with a **bad** webhook URL (404) → single attempt, `Error: …` on stderr,
  exit 1, no URL in error output
- [ ] `pytest tests/delivery/test_discord_delivery.py -q` → 81 passed, 0 failed
- [ ] `pytest tests/ -q` (full suite) → all passed, 0 failed

## Archive

- [x] `openspec archive "discord-retry"` run — spec deltas merged into
  `openspec/specs/delivery/spec.md`, change moved to `openspec/changes/archive/discord-retry/`
- [ ] `_state.json.deploy_status` initialized: `{"master": "pending"}` — update to `pass`/`fail`
  after the branch is merged to master via `node .kiro/tools/state-set.mjs --change discord-retry
  --set deploy_status.master=pass`

## If Rejected After Archive (Revert Playbook)

- **Forward-fixable bug** (found in dev/stg or master without a real rollback): open a new
  `bugfix` pipeline. Do NOT hand-edit `openspec/specs/delivery/spec.md`.
- **Real rollback** (deploy reverted): `git revert <archive-merge-commit>` — undoes code AND
  living-spec fold in one commit. Never hand-edit the living spec back.
