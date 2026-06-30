# Architect — cross-spec lessons (append-only)

## 2026-06-29 — delivery-6: reuse atomic-write pattern across infra modules instead of reinventing

`state/json_store.py:save` establishes the canonical atomic-write pattern:
`mkstemp(dir=target.parent)` → `fdopen(utf-8)` write+flush+`os.fsync` → `os.replace` → `finally unlink`.
When a new infra adapter needs write-durability (delivery, future export, config snapshot),
reference this pattern explicitly in the ADR rather than designing a new approach.
Key constraint: temp file MUST be in `target.parent` (same filesystem) — NOT system `/tmp`.
Divergence point: delivery deliberately does NOT `mkdir -p` parent (fail-fast per AC-6-014);
state store does. Document this distinction per-adapter so it's not accidentally merged.

## 2026-06-29 — delivery-6: per-module error class mirrors module boundary cleanly

Pattern established across infra adapters: `ConfigError` (config.py) · `StateError` (state/) · `DeliveryError` (delivery/).
Each module owns exactly one error class re-raised from infrastructure exceptions (OSError, etc.),
surfaced to the CLI as `Error: <msg>` + exit 1 via `typer.echo(..., err=True)`.
When adding a new infra module, follow this pattern: one error class in `<module>/errors.py`,
catch at the CLI layer, never let raw OS exceptions propagate to the user.
