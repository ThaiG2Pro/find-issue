## ADDED Requirements

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
