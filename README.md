# OSS Pulse

A CLI tool that watches a self-chosen list of GitHub repositories and produces an
LLM-summarized digest of new issues, so you can understand a repo deeply before
contributing — without manually scanning Issues tabs.

Goal: depth of understanding, not speed. This is a personal/self-host tool for a
single operator; it is not a multi-tenant SaaS.

---

## Privacy Disclosure (RF-1)

**What is sent to the LLM provider?**

Only the `title` and `body` of each GitHub issue are sent. No other fields — no
issue URL, no issue number, no repository name, no GitHub username, no creation
date, no labels, and no GitHub API token — leave your machine as part of an LLM
call.

The LLM provider is the **single provider you configure** in `config.toml` (e.g.
OpenAI, Anthropic, or a local Ollama instance). OSS Pulse does not send data to any
other third party. Issues are fetched only from the public repositories on your
explicit watchlist; the tool never crawls beyond that list.

If you use a local provider (Ollama), no data leaves your machine at all.

---

## Requirements

- Python 3.13 (managed by [mise](https://mise.jdx.dev/))
- [uv](https://github.com/astral-sh/uv) package manager
- A GitHub personal access token (public_repo read scope)
- A Redis instance (optional — used for LLM summary caching)
- An LLM provider API key, or a local Ollama instance

---

## Setup

```bash
# 1. Install mise + uv (if not already present)
brew install mise              # or: curl https://mise.run | sh
pip install uv                 # or follow https://github.com/astral-sh/uv#installation

# 2. Clone and enter the repo
git clone https://github.com/your-org/osspulse.git
cd osspulse

# 3. Install the correct Python version
mise install

# 4. Install project dependencies
uv sync

# 5. Configure secrets
cp .env.example .env
# Edit .env — set GITHUB_TOKEN and LLM_API_KEY (see variable reference below)

# 6. Configure your watchlist
cp config.example.toml config.toml
# Edit config.toml — add repos, set lookback_days, choose LLM provider
```

---

## Configuration

### `config.toml`

```toml
[watchlist]
# List of GitHub repos to monitor, in "owner/name" format.
repos = [
    "facebook/react",
    "python/cpython",
]
# How many days back to look for new issues (default: 7).
lookback_days = 7

[llm]
# LLM provider name — passed to LiteLLM.
# Options: "openai", "anthropic", "ollama", or any LiteLLM-supported provider.
provider = "openai"
# Model string in LiteLLM format (e.g. "openai/gpt-4o-mini", "anthropic/claude-3-haiku-20240307").
model = "openai/gpt-4o-mini"
# Name of the env var that holds the API key (default: LLM_API_KEY).
api_key_env = "LLM_API_KEY"

[state]
# Where to persist the state file (tracks seen issues for idempotency).
# Default: ./.osspulse/state.json
state_path = "./.osspulse/state.json"
```

### `.env` (secrets — never commit)

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | GitHub personal access token. Minimum scope: `public_repo` (read-only). |
| `LLM_API_KEY` | Yes (unless Ollama) | API key for your configured LLM provider. |
| `LLM_PROVIDER` | No | Override the provider from `config.toml`. |
| `STATE_PATH` | No | Override the state file path from `config.toml`. |
| `REDIS_URL` | No | Redis connection URL for LLM summary caching (e.g. `redis://localhost:6379/0`). If absent, caching is disabled and the LLM is called on every run for new items. |

See `.env.example` for a full annotated template.

---

## Usage

```bash
# Run a digest (collect issues → summarize → print Markdown to stdout)
uv run osspulse run

# Show help
uv run osspulse --help
```

---

## Key Technical Decisions

- **Ports and adapters (hexagonal-lite)**: every external dependency (GitHub, LLM,
  delivery, state, cache) sits behind a Python `Protocol` interface so it can be
  swapped or mocked independently.
- **Cache-aside for LLM summaries**: Redis stores already-computed summaries keyed by
  `summary:{repo}:{type}:{id}:{sha256(title+body)}`. Cache failures degrade gracefully
  — they never crash a run.
- **Idempotency via JSON state store**: a JSON file records which issue IDs have been
  seen. Re-running the tool does not re-summarize or re-emit already-processed items.
- **Hard S2/S4 boundary**: the GitHub collector (S2) and the LLM summarizer (S4) are
  strictly separate modules. They share only data models, never code or I/O channels.
- **Graceful LLM degradation**: a single item's LLM failure (timeout, rate-limit,
  error) is logged and skipped; the rest of the run continues normally.
- **Input cap**: issue bodies are truncated to 8000 characters before being sent to the
  LLM, keeping token costs predictable.
- **No DB in V1**: state is a plain JSON file. A database is not added until there is a
  demonstrated need (V2+).

---

## Development

```bash
# Lint + format check
uv run ruff check src tests
uv run ruff format --check src tests

# Run tests with coverage
uv run pytest --cov=osspulse --cov-report=term-missing

# Run a single test file
uv run pytest tests/test_summarizer_client.py -v
```

Coverage gate: >= 80% lines (CI hard-fails below this threshold).
