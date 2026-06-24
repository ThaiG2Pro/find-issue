# API & Code Conventions

> This is a CLI tool with no HTTP API. "API conventions" therefore cover the
> internal contract between pipeline stages (S1→S7) and the digest output format.

## API Response Format
N/A — no HTTP API. Internal stage contracts use plain Python dataclasses / typed
dicts passed one-directionally down the pipeline. Each stage's output is the next
stage's input (raw items → summarized items → rendered digest). No envelope wrapper.

**Success shape**: on success `osspulse run` exits `0` and writes the rendered
Markdown digest to the configured destination (file/stdout in V1). No JSON envelope.

**Error shape** (the CLI's error contract):
- **Exit codes**: `0` = success; non-zero = failure. `1` is used for invalid config
  and fatal errors (e.g. `ConfigError` → `typer.Exit(code=1)` in `cli.py`).
- **Error message format**: a readable one-line message on **stderr**, prefixed
  `Error: <message>` (e.g. `Error: GITHUB_TOKEN is required`). No raw stacktrace is
  shown to the user for expected/handled errors; tracebacks are only for unexpected bugs.
- **Outbound-error surfacing to the user**:
  - **GitHub 4xx** = permanent/caller error → report a clear message and stop (do not retry blindly).
  - **GitHub 5xx / 429 / rate-limit** = retryable → back off and retry; respect
    `X-RateLimit-Remaining`/`Retry-After`.
  - **LLM timeout/error** = degrade gracefully → treat as a cache miss / skip-item, log
    the failure, and continue the run rather than aborting the whole digest.

## HTTP Status Policy
N/A — no HTTP API surface is exposed. For *outbound* GitHub calls: treat 4xx as
caller/permanent errors (do not retry blindly), 5xx and 429/rate-limit responses as
retryable with backoff. Respect `X-RateLimit-Remaining`/`Retry-After`; pause before
hitting the limit rather than erroring.

## URL / Resource Naming
- Repos identified canonically as `org/repo` (lowercase, validated against the
  GitHub `owner/name` pattern).
- CLI commands are lowercase verbs (`run`, future: `add`, `list`, `remove`).

## Naming Conventions
- **Files/modules**: `snake_case.py`.
- **Classes**: `PascalCase` (e.g. `GitHubCollector`, `Summarizer`).
- **Functions/variables**: `snake_case`.
- **Constants**: `UPPER_SNAKE_CASE`.
- **Interfaces/ports**: name by role (`GitHubClient`, `LLMClient`, `Delivery`,
  `StateStore`), defined as `Protocol` or ABC.
- **Cache keys** (Redis): stable, content-addressable per item
  (e.g. `summary:{repo}:{item_type}:{item_id}:{content_hash}`).

## Validation
- Config validated on load: `org/repo` format, `lookback_days` is a positive int,
  required secrets present (`GITHUB_TOKEN`; LLM key if a remote provider is set).
- Fail fast with a clear message on bad config — do not start the pipeline.
- Treat all GitHub/LLM response data as untrusted (dirty data is expected); guard
  against missing fields rather than assuming shape.

## Documentation
- No OpenAPI (no HTTP API).
- README is the primary doc and a portfolio deliverable: setup, config schema, the
  privacy note (what is sent to the LLM provider), and the key technical decisions.
- CLI self-documents via Typer `--help`.
