## ADDED Requirements

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
