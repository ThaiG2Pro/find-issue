## MODIFIED Requirements

### Requirement: The run iterates the watchlist with per-repo failure isolation
The run SHALL process each repo in `config.watched_repos` independently so that one repo's
recoverable failure does not abort the whole run. For each repo the run SHALL collect BOTH newly
opened issues (`fetch_items`) AND newly published releases (`fetch_releases`) and SHALL concatenate
them into that repo's contribution to the single `list[RawItem]` that flows into the delta →
summarize → render → deliver path. The run SHALL catch a recoverable collector error
(`InvalidRepoError`, `NetworkError`, or a non-auth `RateLimitError`/`CollectorError`) for a single
repo — from either the issue or the release fetch — log a warning, skip that repo, and continue with
the remaining repos. An `AuthError` SHALL be treated as fatal because all repos share one token. The
run SHALL still deliver a digest of whatever was collected when at least one repo succeeded or zero
repos succeeded. Release collection SHALL add no new pipeline stage and SHALL NOT cause any stage
module to import another; `pipeline.py` remains the only cross-stage importer.

> ACs: AC-7-004 [CONFIRMED], AC-7-005 [CONFIRMED], AC-7-006 [CONFIRMED], AC-7-017 [CONFIRMED], AC-V2-003-019 [CONFIRMED], AC-V2-003-020 [CONFIRMED], AC-V2-003-021 [CONFIRMED], AC-V2-003-022 [CONFIRMED]
> Business rules: BR-7-001, BR-7-002, BR-7-008, BR-V2-003-004, BR-V2-003-006, BR-V2-003-007
> Integration: INT-V2-003-002, INT-V2-003-003, INT-V2-003-004

#### Scenario: One repo fails, others succeed (AC-7-004) [CONFIRMED]
- **WHEN** one repo in the watchlist raises `InvalidRepoError` (e.g. 404 / renamed / private) and the others succeed
- **THEN** the failing repo is logged at WARN and skipped, the successful repos are summarized and rendered, and the command exits 0

#### Scenario: Authentication failure is fatal (AC-7-005) [CONFIRMED]
- **WHEN** the collector raises `AuthError` (401/403 — the shared token is invalid or revoked) on either the issue or the release fetch
- **THEN** the run stops immediately, prints `Error: <message>` on stderr that contains no token value and no Python traceback, and the command exits 1

#### Scenario: All repos fail to collect (AC-7-006) [CONFIRMED]
- **WHEN** every repo fails with a recoverable error (each `InvalidRepoError`/`NetworkError`) so zero items are collected
- **THEN** the pipeline passes an empty list to `render`, which returns the "no new items in the last N days" doc, that doc is delivered, and the command exits 0

#### Scenario: Rate limit terminates collection but delivers partial results (AC-7-017) [CONFIRMED]
- **WHEN** after collecting some repos the collector raises a terminal `RateLimitError` (its own backoff exhausted) on a later repo
- **THEN** the run stops collecting further repos, logs the rate-limit reason at WARN, renders+delivers the items already collected, and the command exits 0

#### Scenario: Each repo is collected for both issues and releases (AC-V2-003-019) [CONFIRMED]
- **WHEN** a repo returns 2 new issues and 1 new release within the window
- **THEN** the pipeline collects all 3 as `RawItem`s (2 with `item_type = "issue"`, 1 with `item_type = "release"`) and concatenates them into the single item list for that repo before the delta step

#### Scenario: Releases flow through the delta filter and are marked seen (AC-V2-003-020) [CONFIRMED]
- **WHEN** a release collected on run 1 is collected again on run 2 with `delta_enabled = true`
- **THEN** run 1 renders and records the release seen (`repo + "release" + tag_name`), and run 2 suppresses it as previously-seen — reusing the v2-001 delta filter and state store with no change

#### Scenario: Releases render under the existing Release group with no renderer change (AC-V2-003-021) [CONFIRMED]
- **WHEN** a repo's collected items include releases and the digest is rendered
- **THEN** the releases appear under that repo's `### Release (N)` group (after issues), produced by the unchanged renderer whose `GROUP_ORDER` already includes `"release"`

#### Scenario: A per-repo release-fetch failure is isolated (AC-V2-003-022) [CONFIRMED]
- **WHEN** a repo's `fetch_releases` raises a recoverable error while its `fetch_items` succeeded
- **THEN** the release failure is logged at WARN and that repo's releases are skipped, but the issues already collected for that repo (and all other repos) are still summarized, rendered and delivered, and the command exits 0
