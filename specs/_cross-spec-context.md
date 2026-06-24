# Cross-Spec Context

> Knowledge bridge for OSS Pulse. Agents starting a NEW spec read this to learn what
> shared services/modules exist, what constraints prior specs set, and dependencies.
> Append-only on S3 approval. Never modify existing blocks.

---

## 1 — project-foundation (S3 done: 2026-06-21)
### Dependencies (from other specs)
- None (first spec).

### Shared Decisions
- ADR-001: Hand-written config validation (no Pydantic) — exact error messages, no coercion.
- ADR-002: Port interfaces use `typing.Protocol` (structural typing, fakes need no inheritance).
- ADR-003: `WatchedRepo(owner, name)` + `full_name` property — parsed/validated once at config time.
- ADR-004: Coverage omits `ports.py` + `pipeline.py`; gate ≥ 80% on config.py/cli.py/models.py.

### Exports (other specs may depend on these)
- `osspulse.models` — `WatchedRepo`, `Config`, `RawItem`, `SummarizedItem`, `Digest` dataclasses.
- `osspulse.ports` — Protocols: `GitHubClient`, `LLMClient`, `StateStore`, `SummaryCache`, `Delivery`.
- `osspulse.config.load_config(path, env=None) -> Config` + `ConfigError`.
- `osspulse.pipeline.run_pipeline(config)` — stub; future specs implement the body.

### Constraints Set (apply to subsequent specs)
- Secrets (GITHUB_TOKEN, LLM keys) come from env/.env only — never from config files; never logged/echoed.
- All adapters implement the `ports.py` Protocols; depend on `models`, not on each other.
- ConfigError-style domain errors are surfaced ONLY at the CLI boundary (stderr + non-zero exit, no traceback).
- New code measured by the ≥ 80% coverage gate; only pure stubs/interfaces may be added to `omit`.
- Toolchain fixed: Python 3.13 (mise), uv, ruff (lint+format), pytest+coverage, Typer CLI.

---
