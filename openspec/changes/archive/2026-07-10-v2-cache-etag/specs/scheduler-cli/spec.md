## MODIFIED Requirements

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

## ADDED Requirements

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
