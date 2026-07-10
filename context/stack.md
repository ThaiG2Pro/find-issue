# Tech Stack

## Runtime & Language
- **Language**: Python 3.13
- **Runtime**: Python 3.13, version pinned and managed by **mise** (`.mise.toml`)

## Framework
- **Web/App framework**: None — this is a CLI tool. CLI built with **Typer**.
- **Key libraries**:
  - **httpx** — GitHub HTTP client (async-capable, modern)
  - **LiteLLM** — unified LLM client across providers (OpenAI/Anthropic/Ollama/…)
  - **Typer** — CLI framework
  - **redis** (`redis>=5.0`) — Redis client for the summary cache
  - TOML config parsing via stdlib `tomllib`; `.env` loading via `python-dotenv`

## Data
- **Database**: None in V1. State persisted as a JSON file. SQLite considered in V2 if needed.
- **ORM / data layer**: None (file-based state store behind an interface).
- **Cache / queue**: **Redis** — summary cache (keyed by item identity) to avoid re-calling the LLM. No message broker/queue.

## Testing
- **Test framework**: **pytest** (with mocks for the GitHub and LLM clients)
- **Coverage tooling**: **pytest-cov** (`tool.coverage`); `fail_under = 80`. `ports.py` is
  `omit`-ted from coverage (pure-interface Protocols). `pipeline.py` is now implemented and
  covered (S7 scheduler-cli-7) and is no longer omitted.
- **Coverage gate**: ≥ 80% lines
- **Integration test policy**: GitHub and LLM clients are mocked — tests MUST NOT hit real APIs. Redis may use a fake/in-memory client or a local test instance.

## Build / Tooling
- **Package manager**: **uv** (dependency resolution, lockfile, virtualenv)
- **Build backend**: **hatchling** (`build-system` in `pyproject.toml`); wheel packages `src/osspulse`.
- **Lint / format**: **ruff** (lint + format); `line-length = 100`, lint rules `E, F, I, UP`, target `py313`.
- **CI**: **GitHub Actions** (lint + tests; cron-based scheduled run is a V2 option)
- **Packaging**: `pyproject.toml`, installable via `pipx`/`uv`; entrypoint `osspulse = "osspulse.cli:app"`; small Docker image optional in V2.
