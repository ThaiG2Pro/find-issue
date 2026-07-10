# OSS Pulse

![CI](https://github.com/ThaiG2Pro/find-issuse/actions/workflows/ci.yml/badge.svg) ![License](https://img.shields.io/badge/license-MIT-blue.svg)

A CLI tool that watches a self-chosen list of GitHub repositories and produces an
LLM-summarized digest of new issues, releases, and discussions, so you can understand a
repo deeply before contributing — without manually scanning Issues, Releases, or
Discussions tabs.

Goal: depth of understanding, not speed. This is a personal/self-host tool for a
single operator; it is not a multi-tenant SaaS.

---

## Privacy Disclosure (RF-1)

**What is sent to the LLM provider?**

Only the `title` and `body` of each GitHub issue, release, or discussion are sent. No
other fields — no URL, no number, no tag name, no repository name, no GitHub username, no
creation date, no labels, and no GitHub API token — leave your machine as part of an LLM
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
git clone https://github.com/ThaiG2Pro/find-issuse.git
cd find-issuse

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

[output]
# Where to write the rendered digest.
# destination: "file" (default) writes to output_path; "stdout" pipes to standard output.
destination = "file"
# Path for the digest file (used only when destination = "file"). Default: ./digest.md
output_path = "./digest.md"
# destination = "discord" — POST to Discord webhook.
# Requires DISCORD_WEBHOOK_URL env var (https://discord.com/... or discordapp.com/...).
# webhook_env = "MY_VAR"  # optional: override the env var name

[delta]
# Suppress items already seen on a previous run (identity-based: repo + item type + item ID,
# not content — an edited-but-same-id item stays suppressed). Default: true.
# Set to false to restore V1 behavior: every collected item is rendered every run, regardless
# of whether it was seen before. Items are still recorded to the state file either way.
enabled = true
```

### `.env` (secrets — never commit)

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | GitHub personal access token. Minimum scope: `public_repo` (read-only). |
| `LLM_API_KEY` | Yes (unless Ollama) | API key for your configured LLM provider. |
| `LLM_PROVIDER` | No | Override the provider from `config.toml`. |
| `STATE_PATH` | No | Override the state file path from `config.toml`. |
| `DISCORD_WEBHOOK_URL` | When `destination = "discord"` | Discord webhook URL. Create at: channel ⚙️ → Integrations → Webhooks → Copy URL. |
| `REDIS_URL` | No | Redis connection URL for LLM summary caching (e.g. `redis://localhost:6379/0`). If absent, caching is disabled and the LLM is called on every run for new items. |

See `.env.example` for a full annotated template.

---

## Usage

```bash
# Run a digest (collect issues, releases, and discussions → summarize → write Markdown digest to configured destination)
uv run osspulse run

# Pipe to stdout instead (set destination = "stdout" in config.toml, or redirect)
uv run osspulse run  # with destination="stdout" → pipe freely: osspulse run | less

# Run without an LLM provider (no-LLM mode — see below)
uv run osspulse run  # omit [llm] section from config.toml

# Show help
uv run osspulse --help
```

### No-LLM mode (zero LLM cost)

If you omit the `[llm]` section from `config.toml` (or do not set `provider`), OSS Pulse
will still collect issues and produce a full Markdown digest — each item's summary will
read `(no summary — LLM disabled)` instead of an AI-generated summary. This is useful
for a first run to verify connectivity, or for operators who only need the raw issue list.

### Default LLM model (ADR-002)

The model string is read from `config.toml [llm] model`. If `model` is omitted, the
pipeline infers a sensible default per provider:

| Provider | Default model |
|----------|--------------|
| `openai` | `openai/gpt-4o-mini` |
| `ollama` | `ollama/llama3` |
| `anthropic` | `anthropic/claude-3-haiku-20240307` |
| `groq` | `groq/llama3-8b-8192` |
| other | `<provider>/<provider>` |

It is recommended to set `model` explicitly in `config.toml` for predictable costs.

### Redis cache (optional)

Set `REDIS_URL` in `.env` (e.g. `redis://localhost:6379`) to enable LLM summary caching.
If `REDIS_URL` is absent or Redis is unreachable, the run continues without caching —
the LLM is called for each new item on every run.

---

## Scheduling

osspulse is single-shot — it runs once and exits. All timing is delegated to the OS or CI.

### Generating a crontab line (OS cron — primary)

```bash
# Print the default daily crontab line (08:00 local time) — nothing is modified:
uv run osspulse schedule

# Choose a different cadence:
uv run osspulse schedule --preset hourly   # 0 * * * *
uv run osspulse schedule --preset weekly   # 0 8 * * 1
uv run osspulse schedule --cron "*/15 * * * *"

# Install (or replace) the managed block in your crontab:
uv run osspulse schedule --install

# Remove the managed block (no-op if absent):
uv run osspulse schedule --uninstall
```

The generated crontab line uses **absolute paths** for both the `osspulse` binary and
the config file so it runs correctly under cron's minimal `PATH`/`cwd`.

The managed block is delimited by `# >>> osspulse >>>` / `# <<< osspulse <<<` markers.
`--install` is idempotent — re-running replaces the block in place. All other crontab
lines outside the managed block are preserved byte-for-byte.

> **`python -m osspulse` users**: `osspulse schedule` resolves the binary via
> `shutil.which("osspulse")` first (works for pipx/pip console-script installs). If not
> found, it falls back to `os.path.abspath(sys.argv[0])`, which points to the module
> launcher, not the console-script. In this case, review the generated line before
> installing — the `which` path is strongly preferred for scheduled use.

### OS cron vs GitHub Actions UTC

**OS cron** evaluates expressions in the **system local timezone**. If your machine is
UTC+7, `0 8 * * *` fires at 08:00 ICT.

**GitHub Actions** evaluates `on.schedule.cron` in **UTC**. `0 8 * * *` fires at
08:00 UTC (= 15:00 ICT in the example above). Keep this in mind when choosing a cadence.

### Generating a GitHub Actions workflow (optional)

```bash
# Print the workflow YAML to stdout:
uv run osspulse schedule --github-actions

# Write to a file (atomically):
uv run osspulse schedule --github-actions --output .github/workflows/osspulse.yml
```

The generated workflow references `${{ secrets.GITHUB_TOKEN }}` and
`${{ secrets.LLM_API_KEY }}` from the repository secrets store — no secret value is
ever inlined into the YAML.

### Overlapping runs (cron-safe lock)

If a scheduled run is still active when the next cron tick fires, the second invocation
**logs a WARN and exits 0** (a benign skip — deliberately not an error so cron mail stays
quiet). The lock is a kernel advisory lock (`fcntl.flock`) that is auto-released if the
process dies (`kill -9`, crash) — no stale-lock heuristic is needed.

---

## Key Technical Decisions

- **Ports and adapters (hexagonal-lite)**: every external dependency (GitHub, LLM,
  delivery, state, cache) sits behind a Python `Protocol` interface so it can be
  swapped or mocked independently.
- **Digest includes Issues + Releases + Discussions (V2)**: the digest groups items per
  repo into `### Issues`, `### Releases`, and `### Discussions` sections. Releases are
  fetched via a dedicated `fetch_releases` method on the collector adapter; Discussions
  via `fetch_discussions` using the GitHub GraphQL API. The `GitHubClient` Protocol stays
  frozen (adapter-only extension). Draft releases (`published_at == null`) are excluded;
  prereleases are included. Release identity is `repo + "release" + tag_name`; Discussion
  identity is `repo + "discussion" + str(number)`.
- **GitHub Discussions via GraphQL**: `fetch_discussions` sends a POST to
  `https://api.github.com/graphql` with a fixed query constant and `owner`/`name`/cursor
  variables. The `GITHUB_TOKEN` is applied only to the httpx Authorization header — never
  in the GraphQL POST body. Repos where Discussions is disabled return an empty list
  (null-shape detection, ADR-003); the run continues unaffected. HTTP transport routing:
  `_request_with_retry` uses GET for REST calls and POST for GraphQL calls via the
  `json_body` parameter (ADR-002) — one shared retry/backoff path for both.
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

---

## Running on GitHub Actions

OSS Pulse ships a ready-to-use daily workflow at `.github/workflows/osspulse.yml`. It runs at
08:00 ICT (01:00 UTC) every day, installs the tool from source, runs `osspulse run`, and
commits `.osspulse/state.json` back to the repo so the next run starts delta-aware.

### Required GitHub repo Secrets

Set these in your repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Required | Description |
|--------|----------|-------------|
| `LLM_API_KEY` | Yes (unless Ollama) | API key for your configured LLM provider (OpenAI, Anthropic, etc.). |
| `DISCORD_WEBHOOK_URL` | Only when `destination = "discord"` | Discord webhook URL (channel ⚙️ → Integrations → Webhooks → Copy URL). |

`GITHUB_TOKEN` is **automatically provided** by GitHub Actions — no setup needed.

### Steps to enable

1. **Commit a `config.toml`** at the repo root (copy from `config.toml.ci.example`). This file
   must contain no secret values — only env-var names (e.g. `api_key_env = "LLM_API_KEY"`).
   Even though `config.toml` is listed in `.gitignore` for local dev, you must commit this CI
   copy via `git add -f config.toml` so the runner has it.

2. **Add the required secrets** listed above in your GitHub repo settings.

3. **Push the workflow** (`.github/workflows/osspulse.yml`) to your default branch. GitHub
   Actions will pick it up on the next scheduled tick or you can trigger it immediately with
   **Actions → OSS Pulse Daily Digest → Run workflow**.

4. After the first successful run, the workflow commits `.osspulse/state.json` back with a
   `[skip ci]` message. This is intentional — it records which items were seen so subsequent
   runs skip already-processed issues.

### Design notes

- **No `src/` changes**: the workflow file is pure CI config; all application logic lives in `src/`.
- **State persistence**: `.osspulse/` is gitignored locally but the CI step uses `git add -f`
  to stage only `state.json`. Your local `.gitignore` is unchanged.
- **No workflow loop**: the persistence commit uses `[skip ci]` and is pushed with the
  default `GITHUB_TOKEN`, which does not re-trigger `on: schedule` or `on: push`.
- **Concurrency**: `concurrency: group: osspulse-digest` with `cancel-in-progress: false`
  serializes overlapping manual + scheduled runs so two runners never race the state file.
