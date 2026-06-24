# Project Context

## Identity
- **Name**: OSS Pulse
- **Slug**: osspulse
- **One-liner**: A CLI tool that watches a self-chosen list of GitHub repos and produces an LLM-summarized digest of new issues (V1; discussions/releases in V2) so a user can understand a repo deeply before contributing.

## Domain
OSS Pulse helps a developer follow a watchlist of GitHub repositories and get a short, readable "what happened in the last N days" digest without manually opening Issues/Discussions/Releases tabs. The goal is depth of understanding (context to make quality contributions), explicitly NOT racing to claim "good first issues". It is a personal/self-host tool (single operator), not a multi-tenant SaaS. The project also serves as a portfolio piece demonstrating real-API integration under constraints (rate limits), delta data pipelines, LLM integration, scheduling, and notification.

## Modules / Bounded Contexts
| Module | Responsibility |
|--------|----------------|
| S1 Config & Watchlist | Read config, validate `org/repo`, manage the watched-repo list, lookback window |
| S2 GitHub Collector | Call GitHub API (REST V1; GraphQL for Discussions V2), paginate, handle rate limits, return raw items |
| S3 State Store | Record "what has been seen" to enable delta and avoid reprocessing (JSON file V1 → SQLite V2) |
| S4 Summarizer (LLM) | Turn raw text into a short summary via LiteLLM; handle errors/timeouts; cache results |
| S5 Digest Renderer | Aggregate summarized data into a readable Markdown digest |
| S6 Delivery | Deliver the digest (file/stdout V1 → email/webhook V2) |
| S7 Scheduler/CLI | `osspulse run` command; orchestrate the pipeline; cron in V2 |
| S8 Meta-summary & Insights | Cross-source meta-summary and repo-welcomeness metrics (V3) |

**Hard boundary**: S2 (GitHub I/O) and S4 (LLM I/O) MUST stay separate — each has its own rate limit/cost and must be mocked/tested independently.

## Primary Interfaces / Endpoints
- CLI command `osspulse run` — read watchlist → collect → (delta) → summarize → render → deliver. (No HTTP API; this is a CLI tool.)
- Config file (`config.toml`) + `.env` for secrets as the setup-once entry point.

## External Dependencies
- **GitHub API** (REST V1; GraphQL V2) — authenticated with the operator's `GITHUB_TOKEN` (read-only public-repo scope) for the 5000 req/hr limit.
- **LLM provider via LiteLLM** — provider chosen by the operator (e.g. OpenAI/Anthropic/Ollama); only the data the operator configured is sent there.
- **Redis** — summary cache (avoid re-summarizing already-summarized items, saving LLM cost/tokens).

## Principles / Non-negotiables
- **Watchlist model only** — never scan/crawl all of GitHub; the user picks repos.
- **Understanding over speed** — no real-time "issue opened 30s ago" alerts, no auto-claim/auto-PR.
- **Idempotent** — re-running must not produce duplicate digests or re-summarize seen items.
- **Each external dependency sits behind an interface** (GitHub client, LLM client, delivery) so it can be mocked in tests and swapped later.
- **State is a file in V1** — no DB server until genuinely needed (V2/V3).
- **Secrets via env / gitignored `.env`** — never hardcode or commit tokens; minimum scope only.
- **No user data sent to any third party** beyond the LLM provider the operator explicitly configured.
- **Digest must be readable in < 2 minutes** — if it is longer than reading GitHub directly, the tool failed.
