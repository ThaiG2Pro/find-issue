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
  - TOML config parsing via stdlib `tomllib`; `.env` loading via `python-dotenv`

## Data
- **Database**: None in V1. State persisted as a JSON file. SQLite considered in V2 if needed.
- **ORM / data layer**: None (file-based state store behind an interface).
- **Cache / queue**: **Redis** — summary cache (keyed by item identity) to avoid re-calling the LLM. No message broker/queue.

## Testing
- **Test framework**: **pytest** (with mocks for the GitHub and LLM clients)
- **Coverage gate**: ≥ 80% lines
- **Integration test policy**: GitHub and LLM clients are mocked — tests MUST NOT hit real APIs. Redis may use a fake/in-memory client or a local test instance.

## Build / Tooling
- **Package manager**: **uv** (dependency resolution, lockfile, virtualenv)
- **Lint / format**: **ruff** (lint + format)
- **CI**: **GitHub Actions** (lint + tests; cron-based scheduled run is a V2 option)
- **Packaging**: `pyproject.toml`, installable via `pipx`/`uv`; small Docker image optional in V2.
