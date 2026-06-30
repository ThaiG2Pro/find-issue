# Contributing to OSS Pulse

Thanks for your interest! Here's how to get started.

## Setup

```bash
git clone https://github.com/ThaiG2Pro/find-issue.git
cd find-issuse
mise install
uv sync
cp .env.example .env
# Fill in GITHUB_TOKEN and LLM_API_KEY
```

## Running tests

```bash
uv run pytest --cov=osspulse --cov-report=term-missing
```

Coverage must stay at or above **80%**.

## Code style

```bash
uv run ruff check src tests
uv run ruff format src tests
```

All lint and format checks must pass before opening a PR.

## Submitting a PR

1. Fork the repo and create a branch from `main`
2. Make your changes with tests
3. Ensure `ruff` and `pytest` pass locally
4. Open a pull request — describe what you changed and why
