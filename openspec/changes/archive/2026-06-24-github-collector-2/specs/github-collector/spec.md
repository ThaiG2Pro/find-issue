## ADDED Requirements

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

## Business Rules

- BR-2-001: A "newly-opened issue" is an issue whose `created_at` is within the last `lookback_days`, evaluated in UTC.
- BR-2-002: Issues are requested with `state=all` and `sort=created&direction=desc` (newest first).
- BR-2-003: Any item carrying a `pull_request` field is excluded (PRs are not collected in V1).
- BR-2-004: Pagination follows the `Link` header `rel="next"`; a missing/malformed `Link` header means no further pages.
- BR-2-005: The result for one repo is bounded by `max_items_per_repo` (config-driven, default 100) OR the lookback cutoff, whichever is hit first.
- BR-2-006: Every request authenticates with `GITHUB_TOKEN`; the token value is never logged, echoed in errors, or returned.
- BR-2-007: `4xx` is permanent (no blind retry); `5xx`/`429`/secondary-rate-limit (`403` + `X-RateLimit-Remaining: 0`) are retryable via the config-driven retry-policy object (default `max_retries`=3, exponential backoff with jitter and a ceiling), honoring `Retry-After`.
- BR-2-008: The Collector issues only `GET` requests and never disables TLS verification; the base URL is a config constant (default `https://api.github.com`), never built from untrusted input.
- BR-2-009: The lookback cutoff is `now(UTC) - lookback_days`.
- BR-2-010: All GitHub response fields are treated as untrusted; missing/null fields map to safe defaults (`body` → `""`).
- BR-2-011: A `repo` must match `^[\w.-]+/[\w.-]+$` or be rejected before any request.
- BR-2-012: The Collector never touches the State Store (S3) or the LLM (S4); it depends only on `osspulse.models`.
- BR-2-013: Every tunable (`max_items_per_repo`, `page_size`, `base_url`, and all retry-policy fields) is read from the Collector configuration object — no hardcoded literals in the fetch loop; defaults apply only when a value is omitted.
- BR-2-014: The retry policy is a single config object (`max_retries`, `backoff_base_seconds`, `backoff_multiplier`, `jitter_seconds`, `backoff_ceiling_seconds`) so it can be tuned at S3/S4 without editing the fetch loop.

## Integration Points

- INT-2-001: Collector implements `osspulse.ports.GitHubClient` Protocol (`fetch_items(repo, lookback_days) -> list[RawItem]`).
- INT-2-002: Collector → GitHub REST API `GET /repos/{owner}/{repo}/issues` (mocked in all tests).
- INT-2-003: Collector → `osspulse.models.RawItem` (output contract consumed by the pipeline / State Store, S3).

## Error / Outcome States

| Condition | Collector behavior | Rationale |
|-----------|--------------------|-----------|
| `200` with in-window issues | Return mapped `RawItem`s | Happy path |
| `200` with no in-window issues | Return `[]` | EC-001, not an error |
| `404` / `410` (one repo) | Warn + skip + return `[]` for that repo | BR-2-007, per-repo isolation |
| `401` / `403` (not rate limit) | Fail fast, clear error, token not shown | Affects all repos |
| `403` + `X-RateLimit-Remaining: 0` | Treat as rate-limit backoff | BR-2-007, secondary limit |
| `429` / `5xx` | Bounded backoff + retry; then surface error | BR-2-007 |
| Network / timeout | Bounded retry; then surface clear error | BR-2-007 |
| `pull_request` field present | Drop the item | BR-2-003 |
| `body: null` / missing field | Coerce to safe default | BR-2-010 |
| `repo` not `owner/name` | Raise before any request | BR-2-011 |

## Figma Design

Figma: N/A — CLI tool, no UI.

---

## _Structured Extract

### AC List
- AC-2-001: [CONFIRMED] Issues within the lookback window are returned as RawItems
- AC-2-002: [CONFIRMED] Issues older than the cutoff are excluded
- AC-2-003: [CONFIRMED] Repo with no in-window issues returns empty list (no error)
- AC-2-004: [CONFIRMED] Issue opened-then-closed inside window still collected (state=all)
- AC-2-005: [CONFIRMED] Pagination stops at the lookback cutoff mid-traversal
- AC-2-006: [CONFIRMED] Pagination stops at max_items_per_repo cap with an info truncation note
- AC-2-007: [CONFIRMED] Missing/malformed Link header → single-page result
- AC-2-008: [CONFIRMED] 401 invalid token fails fast without leaking the token
- AC-2-009: [CONFIRMED] Token sent via Authorization header but never leaked to logs/errors/output
- AC-2-010: [CONFIRMED] Null body coerced to empty string
- AC-2-011: [CONFIRMED] 404/410 repo skipped with warning, run continues
- AC-2-012: [CONFIRMED] Missing optional field does not crash (safe default)
- AC-2-013: [CONFIRMED] Only GET requests; TLS verification never disabled
- AC-2-014: [CONFIRMED] Malformed repo rejected before any request
- AC-2-015: [CONFIRMED] Pure I/O — no State Store / LLM access
- AC-2-016: [CONFIRMED] item_id is the stringified issue number
- AC-2-017: [CONFIRMED] created_at preserved as raw ISO string
- AC-2-018: [CONFIRMED] Pull requests dropped
- AC-2-019: [CONFIRMED] Backoff + retry on 429 honoring Retry-After
- AC-2-020: [CONFIRMED] 403 + X-RateLimit-Remaining 0 treated as backoff, not auth failure
- AC-2-021: [CONFIRMED] Backoff + retry on 5xx then succeed
- AC-2-022: [CONFIRMED] Retries bounded by config max_retries (default 3) then error surfaces
- AC-2-023: [CONFIRMED] Network/timeout retried (bounded by retry policy) then surfaced
- AC-2-024: [CONFIRMED] max_items_per_repo and page_size are config-driven, not hardcoded
- AC-2-025: [CONFIRMED] Base URL is a config constant, never derived from untrusted input
- AC-2-026: [CONFIRMED] Retry policy values are read from config, not hardcoded
- AC-2-027: [CONFIRMED] Config defaults apply when omitted; explicit values override without code change

### Business Rules
- BR-2-001: Newly-opened = created_at within lookback_days (UTC)
- BR-2-002: state=all, sort=created&direction=desc
- BR-2-003: Exclude items with a pull_request field
- BR-2-004: Follow Link rel=next; missing/malformed = no more pages
- BR-2-005: Bounded by max_items_per_repo (config, default 100) OR cutoff
- BR-2-006: GITHUB_TOKEN never logged/echoed/returned
- BR-2-007: 4xx permanent; 5xx/429/secondary-limit retryable via config retry-policy object (default max_retries 3, exp backoff + jitter + ceiling, Retry-After)
- BR-2-008: GET-only, TLS verify never disabled, base URL is a config constant (default https://api.github.com)
- BR-2-009: Lookback cutoff = now(UTC) - lookback_days
- BR-2-010: Untrusted data; missing/null → safe defaults (body → "")
- BR-2-011: repo must match ^[\w.-]+/[\w.-]+$ or be rejected pre-request
- BR-2-012: No State Store (S3) / LLM (S4) access
- BR-2-013: Every tunable (max_items_per_repo, page_size, base_url, retry fields) is config-driven — no hardcoded literals in the fetch loop
- BR-2-014: Retry policy is a single config object (max_retries, backoff_base_seconds, backoff_multiplier, jitter_seconds, backoff_ceiling_seconds) tunable without editing the fetch loop

### Integration Points
- INT-2-001: implements ports.GitHubClient
- INT-2-002: GitHub REST GET /repos/{owner}/{repo}/issues (mocked)
- INT-2-003: outputs models.RawItem to pipeline/State Store

### Risk Flags
- RISK-001: Token leakage (T-I1) — HIGH — AC-2-009
- RISK-002: Untrusted/dirty response data (T-T1) — HIGH — AC-2-010, AC-2-012
- RISK-003: Rate-limit DoS / unbounded pagination (T-D1) — HIGH — AC-2-005, AC-2-006, AC-2-019, AC-2-020, AC-2-021, AC-2-022, AC-2-024, AC-2-026
- RISK-004: SSRF-shaped repo string (T-T2) — MEDIUM — AC-2-014
- RISK-005: TLS / minimum scope (T-S1/T-E1) — MEDIUM — AC-2-013

### Metadata
ticket_id: 2
domain: github-integration
has_figma: false
has_cms_ui: false
actors: [operator]
ac_count: 27
ac_confirmed: 27
ac_assumed: 0
ac_missing: 0
ac_unclear: 0
br_count: 14
int_count: 3
