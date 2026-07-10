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

> ACs: AC-7-004 [CONFIRMED], AC-7-005 [CONFIRMED], AC-7-006 [CONFIRMED], AC-7-017 [CONFIRMED], AC-V2-006-019 [CONFIRMED], AC-V2-006-020 [CONFIRMED], AC-V2-006-021 [CONFIRMED], AC-V2-006-022 [CONFIRMED]
> Business rules: BR-7-001, BR-7-002, BR-7-008, BR-V2-006-004, BR-V2-006-008, BR-V2-006-009
> Integration: INT-V2-006-002, INT-V2-006-003, INT-V2-006-004, INT-V2-006-005

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
