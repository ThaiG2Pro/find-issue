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
recoverable failure does not abort the whole run. For each repo the run SHALL collect newly opened
issues (`fetch_items`), newly published releases (`fetch_releases`) AND newly created discussions
(`fetch_discussions`) and SHALL concatenate them into that repo's contribution to the single
`list[RawItem]` that flows into the delta → summarize → render → deliver path. The run SHALL catch a
recoverable collector error (`InvalidRepoError`, `NetworkError`, or a non-auth
`RateLimitError`/`CollectorError`) for a single repo — from the issue, release, or discussion fetch —
log a warning, skip that portion, and continue with the remaining repos. A repo whose Discussions are
disabled (surfaced by the collector as an empty discussion list) SHALL simply contribute no
discussion items, with no error. An `AuthError` SHALL be treated as fatal because all repos share one
token. The run SHALL still deliver a digest of whatever was collected when at least one repo succeeded
or zero repos succeeded. Discussion collection SHALL add no new pipeline stage and SHALL NOT cause any
stage module to import another; `pipeline.py` remains the only cross-stage importer.

When conditional ETag caching is active (see the ETag-cache config requirement), `run_pipeline` SHALL
build a `JsonFileETagStore` best-effort — mirroring the best-effort Redis summary-cache build, so any
construction/load failure yields a no-op null cache and the run continues with unconditional fetches —
and SHALL inject it into the `GitHubCollector`. The collector's `set()` calls SHALL update only the
in-memory cache during collection; `run_pipeline` SHALL call `conditional_cache.commit()` exactly
once, **after** the per-repo collection loop has completed and each collected repo's items have been
recorded via `mark_seen`. If the run aborts before that commit (a fatal `AuthError` or `StateError`,
or any crash during collection), `etags.json` SHALL be left unchanged so the next run re-fetches those
endpoints and no item is ever `304`-skipped before it was recorded seen.

> ACs: AC-7-004 [CONFIRMED], AC-7-005 [CONFIRMED], AC-7-006 [CONFIRMED], AC-7-017 [CONFIRMED], AC-V2-006-019 [CONFIRMED], AC-V2-006-020 [CONFIRMED], AC-V2-006-021 [CONFIRMED], AC-V2-006-022 [CONFIRMED], AC-V2-007-019 [CONFIRMED], AC-V2-007-024 [CONFIRMED], AC-V2-007-025 [CONFIRMED]
> Business rules: BR-7-001, BR-7-002, BR-7-008, BR-V2-006-004, BR-V2-006-008, BR-V2-006-009, BR-V2-007-008
> Integration: INT-V2-006-002, INT-V2-006-003, INT-V2-006-004, INT-V2-006-005, INT-V2-007-002

#### Scenario: One repo fails, others succeed (AC-7-004) [CONFIRMED]
- **WHEN** one repo in the watchlist raises `InvalidRepoError` (e.g. 404 / renamed / private) and the others succeed
- **THEN** the failing repo is logged at WARN and skipped, the successful repos are summarized and rendered, and the command exits 0

#### Scenario: Authentication failure is fatal (AC-7-005) [CONFIRMED]
- **WHEN** the collector raises `AuthError` (401/403 — the shared token is invalid or revoked) on the issue, release, or discussion fetch
- **THEN** the run stops immediately, prints `Error: <message>` on stderr that contains no token value and no Python traceback, and the command exits 1

#### Scenario: All repos fail to collect (AC-7-006) [CONFIRMED]
- **WHEN** every repo fails with a recoverable error (each `InvalidRepoError`/`NetworkError`) so zero items are collected
- **THEN** the pipeline passes an empty list to `render`, which returns the "no new items in the last N days" doc, that doc is delivered, and the command exits 0

#### Scenario: Rate limit terminates collection but delivers partial results (AC-7-017) [CONFIRMED]
- **WHEN** after collecting some repos the collector raises a terminal `RateLimitError` (its own backoff exhausted) on a later repo
- **THEN** the run stops collecting further repos, logs the rate-limit reason at WARN, renders+delivers the items already collected, and the command exits 0

#### Scenario: Each repo is collected for issues, releases and discussions (AC-V2-006-019) [CONFIRMED]
- **WHEN** a repo returns 2 new issues, 1 new release and 3 new discussions within the window
- **THEN** the pipeline collects all 6 as `RawItem`s (2 `issue`, 1 `release`, 3 `discussion`) and concatenates them into the single item list for that repo before the delta step

#### Scenario: Discussions flow through the delta filter and are marked seen (AC-V2-006-020) [CONFIRMED]
- **WHEN** a discussion collected on run 1 is collected again on run 2 with `delta_enabled = true`
- **THEN** run 1 renders and records the discussion seen (`repo + "discussion" + number`), and run 2 suppresses it as previously-seen — reusing the v2-001 delta filter and state store with no change

#### Scenario: Discussions render under the existing Discussion group with no renderer change (AC-V2-006-021) [CONFIRMED]
- **WHEN** a repo's collected items include discussions and the digest is rendered
- **THEN** the discussions appear under that repo's `### Discussion (N)` group (between issues and releases), produced by the unchanged renderer whose `GROUP_ORDER` already includes `"discussion"`

#### Scenario: A per-repo discussion-fetch failure is isolated (AC-V2-006-022) [CONFIRMED]
- **WHEN** a repo's `fetch_discussions` raises a recoverable error while its `fetch_items`/`fetch_releases` succeeded
- **THEN** the discussion failure is logged at WARN and that repo's discussions are skipped, but the issues and releases already collected for that repo (and all other repos) are still summarized, rendered and delivered, and the command exits 0

#### Scenario: run_pipeline builds and injects the ETag store best-effort (AC-V2-007-019) [CONFIRMED]
- **WHEN** conditional caching is active and `run_pipeline` constructs the collector — and separately when `JsonFileETagStore` construction/load fails
- **THEN** on success a `JsonFileETagStore` over `config.etag_cache_path` is injected into the `GitHubCollector`, and on any build failure a no-op null cache is injected instead and the run continues with unconditional fetches

#### Scenario: commit is called only after the collection loop and mark_seen (AC-V2-007-024) [CONFIRMED]
- **WHEN** a run collects several repos successfully
- **THEN** `conditional_cache.commit()` is invoked exactly once, after the per-repo loop completes and every collected repo's items have been recorded via `mark_seen` — never per-repo mid-loop and never before `mark_seen`

#### Scenario: Aborting before commit leaves etags.json unchanged so no item is lost (AC-V2-007-025) [CONFIRMED]
- **WHEN** a run receives a first-page `200` for a repo, collects items, but then aborts before `commit()` (e.g. a later repo raises a fatal `AuthError`, or `mark_seen` raises `StateError`)
- **THEN** `etags.json` on disk is unchanged from before the run, so the next run issues an unconditional (or previously-cached) request for that endpoint and re-collects those items — the ETag optimization never causes an item to be skipped before it was recorded seen

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
idempotent and the recorded state drives the V2 delta filter. State writes SHALL be atomic and
SHALL preserve a write-once `first_seen_at`. When `config.delta_enabled` is `true` (the V2
default), the run SHALL filter already-seen items out of the digest so a re-run over unchanged
activity renders the "no new items" document; when `delta_enabled` is `false` the run SHALL NOT
suppress seen items (preserving the original V1 behavior). Recording seen state SHALL remain
decoupled from summarization outcome.

> ACs: AC-7-010 [CONFIRMED], AC-7-011 [CONFIRMED], AC-7-019 [CONFIRMED]
> Business rules: BR-7-003, BR-7-011, BR-V2-001-001
> Integration: INT-7-003

#### Scenario: Collected items are marked seen (AC-7-010) [CONFIRMED]
- **WHEN** a run collects N items across the watchlist
- **THEN** each item is recorded via `mark_seen` and the state file is written atomically, and re-running preserves each item's original `first_seen_at`

#### Scenario: V2 delta suppresses previously-seen items on re-run (AC-7-011) [CONFIRMED]
- **WHEN** a run is executed twice with no new GitHub activity (the same issues are returned both times) and `delta_enabled = true`
- **THEN** the first run renders the items and records them seen, and the second run renders the "no new items in the last N days" document (previously-seen items are suppressed) — this replaces the V1 behavior where both runs rendered identical items

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

### Requirement: The run filters out previously-seen items when delta is enabled
The run SHALL suppress from the digest any collected item that was already recorded as seen on a
previous run, when `config.delta_enabled` is `true`. An item SHALL count as NEW if and only if
`state.is_seen(repo, item_type, item_id)` returns `false` at the instant BEFORE this run records
it via `mark_seen`. The run SHALL still call `mark_seen` on ALL collected items (new and
previously-seen alike) so `first_seen_at` history is preserved and idempotency is maintained; the
filter SHALL affect only WHICH items are summarized and rendered, never WHICH items are recorded.
This applies per collected item across the whole watchlist.

> ACs: AC-V2-001-001 [CONFIRMED], AC-V2-001-004 [CONFIRMED], AC-V2-001-005 [CONFIRMED], AC-V2-001-010 [CONFIRMED]
> Business rules: BR-V2-001-001, BR-V2-001-002
> Modifies: scheduler-cli AC-7-011 (see MODIFIED Requirements)

#### Scenario: First run shows all items (empty prior state) (AC-V2-001-001) [CONFIRMED]
- **WHEN** `osspulse run` executes with `delta_enabled = true` against an empty/missing state file and a repo returns 3 new issues
- **THEN** all 3 issues are rendered (nothing was previously seen) and all 3 are recorded via `mark_seen`

#### Scenario: Item is NEW iff not seen before this run's mark_seen (AC-V2-001-004) [CONFIRMED]
- **WHEN** a repo returns issue #6 (never seen) and issue #5 (recorded as seen on a prior run), with `delta_enabled = true`
- **THEN** only #6 is passed to the summarizer/renderer, while BOTH #5 and #6 are recorded via `mark_seen` (the seen-snapshot is taken before `mark_seen`, so #6 — first seen this run — still appears)

#### Scenario: Second run with no new activity suppresses everything (AC-V2-001-005) [CONFIRMED]
- **WHEN** a run collects the exact same issues a previous run already recorded as seen, with `delta_enabled = true`
- **THEN** the filtered list is empty, `render([])` returns the "no new items in the last N days" document, that document is delivered, and the command exits 0

#### Scenario: mark_seen is called for every collected item regardless of filtering or delta_enabled (AC-V2-001-010) [CONFIRMED]
- **WHEN** a run collects N items across the watchlist, of which M are already previously-seen (0 ≤ M ≤ N), for BOTH `delta_enabled = true` and `delta_enabled = false`
- **THEN** `mark_seen` is invoked exactly N times (once per collected item) in both configurations — the count of recorded items equals the count of collected items and is independent of `delta_enabled` and of how many items the filter suppresses; only the number of items passed to summarize/render differs (N when `false`, N−M when `true`). This is the direct guard against a filter-before-`mark_seen` reorder (R1): any ordering bug that skips recording a filtered item makes this count drop below N and fails the test.

### Requirement: Delta suppression is config-gated and defaults to enabled
The run SHALL read a `[delta]` config section whose `enabled` field (boolean, default `true`)
determines whether the delta filter is applied. `config.py` SHALL parse and validate the
`[delta]` section at load time and SHALL fail fast with a `ConfigError` on an invalid value
(non-boolean), never at run time. When the section is absent the run SHALL default to
`delta_enabled = true`. When `delta_enabled` is `false` the run SHALL behave exactly as V1 (no
suppression). The `Config` dataclass SHALL gain a `delta_enabled: bool` field.

> ACs: AC-V2-001-002 [CONFIRMED], AC-V2-001-006 [CONFIRMED], AC-V2-001-007 [CONFIRMED]
> Business rules: BR-V2-001-003
> Integration: INT-V2-001-001 (consumes state-store is_seen)

#### Scenario: delta defaults to enabled when the section is absent (AC-V2-001-002) [CONFIRMED]
- **WHEN** a config file has no `[delta]` section
- **THEN** `load_config` returns a `Config` with `delta_enabled = true`

#### Scenario: delta_enabled=false reproduces V1 behavior (AC-V2-001-006) [CONFIRMED]
- **WHEN** the config sets `[delta] enabled = false` and a run collects issues already recorded as seen
- **THEN** all collected items are rendered (no suppression) and the digest is byte-identical to a V1 run over the same items

#### Scenario: An invalid delta.enabled value fails config validation (AC-V2-001-007) [CONFIRMED]
- **WHEN** the config has `[delta]` with `enabled = "yes"` (or any non-boolean)
- **THEN** `load_config` raises `ConfigError` with a clear message before the pipeline runs

### Requirement: Delta operates only in the pipeline and reuses the frozen state helpers
The delta filter SHALL live entirely in `osspulse.pipeline` and SHALL reuse
`JsonFileStateStore.is_seen` unchanged. This change SHALL NOT alter the `StateStore` Protocol, add
methods to it, or change the signatures of `is_seen`/`mark_seen`. No pipeline stage module SHALL
import another stage module (the existing AC-7-002 boundary is preserved).

> ACs: AC-V2-001-003 [ASSUMED], AC-V2-001-008 [CONFIRMED], AC-V2-001-009 [CONFIRMED]
> Business rules: BR-V2-001-004
> Integration: INT-V2-001-001

#### Scenario: State Store Protocol and helpers are unchanged (AC-V2-001-003) [ASSUMED]
- **WHEN** the delta feature is added
- **THEN** `osspulse.ports.StateStore` still declares exactly `load() -> dict` and `save(state: dict) -> None`, and `is_seen`/`mark_seen` keep their existing signatures — the filter calls `is_seen` from `pipeline.py` only

#### Scenario: Empty-after-filter still delivers the no-new-items doc, never suppresses delivery (AC-V2-001-008) [CONFIRMED]
- **WHEN** every collected item is previously-seen and `delta_enabled = true`
- **THEN** delivery still runs exactly once (the "no new items" document is written to file / printed to stdout); the run never skips delivery and never produces an empty file

#### Scenario: A corrupt or unreadable state file surfaces as a run error, never silently disables the filter (AC-V2-001-009) [CONFIRMED]
- **WHEN** `delta_enabled = true` and the state file is corrupt or unreadable so `JsonFileStateStore.load()` raises `StateError` (AC-3-009)
- **THEN** the run surfaces the error as `Error: <message>` on stderr and exits 1; the run SHALL NOT swallow the error, SHALL NOT silently treat all items as new, and SHALL NOT proceed with the filter disabled

### Requirement: osspulse schedule generates an OS crontab entry for osspulse run
The `osspulse schedule` command SHALL generate a ready-to-use OS crontab entry that invokes
`osspulse run` on a cadence, printing the line to stdout by default so nothing in the operator's
environment is mutated implicitly. The cadence SHALL be selectable via `--preset {hourly|daily|weekly}`
or `--cron "<expr>"`; when neither is given the command SHALL default to a daily schedule at 08:00
local time. The generated invocation SHALL use absolute paths for both the `osspulse` binary and the
config file so the entry works under cron's minimal cwd/PATH. This is the primary scheduling
mechanism per PROJECT_SPEC §8 (OS cron), and osspulse SHALL remain single-shot with timing delegated
to cron.

> ACs: AC-V2-002-001 [CONFIRMED], AC-V2-002-002 [CONFIRMED], AC-V2-002-003 [CONFIRMED], AC-V2-002-004 [CONFIRMED], AC-V2-002-005 [CONFIRMED], AC-V2-002-008 [CONFIRMED]
> Business rules: BR-V2-002-006, BR-V2-002-007, BR-V2-002-001
> Integration: INT-V2-002-002

#### Scenario: Bare schedule prints a daily crontab line (AC-V2-002-001) [CONFIRMED]
- **WHEN** `osspulse schedule` is invoked with no cadence flag
- **THEN** it prints one crontab line to stdout that runs `osspulse run` on the default daily schedule and exits 0, without touching the operator's crontab

#### Scenario: Explicit cron expression is used verbatim (AC-V2-002-002) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "30 6 * * 1"` is invoked with a valid expression
- **THEN** the printed crontab line begins with `30 6 * * 1` and invokes `osspulse run`

#### Scenario: Preset maps to a standard expression (AC-V2-002-003) [CONFIRMED]
- **WHEN** `osspulse schedule --preset hourly` (and likewise `daily`, `weekly`) is invoked
- **THEN** the printed line uses the corresponding standard cron expression (`hourly` → `0 * * * *`, `daily` → `0 8 * * *`, `weekly` → `0 8 * * 1`)

#### Scenario: Generated invocation uses absolute paths (AC-V2-002-004) [CONFIRMED]
- **WHEN** any crontab line is generated
- **THEN** both the `osspulse` executable and the `--config` path in the line are absolute paths (the binary is resolved via `shutil.which("osspulse")`, falling back to an absolute resolution of `sys.argv[0]`; the config path is resolved to its absolute form), never relative, so the entry runs correctly under cron's minimal working directory and minimal PATH — and the command does NOT attempt to verify the binary against the cron daemon's PATH (emitting the absolute path makes cron-PATH verification unnecessary)

#### Scenario: No cadence flag defaults to daily 08:00 local (AC-V2-002-008) [CONFIRMED]
- **WHEN** `osspulse schedule` is invoked with neither `--cron` nor `--preset`
- **THEN** the generated expression is `0 8 * * *` (daily 08:00 in the system local timezone)

#### Scenario: Generated crontab line contains no secret value (AC-V2-002-005) [CONFIRMED]
- **WHEN** `osspulse schedule` generates a crontab line in an environment where `GITHUB_TOKEN` and any LLM key are set
- **THEN** neither the token nor the api-key value appears anywhere in the generated line — the line references the config / environment, not the raw secret

### Requirement: Schedule specification is validated before any write
The command SHALL validate the resolved schedule specification before performing any file write or
crontab mutation so an invalid input fails fast with no partial side effect. An invalid cron
expression SHALL surface as `Error: <message>` on stderr with no Python traceback and exit 1, and
supplying both `--cron` and `--preset` SHALL be rejected as mutually exclusive.

> ACs: AC-V2-002-006 [CONFIRMED], AC-V2-002-007 [CONFIRMED]
> Business rules: BR-V2-002-003

#### Scenario: Invalid cron expression fails fast (AC-V2-002-006) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "99 * * * *"` (an out-of-range field) is invoked
- **THEN** the command prints `Error: <message>` on stderr, shows no traceback, exits 1, and neither prints a crontab line nor mutates any crontab

#### Scenario: --cron and --preset are mutually exclusive (AC-V2-002-007) [CONFIRMED]
- **WHEN** `osspulse schedule --cron "0 8 * * *" --preset daily` is invoked
- **THEN** the command reports the flags are mutually exclusive on stderr and exits 1 without generating anything

### Requirement: schedule --install manages a marker-delimited crontab block idempotently
The `osspulse schedule --install` command SHALL install the generated entry inside a
marker-delimited managed block in the invoking user's crontab so repeated installs never create
duplicate entries and all crontab content outside the managed block is preserved verbatim.
Installation SHALL be opt-in (default behavior is print-only). `--uninstall` SHALL remove only the
managed block, and SHALL be a no-op exit 0 when no managed block is present. The command SHALL
operate on the invoking user's crontab only and SHALL never use elevated privileges.

> ACs: AC-V2-002-009 [CONFIRMED], AC-V2-002-010 [CONFIRMED], AC-V2-002-011 [CONFIRMED], AC-V2-002-012 [CONFIRMED], AC-V2-002-013 [CONFIRMED]
> Business rules: BR-V2-002-002
> Integration: INT-V2-002-001

#### Scenario: Install adds a managed block (AC-V2-002-009) [CONFIRMED]
- **WHEN** `osspulse schedule --install` is invoked and the user crontab has no osspulse block
- **THEN** a marker-delimited block (e.g. `# >>> osspulse >>>` … `# <<< osspulse <<<`) containing the cron line is added to the crontab and the command exits 0

#### Scenario: Re-install is idempotent (AC-V2-002-010) [CONFIRMED]
- **WHEN** `osspulse schedule --install` is invoked twice (or with a changed cadence)
- **THEN** the managed block is replaced in place and the crontab contains exactly one osspulse managed block (no duplicate entries)

#### Scenario: Install preserves unrelated crontab lines (AC-V2-002-011) [CONFIRMED]
- **WHEN** the user crontab already contains unrelated jobs and `--install` runs
- **THEN** every line outside the osspulse managed block is preserved byte-for-byte

#### Scenario: Uninstall removes only the managed block (AC-V2-002-012) [CONFIRMED]
- **WHEN** `osspulse schedule --uninstall` is invoked
- **THEN** only the osspulse managed block is removed, unrelated lines remain, and when no block exists the command is a no-op that exits 0

#### Scenario: crontab command unavailable is reported clearly (AC-V2-002-013) [CONFIRMED]
- **WHEN** `--install` or `--uninstall` runs on a host with no `crontab` command on PATH
- **THEN** the command prints `Error: <message>` on stderr, shows no traceback, and exits 1

#### Scenario: Install writes the absolute-path line without verifying the cron daemon PATH (AC-V2-002-024) [CONFIRMED]
- **WHEN** `osspulse schedule --install` installs the managed block
- **THEN** the installed cron line invokes the `shutil.which`/`sys.argv[0]`-resolved absolute `osspulse` binary path (AC-V2-002-004), and the command does NOT probe or assert the binary's presence on the cron daemon's PATH — because the emitted absolute path is independent of cron's minimal PATH, no such verification is performed

### Requirement: schedule --github-actions emits a secretless CI cron workflow
The `osspulse schedule --github-actions` command SHALL emit a GitHub Actions workflow that runs
`osspulse run` on an `on.schedule.cron` trigger, referencing the repository secrets store for the
GitHub token and any LLM key so no secret value is ever inlined. The generated workflow SHALL
document that GitHub Actions cron is evaluated in UTC. With `--output PATH` the workflow SHALL be
written to that path; an unwritable destination SHALL fail with `Error: <message>` exit 1 and leave
no partial file.

> ACs: AC-V2-002-014 [CONFIRMED], AC-V2-002-015 [CONFIRMED], AC-V2-002-016 [CONFIRMED], AC-V2-002-017 [CONFIRMED]
> Business rules: BR-V2-002-001
> Integration: INT-V2-002-004

#### Scenario: Workflow YAML has a schedule trigger (AC-V2-002-014) [CONFIRMED]
- **WHEN** `osspulse schedule --github-actions` is invoked
- **THEN** the emitted YAML is a valid workflow containing an `on.schedule` with a `cron` expression and a job step that runs `osspulse run`

#### Scenario: Workflow references secrets, never inlines them (AC-V2-002-015) [CONFIRMED]
- **WHEN** a workflow is generated in an environment where `GITHUB_TOKEN`/LLM key are set
- **THEN** the token and key are referenced via `${{ secrets.* }}` and neither raw value appears anywhere in the generated YAML

#### Scenario: --output writes a file, unwritable path errors cleanly (AC-V2-002-016) [CONFIRMED]
- **WHEN** `--github-actions --output <path>` is given a path whose parent directory is not writable
- **THEN** the command prints `Error: <message>` on stderr, exits 1, and writes no partial file

#### Scenario: Workflow documents UTC cron semantics (AC-V2-002-017) [CONFIRMED]
- **WHEN** a workflow is generated
- **THEN** the YAML includes a comment noting that GitHub Actions `schedule.cron` is evaluated in UTC (distinct from OS cron's local time)

### Requirement: osspulse run is cron-safe for unattended execution
The `osspulse run` command SHALL be safe to run unattended so that a cron/CI invocation never
blocks on input and produces deterministic, cron-friendly output. The command SHALL never prompt
and SHALL require no TTY, SHALL keep the deterministic exit-code contract (0 on success including
the no-new-items case; 1 on fatal ConfigError/AuthError/DeliveryError/StateError), and SHALL emit
no ANSI color codes when stdout is not a TTY.

> ACs: AC-V2-002-018 [CONFIRMED], AC-V2-002-019 [CONFIRMED], AC-V2-002-020 [CONFIRMED]
> Business rules: BR-V2-002-007
> Integration: INT-V2-002-002

#### Scenario: Run never prompts and needs no TTY (AC-V2-002-018) [CONFIRMED]
- **WHEN** `osspulse run` is invoked with stdin/stdout not attached to a terminal (as under cron)
- **THEN** the command completes the pipeline without ever awaiting interactive input

#### Scenario: Exit codes are deterministic for cron (AC-V2-002-019) [CONFIRMED]
- **WHEN** `osspulse run` completes a scheduled run
- **THEN** it exits 0 on success (including a delivered no-new-items digest) and exits 1 only on the established fatal errors, so cron can distinguish success from failure

#### Scenario: No ANSI color when not a TTY (AC-V2-002-020) [CONFIRMED]
- **WHEN** `osspulse run` writes to a non-TTY stdout (redirected to a file or cron mail)
- **THEN** the output contains no ANSI escape/color sequences

### Requirement: osspulse run enforces a single-instance lock to prevent overlapping schedules
The `osspulse run` command SHALL acquire an exclusive single-instance lock before executing the
pipeline so that at most one run mutates a given state file at a time, preventing a fast cron
cadence from racing two pipelines over the JSON state. The lock SHALL be co-located with the state
it protects (under `state_path.parent`). A second run that finds the lock held SHALL log a WARN and
exit 0 (a benign skip, not a failure), and the lock SHALL be released automatically on process exit
including an abnormal termination so a crashed run leaves no stale-lock deadlock.

> ACs: AC-V2-002-021 [CONFIRMED], AC-V2-002-022 [CONFIRMED], AC-V2-002-023 [CONFIRMED]
> Business rules: BR-V2-002-004, BR-V2-002-005
> Integration: INT-V2-002-003

#### Scenario: Run acquires the lock before the pipeline (AC-V2-002-021) [CONFIRMED]
- **WHEN** `osspulse run` starts
- **THEN** it acquires an exclusive lock under `state_path.parent` before invoking `run_pipeline`, and releases it when the run finishes

#### Scenario: Overlapping run skips benignly (AC-V2-002-022) [CONFIRMED]
- **WHEN** a second `osspulse run` starts while a first run still holds the lock
- **THEN** the second run does not execute the pipeline, logs a WARN that a run is already in progress, and exits **0** (a benign skip — deliberately NOT a distinct non-zero "skipped" code, so an overrunning cron cadence never emails a spurious failure)

#### Scenario: Lock auto-releases on crash (AC-V2-002-023) [CONFIRMED]
- **WHEN** a run holding the lock is terminated abnormally (e.g. `kill -9`)
- **THEN** the next scheduled run can acquire the lock (the `fcntl.flock` advisory lock is released by the OS kernel on process death) and is not blocked by a stale lock — no manual staleness heuristic (pidfile age / mtime timeout) is required

### Requirement: Conditional ETag caching is config-gated and requires delta to be enabled
The run SHALL read an optional `[etag_cache]` config section whose `enabled` field (boolean, default
`true`) and `path` field (string, default `./.osspulse/etags.json`) configure conditional GitHub
requests. `config.py` SHALL parse and validate the section at load time and SHALL fail fast with a
`ConfigError` on a non-boolean `enabled`, never at run time; an absent section SHALL default to
`etag_cache_enabled = true`. The `Config` dataclass SHALL gain `etag_cache_enabled: bool` and
`etag_cache_path: str` fields. Conditional requests (sending `If-None-Match`) SHALL be performed only
when BOTH `etag_cache_enabled` is `true` AND `delta_enabled` is `true`; when either is `false` the run
SHALL send no conditional header and SHALL leave `etags.json` untouched, because `delta_enabled = false`
means the operator wants every item rendered every run and a `304`-driven empty delta would violate
that.

> ACs: AC-V2-007-020 [CONFIRMED], AC-V2-007-021 [CONFIRMED], AC-V2-007-022 [CONFIRMED], AC-V2-007-023 [CONFIRMED]
> Business rules: BR-V2-007-009, BR-V2-007-010
> Integration: INT-V2-007-004

#### Scenario: etag_cache defaults to enabled when the section is absent (AC-V2-007-020) [CONFIRMED]
- **WHEN** a config file has no `[etag_cache]` section
- **THEN** `load_config` returns a `Config` with `etag_cache_enabled = true` and `etag_cache_path = "./.osspulse/etags.json"`

#### Scenario: An invalid etag_cache.enabled value fails config validation (AC-V2-007-021) [CONFIRMED]
- **WHEN** the config has `[etag_cache]` with `enabled = "yes"` (or any non-boolean)
- **THEN** `load_config` raises `ConfigError` with a clear message before the pipeline runs

#### Scenario: Conditional requests require both flags true (AC-V2-007-022) [CONFIRMED]
- **WHEN** a run executes with `etag_cache_enabled = true` and `delta_enabled = true` and a validator is cached for an endpoint
- **THEN** the first-page request for that endpoint carries `If-None-Match`

#### Scenario: Either flag false disables conditional requests and leaves the cache untouched (AC-V2-007-023) [CONFIRMED]
- **WHEN** a run executes with `delta_enabled = false` (or `etag_cache_enabled = false`), regardless of the other flag
- **THEN** no first-page request carries an `If-None-Match` header and `etags.json` is neither written nor modified during the run

### Requirement: A run over an unchanged watchlist consumes near-zero rate-limit budget
When conditional caching is active and a subsequent run finds no new activity, the run SHALL still
produce and deliver a valid digest while issuing only `304`-answered conditional requests for the REST
endpoints (which do not count against the GitHub rate limit). A genuinely new item SHALL still be
collected and rendered on the run where the endpoint's first-page `ETag` changes.

> ACs: AC-V2-007-026 [CONFIRMED], AC-V2-007-027 [CONFIRMED], AC-V2-007-028 [CONFIRMED]
> Business rules: BR-V2-007-002, BR-V2-007-005
> Integration: INT-V2-007-002, INT-V2-007-003

#### Scenario: Second run with no new activity delivers the no-new-items digest for free (AC-V2-007-026) [CONFIRMED]
- **WHEN** run 1 collects items with a `200` (recording first-page ETags and committing them after `mark_seen`), then run 2 executes with no new GitHub activity so every REST first page answers `304`
- **THEN** run 2 delivers the "no new items in the last N days" document, exits 0, and issues only `304`-answered conditional REST requests (near-zero rate-limit consumption)

#### Scenario: A new item on the second run is collected and rendered (AC-V2-007-027) [CONFIRMED]
- **WHEN** run 2 executes after a new issue was opened, so the issues first-page returns `200` with a changed `ETag`
- **THEN** the collector paginates that endpoint, only the genuinely-new issue passes the delta filter and is rendered, and the fresh `ETag` is recorded and committed

#### Scenario: A corrupt etags.json does not break the run (AC-V2-007-028) [CONFIRMED]
- **WHEN** `etags.json` is corrupt at the start of a run
- **THEN** the ETag store logs a WARN and is treated as empty, the run fetches unconditionally, delivers its digest normally, and exits 0

