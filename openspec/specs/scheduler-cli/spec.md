# scheduler-cli Specification

## Purpose
TBD - created by archiving change scheduler-cli-7. Update Purpose after archive.
## Requirements
### Requirement: osspulse run orchestrates the full V1 pipeline end-to-end
The `osspulse run` command SHALL orchestrate the complete V1 pipeline in one invocation, wiring
Config → GitHub Collector → State Store → Summarizer → Digest Renderer → Delivery so that a single
run reads the watchlist, collects new issues per repo, records them as seen, summarizes them,
renders one Markdown digest, and delivers it. The orchestration SHALL live in
`osspulse.pipeline.run_pipeline(config: Config) -> None`, invoked by `osspulse.cli.run`, and each
stage SHALL receive only the data the previous stage produced. No pipeline stage module SHALL import
another pipeline stage module.

> ACs: AC-7-001 [CONFIRMED], AC-7-002 [CONFIRMED], AC-7-003 [CONFIRMED], AC-7-016 [CONFIRMED]
> Business rules: BR-7-006, BR-7-007
> Integration: INT-7-002, INT-7-003, INT-7-004, INT-7-005, INT-7-006
> Decision: D-1 (no-LLM-provider path)

#### Scenario: A successful run produces and delivers one digest (AC-7-001) [CONFIRMED]
- **WHEN** `osspulse run` is invoked with a valid config and ≥1 repo that has new issues
- **THEN** the pipeline collects issues, summarizes them, renders ONE Markdown digest aggregating all repos into `## {repo}` sections, delivers it exactly once via the configured Delivery adapter, and the command exits 0

#### Scenario: The pipeline wires stages without cross-stage coupling (AC-7-002) [CONFIRMED]
- **WHEN** the `osspulse.pipeline` module is imported and its imports are inspected statically
- **THEN** `run_pipeline` constructs each adapter from `Config` and passes data one direction, and no pipeline stage module (`github`, `state`, `summarizer`, `cache`, `render`, `delivery`) imports another stage module

#### Scenario: run_pipeline replaces the NotImplementedError stub (AC-7-003) [CONFIRMED]
- **WHEN** `run_pipeline(config)` is called with a valid config
- **THEN** it executes the real pipeline and does not raise `NotImplementedError`, and `cli.run` does not deliver the hardcoded `"osspulse: pipeline not yet implemented"` string

#### Scenario: Items from multiple repos are aggregated into one flat render call (AC-7-016) [CONFIRMED]
- **WHEN** two repos each return issues
- **THEN** the pipeline passes a single combined `list[SummarizedItem]` to `render(items, lookback_days=...)` (one call), and the renderer groups them into per-repo sections itself

### Requirement: The run iterates the watchlist with per-repo failure isolation
The run SHALL process each repo in `config.watched_repos` independently so that one repo's
recoverable failure does not abort the whole run. The run SHALL catch a recoverable collector error
(`InvalidRepoError`, `NetworkError`, or a non-auth `RateLimitError`/`CollectorError`) for a single
repo, log a warning, skip that repo, and continue with the remaining repos. An `AuthError` SHALL be
treated as fatal because all repos share one token. The run SHALL still deliver a digest of whatever
was collected when at least one repo succeeded or zero repos succeeded.

> ACs: AC-7-004 [CONFIRMED], AC-7-005 [CONFIRMED], AC-7-006 [CONFIRMED], AC-7-017 [CONFIRMED]
> Business rules: BR-7-001, BR-7-002, BR-7-008

#### Scenario: One repo fails, others succeed (AC-7-004) [CONFIRMED]
- **WHEN** one repo in the watchlist raises `InvalidRepoError` (e.g. 404 / renamed / private) and the others succeed
- **THEN** the failing repo is logged at WARN and skipped, the successful repos are summarized and rendered, and the command exits 0

#### Scenario: Authentication failure is fatal (AC-7-005) [CONFIRMED]
- **WHEN** the collector raises `AuthError` (401/403 — the shared token is invalid or revoked)
- **THEN** the run stops immediately, prints `Error: <message>` on stderr that contains no token value and no Python traceback, and the command exits 1

#### Scenario: All repos fail to collect (AC-7-006) [CONFIRMED]
- **WHEN** every repo fails with a recoverable error (each `InvalidRepoError`/`NetworkError`) so zero items are collected
- **THEN** the pipeline passes an empty list to `render`, which returns the "no new items in the last N days" doc, that doc is delivered, and the command exits 0

#### Scenario: Rate limit terminates collection but delivers partial results (AC-7-017) [CONFIRMED]
- **WHEN** after collecting some repos the collector raises a terminal `RateLimitError` (its own backoff exhausted) on a later repo
- **THEN** the run stops collecting further repos, logs the rate-limit reason at WARN, renders+delivers the items already collected, and the command exits 0

### Requirement: Summarization is wired with graceful degradation and a no-LLM path
The pipeline SHALL summarize collected items through the batch entry point
`LiteLLMSummarizer.summarize_items(...)` so that a single item's LLM failure is skipped and the run
continues. The pipeline SHALL skip the LLM entirely and render an unsummarized digest when
`config.llm_provider` is `None`, rather than erroring, keeping the run useful at zero LLM cost.

> ACs: AC-7-007 [CONFIRMED], AC-7-008 [CONFIRMED], AC-7-009 [CONFIRMED], AC-7-018 [CONFIRMED], AC-7-022 [CONFIRMED]
> Business rules: BR-7-009, BR-7-010
> Integration: INT-7-004
> Decision: D-1

#### Scenario: LLM is wired via the batch entry point (AC-7-007) [CONFIRMED]
- **WHEN** an LLM provider is configured and items are collected
- **THEN** the pipeline calls `summarize_items(items)` exactly once (not the per-item `summarize`), and items whose summarization fails are skipped+logged by the summarizer while the survivors are rendered

#### Scenario: No LLM provider configured (AC-7-008) [CONFIRMED]
- **WHEN** `config.llm_provider is None`
- **THEN** the pipeline does NOT construct or call the summarizer, wraps each `RawItem` as a `SummarizedItem` whose `summary` is the fixed placeholder string `"(no summary — LLM disabled)"`, renders the digest, delivers it, and exits 0

#### Scenario: Redis cache unreachable (AC-7-009) [CONFIRMED]
- **WHEN** an LLM provider is configured but the Redis summary cache is unreachable during a run
- **THEN** the summarizer's cache-aside degrades to a miss (re-summarize), the run does not crash, and the digest is still produced and delivered

#### Scenario: Summarizer returns fewer items than collected (AC-7-018) [CONFIRMED]
- **WHEN** the summarizer skips some items (fully-empty or per-item LLM failure) and returns fewer `SummarizedItem`s than were collected
- **THEN** only the returned survivors are rendered, the run still exits 0, and the skipped count is logged

#### Scenario: The no-LLM placeholder is visible in the rendered digest (AC-7-022) [CONFIRMED]
- **WHEN** a run with `config.llm_provider is None` renders a collected item that has a non-empty title
- **THEN** that item's rendered Markdown line contains the placeholder text `(no summary — LLM disabled)` (the renderer emits the non-empty placeholder; it is not omitted like an empty summary would be)

### Requirement: The run records collected items as seen for idempotency
The run SHALL record each collected item in the State Store via `mark_seen` so re-runs are
idempotent and a future V2 delta can use the recorded state. State writes SHALL be atomic and SHALL
preserve a write-once `first_seen_at`. The run SHALL NOT, in V1, filter already-seen items out of
the digest; recording seen state is V1 and seen-based suppression is V2 delta.

> ACs: AC-7-010 [CONFIRMED], AC-7-011 [CONFIRMED], AC-7-019 [CONFIRMED]
> Business rules: BR-7-003, BR-7-011
> Integration: INT-7-003

#### Scenario: Collected items are marked seen (AC-7-010) [CONFIRMED]
- **WHEN** a run collects N items across the watchlist
- **THEN** each item is recorded via `mark_seen` and the state file is written atomically, and re-running preserves each item's original `first_seen_at`

#### Scenario: V1 does not filter seen items (AC-7-011) [CONFIRMED]
- **WHEN** a run is executed twice with no new GitHub activity (the same issues are returned both times)
- **THEN** both runs render the same items (V1 records seen but does not suppress them) and produce a byte-identical digest

#### Scenario: Marking seen is decoupled from summarization outcome (AC-7-019) [CONFIRMED]
- **WHEN** an item is collected and marked seen but its summarization later fails and it is skipped
- **THEN** the item remains recorded as seen in the state file (collection, not summarization, is what "seen" records) and the run continues

### Requirement: The CLI preserves the established exit-code and error contract
The `osspulse run` command SHALL preserve the V1 CLI error contract so that handled errors exit
non-zero with a readable `Error: <message>` on stderr and no traceback, while success exits 0. The
command SHALL keep `BrokenPipeError` handling (redirect stdout→devnull, clean exit 0) and SHALL
surface `ConfigError`, `DeliveryError`, and fatal collector errors as `Error: <message>` exit 1. No
secret value SHALL ever appear in any message, log line, or delivered digest.

> ACs: AC-7-012 [CONFIRMED], AC-7-013 [CONFIRMED], AC-7-014 [CONFIRMED], AC-7-020 [CONFIRMED]
> Business rules: BR-7-004, BR-7-012
> Integration: INT-7-001 (consumes delivery-6 CLI contract)
> Risk: RF-1 (secret leakage)

#### Scenario: Config error exits 1 with a clear message (AC-7-012) [CONFIRMED]
- **WHEN** config is missing or invalid (e.g. no `GITHUB_TOKEN`, or an unreadable config file)
- **THEN** the CLI prints `Error: <message>` on stderr, shows no Python traceback, and exits 1

#### Scenario: Broken pipe on stdout delivery exits cleanly (AC-7-013) [CONFIRMED]
- **WHEN** stdout delivery's consumer closes the pipe early (raising `BrokenPipeError`)
- **THEN** the CLI handles it at top level (redirect stdout→devnull) and exits 0 with no traceback

#### Scenario: No secret appears in output or logs (AC-7-014) [CONFIRMED]
- **WHEN** any error is surfaced or any log line is emitted during a run that uses a non-empty `github_token` and `llm_api_key`
- **THEN** neither the token nor the api-key substring appears in captured stderr, captured logs, or the delivered digest content (asserted by a log-capture test)

#### Scenario: A file delivery failure exits 1 with a clear message (AC-7-020) [CONFIRMED]
- **WHEN** `destination = "file"` and the digest cannot be written (e.g. missing parent directory)
- **THEN** the CLI surfaces the `DeliveryError` as `Error: <message>` on stderr, shows no traceback, and exits 1

### Requirement: The run logs a per-repo outcome for observability
The run SHALL log one outcome line per repo so the operator can see what happened. The run SHALL log
the count of items collected or the skip reason at INFO/WARN level for each repo, and SHALL NOT emit
any secret value or a full stack trace for handled errors.

> ACs: AC-7-015 [CONFIRMED], AC-7-021 [CONFIRMED]
> Business rules: BR-7-005
> Risk: RF-4

#### Scenario: Per-repo outcome is logged (AC-7-015) [CONFIRMED]
- **WHEN** a run processes a watchlist of multiple repos where some succeed and some are skipped
- **THEN** each repo emits exactly one outcome log line (`collected N` or `skipped: <reason>`) and no secret value appears in any log line

#### Scenario: A run summary line is logged at the end (AC-7-021) [CONFIRMED]
- **WHEN** a run completes (successfully or with some repos skipped)
- **THEN** a final summary line is logged with total repos processed, total items collected, total summarized, and total skipped

