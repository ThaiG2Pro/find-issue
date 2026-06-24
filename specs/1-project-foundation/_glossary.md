# Glossary — 1-project-foundation

| Term | Definition | Defined by | Phase | AC/BR ref |
|------|-----------|-----------|-------|-----------|
| Foundation | The technical skeleton of the project: toolchain setup (mise/uv/ruff/pytest), port interfaces, config loader, and CLI stub — with no business adapters implemented yet | analyst | S1 | — |
| Port interface | A Python `Protocol` or ABC that defines the contract for an external dependency (GitHub, LLM, delivery, state, cache) without any implementation | analyst | S1 | — |
| Config | The validated in-memory representation of `config.toml` + env vars; produced by `config.py` and passed to the pipeline | analyst | S1 | — |
| WatchedRepo | A single `org/repo` entry in the watchlist, validated to match the `owner/name` pattern | analyst | S1 | — |
| FakeSummaryCache | An in-memory implementation of the `SummaryCache` port used in tests — no Redis, no network | analyst | S1 | — |
| Fail fast | The pattern where invalid config/env causes the tool to exit with a clear human-readable error message and non-zero exit code before starting the pipeline | analyst | S1 | EC-07, EC-08 |
| ConfigError | The exception type raised by `config.py` for any validation failure; caught at CLI boundary and printed as `Error: <message>` to stderr | analyst | S1 | EC-14 |
| `load_config(path, env)` | The public function in `config.py` that reads a TOML file + env vars and returns a validated `Config` object, or raises `ConfigError` | analyst | S2 | AC-1-011 |
| `RawItem` | Domain dataclass representing a single unprocessed item fetched from GitHub (issue, discussion, or release) | analyst | S2 | models.py |
| `SummarizedItem` | Domain dataclass representing a `RawItem` paired with its LLM-generated summary | analyst | S2 | models.py |
| Coverage omit | The `pyproject.toml` `[tool.coverage.run] omit` list that excludes stub/interface files from coverage measurement | analyst | S2 | BR-1-006 |
| `ConfigError` boundary | The single try/except in `cli.py` that converts a `ConfigError` to `Error: <msg>` on stderr + `typer.Exit(1)`; the only place config errors are presented | architect | S3 | BR-1-007 |
| `run_pipeline` | The pipeline orchestration entry function in `pipeline.py`; a stub raising `NotImplementedError` at foundation stage | architect | S3 | AC-1-008 |
| Bool trap | Python gotcha where `bool` is an `int` subclass, so `lookback_days = true` would pass an `isinstance(x, int)` check; mitigated with `type(x) is int` | architect | S3 | AC-1-020 |
| `x-cli-commands` | OpenAPI vendor extension used to document the CLI command contract since this tool exposes no HTTP paths | architect | S3 | — |
