# github-collector Specification

## Purpose
TBD - created by archiving change github-collector-2. Update Purpose after archive.
## Requirements
### Requirement: Fetch newly-opened issues for a repo
The Collector SHALL fetch GitHub issues whose `created_at` falls within the last
`lookback_days` (UTC) for a single validated `owner/repo`, and return them as `RawItem`
objects with `item_type = "issue"`. It SHALL request `state=all` ordered by
`sort=created&direction=desc` so the newest issues arrive first (which enables early-stop
pagination). The lookback cutoff SHALL be computed as `now(UTC) - lookback_days`.

> ACs: AC-2-001 [CONFIRMED], AC-2-002 [CONFIRMED], AC-2-003 [CONFIRMED], AC-2-004 [CONFIRMED]
> Business rules: BR-2-001, BR-2-002, BR-2-009

#### Scenario: Issues within the lookback window are returned (AC-2-001) [CONFIRMED]
- **WHEN** a repo has 3 issues opened 1, 2 and 6 days ago and `lookback_days = 7`
- **THEN** all 3 are returned as `RawItem`s with `item_type = "issue"` and a correctly mapped `repo`, `item_id`, `title`, `body`, `url`, `created_at`

#### Scenario: Issues older than the cutoff are excluded (AC-2-002) [CONFIRMED]
- **WHEN** a repo has one issue opened 2 days ago and one opened 30 days ago and `lookback_days = 7`
- **THEN** only the 2-day-old issue is returned

#### Scenario: Repo with no issues in the window returns empty (AC-2-003) [CONFIRMED]
- **WHEN** a repo has no issues opened within `lookback_days`
- **THEN** an empty list is returned and no error is raised

#### Scenario: Issue opened then closed inside the window is still collected (AC-2-004) [CONFIRMED]
- **WHEN** an issue was opened 2 days ago and closed 1 day ago and `lookback_days = 7`
- **THEN** it is still returned, because the request uses `state=all` (created_at, not state, decides inclusion)

### Requirement: Map issue JSON to RawItem
The Collector SHALL map each collected GitHub issue to a `RawItem` using the
`project-foundation` contract: `repo` = the validated `owner/repo`; `item_type` =
`"issue"`; `item_id` = the issue `number` as a string; `title` = the issue title;
`body` = the issue body (empty string when `null`); `url` = the issue `html_url`;
`created_at` = the raw ISO-8601 `created_at` string (no reformatting).

> ACs: AC-2-016 [CONFIRMED], AC-2-017 [CONFIRMED]
> Business rules: BR-2-010

#### Scenario: item_id is the stringified issue number (AC-2-016) [CONFIRMED]
- **WHEN** an issue with `number = 42` is collected
- **THEN** the resulting `RawItem.item_id == "42"` (a string, not the GitHub global `id`)

#### Scenario: created_at is preserved as the raw ISO string (AC-2-017) [CONFIRMED]
- **WHEN** an issue has `created_at = "2026-06-20T08:15:30Z"`
- **THEN** the resulting `RawItem.created_at == "2026-06-20T08:15:30Z"` (unchanged, no reformatting)

### Requirement: Exclude pull requests
The Collector SHALL exclude any item that carries a `pull_request` field, because the
GitHub issues endpoint returns pull requests alongside issues.

> ACs: AC-2-018 [CONFIRMED]
> Business rules: BR-2-003

#### Scenario: Pull requests are dropped (AC-2-018) [CONFIRMED]
- **WHEN** the issues response contains 2 issues and 1 pull request (an item with a `pull_request` field)
- **THEN** only the 2 issues are returned and the pull request is omitted

### Requirement: Bounded pagination
The Collector SHALL page through results by following the `Link` header `rel="next"`
URL, and SHALL stop when either `max_items_per_repo` (config-driven, default 100) is
reached OR an item's `created_at` is before the lookback cutoff, whichever comes first.
Each page SHALL be requested with `per_page = page_size` (config-driven, default 100,
GitHub's max). Both `max_items_per_repo` and `page_size` SHALL be read from the
Collector configuration object — never hardcoded literals in the fetch loop. A missing
or malformed `Link` header SHALL be treated as no further pages. When the
`max_items_per_repo` cap is reached, the Collector SHALL emit an info-level log noting
the result was truncated.

> ACs: AC-2-005 [CONFIRMED], AC-2-006 [CONFIRMED], AC-2-007 [CONFIRMED], AC-2-024 [CONFIRMED]
> Business rules: BR-2-004, BR-2-005, BR-2-013

#### Scenario: Stops at the lookback cutoff mid-pagination (AC-2-005) [CONFIRMED]
- **WHEN** page 1 ends with items still inside the window and page 2 begins with an item older than the cutoff
- **THEN** the Collector stops after detecting the first out-of-window item and does not request any further pages

#### Scenario: Stops at the max-items cap with a truncation note (AC-2-006) [CONFIRMED]
- **WHEN** a repo has 250 in-window issues and `max_items_per_repo = 100`
- **THEN** exactly 100 `RawItem`s are returned and an info-level log records that the cap was reached for that repo

#### Scenario: Single page when no next link (AC-2-007) [CONFIRMED]
- **WHEN** the response has no `Link` header (or a malformed one)
- **THEN** the Collector returns the first page's in-window items without requesting more pages

#### Scenario: max_items_per_repo and page_size come from config, not hardcoded (AC-2-024) [CONFIRMED]
- **WHEN** the Collector is constructed with a config object setting `max_items_per_repo = 50` and `page_size = 25`
- **THEN** each page request carries `per_page=25` and the result is capped at 50 items — neither value is a literal baked into the fetch loop (changing config changes the behavior without code edits)

### Requirement: Authenticated requests without token leakage
The Collector SHALL authenticate every request with the operator's `GITHUB_TOKEN` via the
`Authorization` header and SHALL NEVER write the token value into logs, error messages, or
returned data. It SHALL issue only `GET` requests and SHALL NOT disable TLS verification.
The GitHub API base URL SHALL be a configuration constant (default
`https://api.github.com`), never derived from untrusted input — it is overridable via
config (e.g. for GitHub Enterprise) but never built from the `repo` argument or any
request data.

> ACs: AC-2-009 [CONFIRMED], AC-2-013 [CONFIRMED], AC-2-025 [CONFIRMED]
> Business rules: BR-2-006, BR-2-008, BR-2-014
> STRIDE: T-I1 (High), T-S1 / T-E1 (Medium)

#### Scenario: Token is sent but never leaked (AC-2-009) [CONFIRMED]
- **WHEN** any request is made or any error is logged
- **THEN** the request carries the `Authorization` header, but the `GITHUB_TOKEN` value never appears in any log line, exception message, or returned `RawItem`

#### Scenario: Only GET, TLS verification never disabled (AC-2-013) [CONFIRMED]
- **WHEN** the Collector issues any request to GitHub
- **THEN** the HTTP method is always `GET` and TLS certificate verification is never disabled

#### Scenario: Base URL is a config constant, never from untrusted input (AC-2-025) [CONFIRMED]
- **WHEN** the Collector builds a request URL
- **THEN** the host/scheme come from the configured base URL (default `https://api.github.com`); the `repo` argument only fills the validated `{owner}/{repo}` path segment and can never alter the host, scheme, or port

### Requirement: Rate-limit handling
The Collector SHALL respect GitHub rate limits using a single config-driven retry-policy
object (no retry constants scattered through the fetch loop). The retry policy SHALL
expose: `max_retries` (default 3), `backoff_base_seconds` (default 1.0),
`backoff_multiplier` (default 2.0), `jitter_seconds` (default 0.5, random 0..jitter added
per wait), and `backoff_ceiling_seconds` (default 60.0). The wait before retry N SHALL be
`min(backoff_base * multiplier**(N-1) + random_jitter, backoff_ceiling)`, EXCEPT that when
a `Retry-After` header is present its value SHALL take precedence (still capped by the
ceiling). The Collector SHALL back off and retry on `429` and `5xx` responses, and SHALL
treat a `403` carrying `X-RateLimit-Remaining: 0` as a rate-limit backoff rather than a
permanent auth error. After exhausting `max_retries` the Collector SHALL surface a clear
error. All five values SHALL come from the retry-policy config object so S3/S4 can tune
them without touching the fetch loop.

> ACs: AC-2-019 [CONFIRMED], AC-2-020 [CONFIRMED], AC-2-021 [CONFIRMED], AC-2-022 [CONFIRMED], AC-2-026 [CONFIRMED]
> Business rules: BR-2-005, BR-2-007, BR-2-013
> STRIDE: T-D1 (High)

#### Scenario: Backoff and retry on 429 (AC-2-019) [CONFIRMED]
- **WHEN** GitHub returns `429` with `Retry-After: 1`
- **THEN** the Collector waits the indicated interval and retries rather than failing immediately

#### Scenario: Secondary rate limit (403 with remaining 0) is a backoff (AC-2-020) [CONFIRMED]
- **WHEN** GitHub returns `403` with header `X-RateLimit-Remaining: 0`
- **THEN** the Collector treats it as a rate-limit backoff, not a permanent auth failure

#### Scenario: Backoff and retry on 5xx (AC-2-021) [CONFIRMED]
- **WHEN** GitHub returns `502`/`503` then succeeds on the next attempt
- **THEN** the Collector retries with exponential backoff and ultimately returns the items

#### Scenario: Retries are bounded by config then the error surfaces (AC-2-022) [CONFIRMED]
- **WHEN** GitHub keeps returning `503` past `max_retries` (default 3)
- **THEN** the Collector makes at most `max_retries` retry attempts, then stops and raises a clear error (no infinite retry)

#### Scenario: Retry policy values are read from config, not hardcoded (AC-2-026) [CONFIRMED]
- **WHEN** the Collector is constructed with a retry-policy config setting `max_retries = 5` and `backoff_base_seconds = 0.1`
- **THEN** the Collector makes up to 5 retry attempts using the configured base — the retry counts and backoff timings are not literals baked into the fetch loop, and changing the policy object changes behavior without code edits

### Requirement: Per-repo error isolation
The Collector SHALL isolate per-repo errors: a `404`/`410` for a repo SHALL be logged as
a warning and skipped (returning an empty list for that repo) so the run continues, while
a `401`/`403` auth failure (that is NOT a secondary rate limit) SHALL fail fast because it
affects every repo. Network/connection errors SHALL be retried (bounded) and then surfaced.

> ACs: AC-2-011 [CONFIRMED], AC-2-008 [CONFIRMED], AC-2-023 [CONFIRMED]
> Business rules: BR-2-007
> STRIDE: drives the structured per-repo audit log (T-R1)

#### Scenario: Missing repo is skipped, run continues (AC-2-011) [CONFIRMED]
- **WHEN** fetching a repo that returns `404` (or `410`)
- **THEN** a warning is logged, an empty list is returned for that repo, and no exception aborts the overall run

#### Scenario: Invalid token fails fast without leaking it (AC-2-008) [CONFIRMED]
- **WHEN** a request returns `401` (invalid/expired token) and `X-RateLimit-Remaining` is not `0`
- **THEN** the Collector raises a clear error that stops the run, without revealing the token value

#### Scenario: Network/timeout error is retried then surfaced (AC-2-023) [CONFIRMED]
- **WHEN** a connection times out repeatedly past `max_retries`
- **THEN** the Collector retries (bounded by the same retry-policy object) and then raises a clear connection error

### Requirement: Tolerate dirty response data
The Collector SHALL treat all GitHub response data as untrusted: it SHALL guard against
missing or `null` fields (e.g. `body`, `user`, `html_url`, `title`) and map them to safe
defaults rather than crashing.

> ACs: AC-2-010 [CONFIRMED], AC-2-012 [CONFIRMED]
> Business rules: BR-2-010
> STRIDE: T-T1 (High)

#### Scenario: Null body is coerced to empty string (AC-2-010) [CONFIRMED]
- **WHEN** an issue is returned with `body: null`
- **THEN** the resulting `RawItem.body` is an empty string and no error is raised

#### Scenario: Missing optional field does not crash (AC-2-012) [CONFIRMED]
- **WHEN** an issue JSON omits an expected field (e.g. `html_url` or `user`)
- **THEN** the Collector substitutes a safe default and still returns the item

### Requirement: Validate the repo identifier
The Collector SHALL reject any `repo` value that does not match the strict pattern
`^[\w.-]+/[\w.-]+$` before issuing any request, as defense-in-depth against an
SSRF-shaped request path (over and above S1 config validation).

> ACs: AC-2-014 [CONFIRMED]
> Business rules: BR-2-011
> STRIDE: T-T2 (Medium)

#### Scenario: Malformed repo is rejected before any request (AC-2-014) [CONFIRMED]
- **WHEN** the Collector is called with `repo = "../evil"`, `"a/b/c"`, or `""`
- **THEN** it raises an error before any HTTP request is made

### Requirement: Configuration-driven tunables (no hardcoded literals)
The Collector SHALL read every tunable value from a configuration object passed at
construction — no magic numbers, URLs, or counts baked into the fetch loop. The tunables
and their locked defaults are: `max_items_per_repo` = 100, `page_size` = 100,
`base_url` = `"https://api.github.com"`, and a `retry_policy` object
(`max_retries` = 3, `backoff_base_seconds` = 1.0, `backoff_multiplier` = 2.0,
`jitter_seconds` = 0.5, `backoff_ceiling_seconds` = 60.0). Defaults SHALL apply when a
value is omitted, and an explicit config value SHALL override the default without any
code change. The `base_url` SHALL remain GET-only and SHALL NEVER be sourced from the
`repo` argument or any response/untrusted input.

> ACs: AC-2-027 [CONFIRMED]
> Business rules: BR-2-013, BR-2-014

#### Scenario: Defaults apply when config omits values (AC-2-027) [CONFIRMED]
- **WHEN** the Collector is constructed with no overrides
- **THEN** it behaves as `max_items_per_repo=100`, `page_size=100`, `base_url="https://api.github.com"`, and `retry_policy(max_retries=3, backoff_base_seconds=1.0, backoff_multiplier=2.0, jitter_seconds=0.5, backoff_ceiling_seconds=60.0)` — and supplying any of these via config overrides the default with no source-code change

### Requirement: Pure I/O boundary
The Collector SHALL be pure GitHub I/O: it SHALL NOT read or write the State Store and
SHALL NOT call the LLM/Summarizer. It SHALL depend only on `osspulse.models` (and its
HTTP client), implementing the existing `osspulse.ports.GitHubClient` Protocol.

> ACs: AC-2-015 [CONFIRMED]
> Business rules: BR-2-012
> Integration: INT-2-001, INT-2-002, INT-2-003

#### Scenario: No state or LLM access (AC-2-015) [CONFIRMED]
- **WHEN** the Collector fetches items
- **THEN** it neither reads/writes any State Store nor invokes any LLM client; it only returns `RawItem`s via `fetch_items(repo, lookback_days)`

---

### Requirement: Fetch newly-published releases for a repo
The Collector SHALL fetch GitHub releases whose `published_at` falls within the last
`lookback_days` (UTC) for a single validated `owner/repo`, and return them as `RawItem` objects with
`item_type = "release"`. It SHALL call the REST endpoint `GET /repos/{owner}/{repo}/releases`. A
release is included when it is **published** and its `published_at` is at or after the cutoff
`now(UTC) - lookback_days`; a **draft** release (`published_at == null`) SHALL be excluded and a
prerelease SHALL be included. A repo with no qualifying releases SHALL return an empty list without
raising. This release path SHALL be exposed as an adapter method `fetch_releases(repo, lookback_days)`
and SHALL NOT add a method to the frozen `osspulse.ports.GitHubClient` Protocol.

> ACs: AC-V2-003-001 [CONFIRMED], AC-V2-003-002 [CONFIRMED], AC-V2-003-003 [CONFIRMED], AC-V2-003-004 [CONFIRMED], AC-V2-003-005 [CONFIRMED]
> Business rules: BR-V2-003-002, BR-V2-003-003
> Integration: INT-V2-003-001

#### Scenario: Releases within the lookback window are returned (AC-V2-003-001) [CONFIRMED]
- **WHEN** a repo has 2 releases published 1 and 5 days ago and `lookback_days = 7`
- **THEN** both are returned as `RawItem`s with `item_type = "release"` and correctly mapped `repo`, `item_id`, `title`, `body`, `url`, `created_at`

#### Scenario: Releases older than the cutoff are excluded (AC-V2-003-002) [CONFIRMED]
- **WHEN** a repo has one release published 2 days ago and one published 40 days ago and `lookback_days = 7`
- **THEN** only the 2-day-old release is returned

#### Scenario: Draft releases are skipped (AC-V2-003-003) [CONFIRMED]
- **WHEN** a repo returns a release with `published_at = null` (a draft) alongside one published yesterday, with `lookback_days = 7`
- **THEN** only the published release is returned and the draft is omitted

#### Scenario: Prereleases are included (AC-V2-003-004) [CONFIRMED]
- **WHEN** a repo returns a release with `prerelease = true` published within the window
- **THEN** it is returned as a `RawItem` (a prerelease still counts as a release)

#### Scenario: Repo with no releases returns empty (AC-V2-003-005) [CONFIRMED]
- **WHEN** a repo has no releases (or none within `lookback_days`)
- **THEN** an empty list is returned and no error is raised

### Requirement: Map release JSON to RawItem
The Collector SHALL map each qualifying GitHub release to a `RawItem` using: `repo` = the validated
`owner/repo`; `item_type` = `"release"`; `item_id` = the release `tag_name` (a stable,
human-readable per-repo identifier); `title` = the release `name`, falling back to `tag_name` when
`name` is null/empty; `body` = the release `body` (changelog markdown, empty string when null);
`url` = the release `html_url` (empty string when null); `created_at` = the raw ISO-8601
`published_at` string (used for the cutoff, never reformatted). A release JSON missing BOTH
`tag_name` and `id` SHALL be skipped rather than crashing.

> ACs: AC-V2-003-006 [CONFIRMED], AC-V2-003-007 [CONFIRMED], AC-V2-003-008 [CONFIRMED], AC-V2-003-009 [CONFIRMED], AC-V2-003-010 [CONFIRMED], AC-V2-003-011 [CONFIRMED]
> Business rules: BR-V2-003-001
> Integration: INT-V2-003-003

#### Scenario: item_id is the release tag_name (AC-V2-003-006) [CONFIRMED]
- **WHEN** a release with `tag_name = "v1.2.0"` is collected
- **THEN** the resulting `RawItem.item_id == "v1.2.0"` (so it renders as `#v1.2.0`, not an opaque numeric id)

#### Scenario: title falls back to tag_name when name is empty (AC-V2-003-007) [CONFIRMED]
- **WHEN** a release has `name = null` (or empty) and `tag_name = "v2.0.0"`
- **THEN** the resulting `RawItem.title == "v2.0.0"`

#### Scenario: Null body is coerced to empty string (AC-V2-003-008) [CONFIRMED]
- **WHEN** a release is returned with `body: null`
- **THEN** the resulting `RawItem.body` is an empty string and no error is raised

#### Scenario: Null html_url is coerced to empty string (AC-V2-003-009) [CONFIRMED]
- **WHEN** a release omits or nulls `html_url`
- **THEN** the resulting `RawItem.url` is an empty string and the item is still returned

#### Scenario: created_at is the raw published_at string (AC-V2-003-010) [CONFIRMED]
- **WHEN** a release has `published_at = "2026-07-01T09:00:00Z"`
- **THEN** the resulting `RawItem.created_at == "2026-07-01T09:00:00Z"` (unchanged, no reformatting)

#### Scenario: Release missing both tag_name and id is skipped (AC-V2-003-011) [CONFIRMED]
- **WHEN** a release JSON has neither a `tag_name` nor an `id` field
- **THEN** it is skipped (cannot be keyed) and the Collector continues without raising

### Requirement: Release pagination and cutoff reuse the collector's bounded machinery
The Collector SHALL page through releases by following the `Link` header `rel="next"` URL and SHALL
stop when either `max_items_per_repo` is reached OR a release falls before the lookback cutoff,
whichever comes first, using the same config-driven `max_items_per_repo` and `page_size` values as
issue collection (no new tunables, no hardcoded literals). When the `max_items_per_repo` cap is
reached the Collector SHALL emit an info-level truncation log. The GitHub `/releases` endpoint
returns releases newest-first; the per-item cutoff comparison uses `published_at`.

> ACs: AC-V2-003-012 [CONFIRMED], AC-V2-003-013 [CONFIRMED], AC-V2-003-014 [CONFIRMED]
> Business rules: BR-V2-003-003
> Integration: INT-V2-003-001

#### Scenario: Release fetch reuses config tunables, not hardcoded literals (AC-V2-003-012) [CONFIRMED]
- **WHEN** the Collector is constructed with `max_items_per_repo = 50` and `page_size = 25` and fetches releases
- **THEN** each release page request carries `per_page=25` and the result is capped at 50 — neither value is baked into the release fetch loop

#### Scenario: Early-stop at the cutoff mid-pagination (AC-V2-003-013) [CONFIRMED]
- **WHEN** releases arrive newest-first and a release with `published_at` before the cutoff is encountered
- **THEN** the Collector stops after detecting the first out-of-window release and requests no further pages

#### Scenario: Truncation note at the max-items cap (AC-V2-003-014) [CONFIRMED]
- **WHEN** a repo has more in-window releases than `max_items_per_repo`
- **THEN** exactly `max_items_per_repo` `RawItem`s are returned and an info-level log records the cap was reached for that repo

### Requirement: Release fetching reuses the existing security and error-isolation contract
The release-fetch path SHALL reuse, unchanged, the collector's existing cross-cutting behavior: it
SHALL authenticate with the operator's `GITHUB_TOKEN` via the same httpx client and SHALL NEVER
write the token value into logs, error messages, or returned data; it SHALL issue only `GET`
requests and SHALL NOT disable TLS verification; the `base_url` SHALL come only from config, never
from the `repo` argument or response data. It SHALL apply the same retry policy (backoff/retry on
`429`/`5xx` and on a `403` carrying `X-RateLimit-Remaining: 0`), isolate per-repo errors the same way
(`404`/`410` → warn and return empty for that repo; a non-rate-limit `401`/`403` → fail fast), and
touch neither the State Store nor the LLM.

> ACs: AC-V2-003-015 [CONFIRMED], AC-V2-003-016 [CONFIRMED], AC-V2-003-017 [CONFIRMED], AC-V2-003-018 [CONFIRMED]
> Business rules: BR-V2-003-005, BR-V2-003-003

#### Scenario: Token is sent but never leaked on the release path (AC-V2-003-015) [CONFIRMED]
- **WHEN** a release request is made or a release-path error is logged
- **THEN** the request carries the `Authorization` header but the `GITHUB_TOKEN` value never appears in any log line, exception message, or returned `RawItem`

#### Scenario: Rate limit on releases is retried with backoff (AC-V2-003-016) [CONFIRMED]
- **WHEN** the `/releases` request returns `429` (or `403` with `X-RateLimit-Remaining: 0`) then succeeds
- **THEN** the Collector backs off and retries using the same retry-policy object as issue collection, rather than failing immediately

#### Scenario: Missing repo skips releases; invalid token fails fast (AC-V2-003-017) [CONFIRMED]
- **WHEN** the `/releases` request returns `404`/`410` (repo gone) — or, separately, `401` with `X-RateLimit-Remaining` not `0`
- **THEN** the `404`/`410` case logs a warning and returns an empty release list for that repo (run continues), while the `401` case raises a clear error that stops the run without revealing the token

#### Scenario: Release fetch performs no state or LLM access (AC-V2-003-018) [CONFIRMED]
- **WHEN** `fetch_releases(repo, lookback_days)` runs
- **THEN** it neither reads/writes any State Store nor invokes any LLM client, and the `osspulse.ports.GitHubClient` Protocol is unchanged (`fetch_releases` is an adapter-only method)

### Requirement: Fetch newly-created discussions for a repo via GraphQL
The Collector SHALL fetch GitHub discussions whose `createdAt` falls within the last `lookback_days`
(UTC) for a single validated `owner/repo`, and return them as `RawItem` objects with
`item_type = "discussion"`. Because GitHub Discussions are unavailable via REST, the Collector SHALL
call the GraphQL API via a single `POST` to the `/graphql` endpoint derived from the configured
`base_url`, sending a fixed query for the repository's `discussions` ordered by `CREATED_AT DESC`
with `owner`, `name`, and a pagination cursor as the only variables. A discussion is included when its
`createdAt` is at or after the cutoff `now(UTC) - lookback_days` (Approach A — the same newly-created
rule as issues). A repo with no qualifying discussions SHALL return an empty list without raising.
This discussion path SHALL be exposed as an adapter method `fetch_discussions(repo, lookback_days)`
and SHALL NOT add a method to the frozen `osspulse.ports.GitHubClient` Protocol.

> ACs: AC-V2-006-001 [CONFIRMED], AC-V2-006-002 [CONFIRMED], AC-V2-006-004 [CONFIRMED], AC-V2-006-016 [CONFIRMED], AC-V2-006-018 [CONFIRMED]
> Business rules: BR-V2-006-001, BR-V2-006-002, BR-V2-006-003, BR-V2-006-006
> Integration: INT-V2-006-001

#### Scenario: Discussions within the lookback window are returned (AC-V2-006-001) [CONFIRMED]
- **WHEN** a repo has 2 discussions created 1 and 5 days ago and `lookback_days = 7`
- **THEN** both are returned as `RawItem`s with `item_type = "discussion"` and correctly mapped `repo`, `item_id`, `title`, `body`, `url`, `created_at`

#### Scenario: Discussions older than the cutoff are excluded (AC-V2-006-002) [CONFIRMED]
- **WHEN** a repo has one discussion created 2 days ago and one created 40 days ago and `lookback_days = 7`
- **THEN** only the 2-day-old discussion is returned

#### Scenario: Repo with Discussions enabled but none in the window returns empty (AC-V2-006-004) [CONFIRMED]
- **WHEN** a repo has Discussions enabled but no discussion created within `lookback_days`
- **THEN** an empty list is returned and no error is raised

#### Scenario: Query is a fixed non-mutating GraphQL query with only owner/name/cursor variables (AC-V2-006-016) [CONFIRMED]
- **WHEN** the Collector builds the GraphQL request for `repo = "owner/name"`
- **THEN** it sends a fixed, hardcoded query (a `query`, never a `mutation`) whose only variables are `owner`, `name`, and a pagination cursor — the query string is never constructed from the `repo` argument or any response data

#### Scenario: No state or LLM access; Protocol unchanged (AC-V2-006-018) [CONFIRMED]
- **WHEN** `fetch_discussions(repo, lookback_days)` runs
- **THEN** it neither reads/writes any State Store nor invokes any LLM client, and the `osspulse.ports.GitHubClient` Protocol is unchanged (`fetch_discussions` is an adapter-only method)

### Requirement: Map discussion GraphQL node to RawItem
The Collector SHALL map each qualifying GitHub discussion node to a `RawItem` using: `repo` = the
validated `owner/repo`; `item_type` = `"discussion"`; `item_id` = the discussion `number` as a string
(a stable, human-readable per-repo identifier, mirroring the issue mapping — so it renders as `#42`,
not an opaque GraphQL global node id); `title` = the discussion `title`; `body` = the discussion
`body` (markdown, empty string when null); `url` = the discussion `url` (empty string when null);
`created_at` = the raw ISO-8601 `createdAt` string (used for the cutoff, never reformatted). A
discussion node missing `number` SHALL be skipped rather than crashing.

> ACs: AC-V2-006-005 [CONFIRMED], AC-V2-006-006 [CONFIRMED], AC-V2-006-007 [CONFIRMED], AC-V2-006-008 [CONFIRMED], AC-V2-006-009 [CONFIRMED], AC-V2-006-010 [CONFIRMED]
> Business rules: BR-V2-006-001

#### Scenario: item_id is the stringified discussion number (AC-V2-006-005) [CONFIRMED]
- **WHEN** a discussion with `number = 42` is collected
- **THEN** the resulting `RawItem.item_id == "42"` (a string, not the GraphQL global node `id`)

#### Scenario: title is mapped from the discussion title (AC-V2-006-006) [CONFIRMED]
- **WHEN** a discussion has `title = "RFC: drop legacy API"`
- **THEN** the resulting `RawItem.title == "RFC: drop legacy API"`

#### Scenario: Null body is coerced to empty string (AC-V2-006-007) [CONFIRMED]
- **WHEN** a discussion is returned with `body: null`
- **THEN** the resulting `RawItem.body` is an empty string and no error is raised

#### Scenario: Null url is coerced to empty string (AC-V2-006-008) [CONFIRMED]
- **WHEN** a discussion omits or nulls `url`
- **THEN** the resulting `RawItem.url` is an empty string and the item is still returned

#### Scenario: created_at is the raw createdAt string (AC-V2-006-009) [CONFIRMED]
- **WHEN** a discussion has `createdAt = "2026-07-05T09:00:00Z"`
- **THEN** the resulting `RawItem.created_at == "2026-07-05T09:00:00Z"` (unchanged, no reformatting)

#### Scenario: Discussion missing number is skipped (AC-V2-006-010) [CONFIRMED]
- **WHEN** a discussion node has no `number` field
- **THEN** it is skipped (cannot be keyed) and the Collector continues without raising

### Requirement: Discussion cursor pagination and cutoff
The Collector SHALL page through discussions by following the GraphQL connection cursor
(`pageInfo.hasNextPage` / `pageInfo.endCursor`) rather than a REST `Link` header, requesting up to
`page_size` nodes per page, and SHALL stop when either `max_items_per_repo` is reached OR a discussion
falls before the lookback cutoff, whichever comes first — reusing the same config-driven
`max_items_per_repo` and `page_size` values as issue and release collection (no new tunables, no
hardcoded literals). Discussions are requested newest-first (`CREATED_AT DESC`); because both
inclusion and ordering key on `createdAt`, the per-item early-stop is exact with no ordering-vs-
inclusion skew. When the `max_items_per_repo` cap is reached the Collector SHALL emit an info-level
truncation log.

> ACs: AC-V2-006-011 [CONFIRMED], AC-V2-006-012 [CONFIRMED], AC-V2-006-013 [CONFIRMED]
> Business rules: BR-V2-006-002, BR-V2-006-003

#### Scenario: Discussion fetch reuses config tunables, not hardcoded literals (AC-V2-006-011) [CONFIRMED]
- **WHEN** the Collector is constructed with `max_items_per_repo = 50` and `page_size = 25` and fetches discussions
- **THEN** each GraphQL page requests at most 25 nodes and the result is capped at 50 — neither value is baked into the discussion fetch loop; the loop follows `pageInfo.hasNextPage`/`endCursor`

#### Scenario: Early-stop at the cutoff mid-pagination (AC-V2-006-012) [CONFIRMED]
- **WHEN** discussions arrive newest-first and a discussion with `createdAt` before the cutoff is encountered
- **THEN** the Collector stops after detecting the first out-of-window discussion and requests no further pages

#### Scenario: Truncation note at the max-items cap (AC-V2-006-013) [CONFIRMED]
- **WHEN** a repo has more in-window discussions than `max_items_per_repo`
- **THEN** exactly `max_items_per_repo` `RawItem`s are returned and an info-level log records the cap was reached for that repo

### Requirement: GraphQL error model — disabled Discussions and payload errors
The Collector SHALL classify the GraphQL **payload** (over and above the transport-level HTTP status):
a `200 OK` whose payload indicates the repository is not found or has Discussions disabled — i.e.
`data.repository` is `null`, or `data.repository.discussions` is `null`, accompanied by a top-level
`errors` entry — SHALL be treated as a skipped repo (logged at WARN, returning an empty list for that
repo so the run continues), the same user-visible outcome as a `404` on the REST paths. Any other
`200` response carrying a top-level `errors` array (e.g. a query/validation error or a
`RATE_LIMITED` GraphQL error type) SHALL surface a clear error rather than being silently returned as
an empty list.

> ACs: AC-V2-006-003 [CONFIRMED], AC-V2-006-014 [CONFIRMED]
> Business rules: BR-V2-006-007
> Integration: INT-V2-006-001

#### Scenario: Repo with Discussions disabled is skipped, run continues (AC-V2-006-003) [CONFIRMED]
- **WHEN** the GraphQL response is `200` with `data.repository.discussions == null` and a matching top-level `errors` entry (Discussions feature disabled, or repo not found)
- **THEN** a warning is logged, an empty list is returned for that repo, and no exception aborts the overall run

#### Scenario: Other GraphQL payload errors surface a clear error (AC-V2-006-014) [CONFIRMED]
- **WHEN** the GraphQL response is `200` but carries a top-level `errors` array that is NOT a disabled/not-found case (e.g. a malformed-query error or a `RATE_LIMITED` error type)
- **THEN** the Collector raises a clear error (it does not silently return an empty list)

### Requirement: Discussion GraphQL path reuses the security and transport error-isolation contract
The discussion-fetch path SHALL reuse, unchanged, the collector's existing cross-cutting behavior at
the transport level: it SHALL authenticate with the operator's `GITHUB_TOKEN` via the same httpx
client and SHALL NEVER write the token value into logs, error messages, or returned data; it SHALL
NOT disable TLS verification; the GraphQL endpoint URL SHALL derive only from the configured
`base_url`, never from the `repo` argument or response data. It SHALL apply the same retry policy
(backoff/retry on `429`/`5xx` and on a `403` carrying `X-RateLimit-Remaining: 0`) and isolate
transport auth failures the same way (a non-rate-limit `401`/`403` → fail fast because the shared
token affects every repo). The GraphQL request SHALL be a `POST` of a fixed non-mutating query only —
this is the sole exception to the REST paths' GET-only rule, and it SHALL touch neither the State
Store nor the LLM.

> ACs: AC-V2-006-015 [CONFIRMED], AC-V2-006-017 [CONFIRMED]
> Business rules: BR-V2-006-005, BR-V2-006-006, BR-V2-006-010

#### Scenario: Rate limit on the GraphQL POST is retried with backoff; auth fails fast (AC-V2-006-015) [CONFIRMED]
- **WHEN** the GraphQL `POST` returns `429` (or `403` with `X-RateLimit-Remaining: 0`) then succeeds — or, separately, returns `401` with `X-RateLimit-Remaining` not `0`
- **THEN** the rate-limit case backs off and retries using the same retry-policy object as issue/release collection, while the `401` case raises a clear error that stops the run without revealing the token

#### Scenario: Token is sent but never leaked on the discussion path (AC-V2-006-017) [CONFIRMED]
- **WHEN** a GraphQL discussion request is made or a discussion-path error is logged
- **THEN** the request carries the `Authorization` header and targets the `/graphql` endpoint derived from the configured `base_url`, TLS verification is on, and the `GITHUB_TOKEN` value never appears in any log line, exception message, or returned `RawItem`

### Requirement: The Collector accepts an injected ConditionalCache
The Collector SHALL accept an optional injected `ConditionalCache` (an `osspulse.ports` port) at
construction, defaulting to a no-op null cache. The Collector SHALL depend only on the
`ConditionalCache` **port**, `osspulse.models`, and its httpx client — it SHALL NOT import the
concrete `JsonFileETagStore` nor the State Store, preserving the pure-I/O boundary (living AC-2-015 /
BR-2-012). A Collector constructed with no cache (the null default) SHALL behave exactly as the
current V2 Collector — issuing unconditional requests — so this change is purely additive on a cache
miss. The frozen `osspulse.ports.GitHubClient` Protocol SHALL remain unchanged (the cache is a
constructor dependency, not a Protocol method).

> ACs: AC-V2-007-009 [CONFIRMED], AC-V2-007-018 [CONFIRMED]
> Business rules: BR-V2-007-007
> Integration: INT-V2-007-001

#### Scenario: A collector with the null cache behaves exactly as today (AC-V2-007-009) [CONFIRMED]
- **WHEN** `GitHubCollector` is constructed without a `ConditionalCache` and `fetch_items`/`fetch_releases` run
- **THEN** it issues unconditional requests (no `If-None-Match` header) and returns the same items as the current V2 collector — no behavior change on a cache miss

#### Scenario: The pure-I/O boundary and Protocol are unchanged (AC-V2-007-018) [CONFIRMED]
- **WHEN** the Collector performs a conditional fetch
- **THEN** it neither reads/writes any State Store nor invokes any LLM client, the `osspulse.ports.GitHubClient` Protocol is unchanged, and the `GITHUB_TOKEN` value never appears in any conditional-path log line, exception message, `etags.json`, or returned `RawItem`

### Requirement: The REST paths send a conditional first-page request when a validator is cached
The Collector SHALL send an `If-None-Match: <validator>` header on the **first page only** of a REST
endpoint (`fetch_items` → `issues`, `fetch_releases` → `releases`) whenever the injected cache returns
a validator for `"{repo}:{endpoint}"`. The validator SHALL
be echoed verbatim (both strong `"..."` and weak `W/"..."` forms), never parsed or normalized.
Subsequent pages (2..N) SHALL be requested unconditionally exactly as today. The conditional header
SHALL ride the existing `_request_with_retry` path so transport error handling
(`429`/`5xx`/secondary-rate-limit → retry; non-rate-limit `401`/`403` → fail fast) is unchanged.

> ACs: AC-V2-007-010 [CONFIRMED], AC-V2-007-013 [CONFIRMED], AC-V2-007-015 [CONFIRMED], AC-V2-007-016 [CONFIRMED]
> Business rules: BR-V2-007-004, BR-V2-007-011
> Integration: INT-V2-007-001

#### Scenario: If-None-Match is sent on the first page when cached (AC-V2-007-010) [CONFIRMED]
- **WHEN** the cache holds `'"etag-1"'` for `"owner/name:issues"` and `fetch_items` runs
- **THEN** the first-page GET carries the header `If-None-Match: "etag-1"`

#### Scenario: The conditional header is sent on the first page only (AC-V2-007-013) [CONFIRMED]
- **WHEN** a `200` first page has a `rel="next"` link and pagination continues to page 2
- **THEN** the page-2 (and later) requests carry NO `If-None-Match` header — only page 1 is conditional

#### Scenario: A weak ETag is echoed verbatim (AC-V2-007-015) [CONFIRMED]
- **WHEN** the cached validator is a weak ETag `W/"abc"`
- **THEN** the first-page request sends `If-None-Match: W/"abc"` unchanged — the value is never stripped, parsed, or normalized

#### Scenario: 304 is classified as a handled status, transport errors unchanged (AC-V2-007-016) [CONFIRMED]
- **WHEN** a conditional first-page request returns `304`, and separately when it returns `429`/`5xx`/`401`
- **THEN** `304` is treated as a handled (non-error) status the fetch method branches on, while `429`/`5xx` still retry with backoff and a non-rate-limit `401` still fails fast — the retry/`_classify` machinery is reused unchanged

### Requirement: A first-page 304 yields an empty delta for that endpoint
When a conditional first-page request returns `304 Not Modified`, the Collector SHALL return an empty
list for that endpoint and SHALL make no further page requests. This is sound because the endpoint is
fetched newest-first (`sort=created&direction=desc` for issues; `/releases` newest-first): any item
new within the window would appear on the first page and change its `ETag`, so a `304` proves nothing
new is present. A `304` SHALL NOT be treated as an error and SHALL NOT alter the stored validator.

> ACs: AC-V2-007-011 [CONFIRMED]
> Business rules: BR-V2-007-005
> Integration: INT-V2-007-001

#### Scenario: First-page 304 returns empty and stops paginating (AC-V2-007-011) [CONFIRMED]
- **WHEN** `fetch_items` sends a conditional first-page request and GitHub returns `304 Not Modified`
- **THEN** the method returns `[]` for that endpoint, requests no further pages, raises no error, and leaves the stored `ETag` for `"owner/name:issues"` unchanged

### Requirement: A first-page 200 records the fresh ETag and paginates normally
When a conditional (or unconditional) first-page request returns `200`, the Collector SHALL proceed
with the existing unconditional pagination and cutoff/early-stop logic unchanged, and SHALL record the
first-page response's `ETag` (when present) into the injected cache via `set()` under
`"{repo}:{endpoint}"`. A `200` whose response omits the `ETag` header SHALL record nothing for that
endpoint (or clear a stale entry) and SHALL NOT crash. Recording via `set()` SHALL be in-memory only —
the Collector SHALL NOT itself persist the cache to disk.

> ACs: AC-V2-007-012 [CONFIRMED], AC-V2-007-014 [CONFIRMED]
> Business rules: BR-V2-007-006, BR-V2-007-008
> Integration: INT-V2-007-001

#### Scenario: First-page 200 records the ETag and returns items as today (AC-V2-007-012) [CONFIRMED]
- **WHEN** the first page returns `200` with `ETag: "etag-2"` and 3 in-window issues
- **THEN** the Collector calls `set("owner/name:issues", '"etag-2"')` (in-memory), paginates and returns the issues exactly as the current collector, and the new items surface through the existing delta filter downstream

#### Scenario: A 200 with no ETag header records nothing and does not crash (AC-V2-007-014) [CONFIRMED]
- **WHEN** the first page returns `200` with no `ETag` header
- **THEN** the Collector records no validator for that endpoint (or clears any stale one), returns the fetched items normally, and raises no error

### Requirement: Discussions (GraphQL) are never conditionally cached
The Collector SHALL NOT apply any conditional caching to the Discussions path, because the GitHub
GraphQL API does not support `ETag`/`If-None-Match`. `fetch_discussions` SHALL remain unchanged —
issuing its GraphQL `POST` and never sending a conditional header nor reading/writing the
`ConditionalCache`.

> ACs: AC-V2-007-017 [CONFIRMED]
> Business rules: BR-V2-007-012

#### Scenario: fetch_discussions sends no conditional header (AC-V2-007-017) [CONFIRMED]
- **WHEN** `fetch_discussions` runs for a repo that has cached issue/release validators
- **THEN** the GraphQL `POST` carries no `If-None-Match` header and the Collector neither reads nor writes the `ConditionalCache` on the discussion path — the discussion behavior is identical to v2-006

