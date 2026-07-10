## ADDED Requirements

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
