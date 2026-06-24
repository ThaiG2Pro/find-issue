## Why

OSS Pulse's V1 pipeline can load a watchlist (S1 done) but has no way to actually
fetch anything from GitHub — the `GitHubClient` port is still a bare Protocol stub. The
GitHub Collector (S2) is the first real-API integration: it turns a validated `org/repo`
plus a lookback window into a list of newly-opened issues, under GitHub's real
constraints (authentication, pagination, rate limits, dirty response data). Without it,
nothing downstream (summarizer, renderer, delivery) has data to work on. This is the
Week-1 milestone in PROJECT_SPEC §9 and the core "real API integration under constraints"
portfolio signal.

## What Changes

- Add a concrete `httpx`-based GitHub REST client implementing the existing
  `osspulse.ports.GitHubClient` Protocol (`fetch_items(repo, lookback_days) -> list[RawItem]`).
- Fetch **newly-opened issues** (`created_at` within `lookback_days`) for one repo via
  `GET /repos/{owner}/{repo}/issues`, mapping each to a `RawItem` (`item_type="issue"`).
- **Exclude pull requests** — items carrying a `pull_request` field are dropped (GitHub's
  issues endpoint returns PRs too).
- **Paginate** via the `Link` header `rel=next`, stopping at a configurable
  `max_items_per_repo` cap (default 100) or when an item's `created_at` falls before the
  lookback cutoff (results are created-desc), whichever comes first.
- **Authenticate** with the operator's `GITHUB_TOKEN` (already loaded by S1 config) for the
  5000 req/hr limit; the token is never logged or echoed.
- **Rate-limit handling**: honor `X-RateLimit-Remaining` / `X-RateLimit-Reset`; on `429` or
  `5xx`, back off and retry (respecting `Retry-After`); on `4xx` permanent errors, do not
  blindly retry.
- **Per-repo error isolation**: a `404`/`410` for one repo logs a warning and is skipped so
  the run continues across the watchlist; a `401`/`403` auth failure fails fast (it affects
  every repo).
- The Collector is **pure I/O**: it returns `list[RawItem]` and never reads or writes the
  State Store — delta/seen-tracking is orchestrated by the pipeline (V1 records, V2 filters).
- Tests mock all GitHub HTTP — no test hits the real API.

## Capabilities

### New Capabilities
- `github-collector`: fetch newly-opened GitHub issues for a single repo within a lookback
  window, with authentication, pagination, rate-limit handling, dirty-data tolerance, and
  per-repo error isolation, returning `RawItem`s. (V1 = issues; discussions/releases are V2,
  out of scope here.)

### Modified Capabilities
- _None._ This adds a new capability and only **consumes** existing exports from
  `project-foundation` (`osspulse.models`, `osspulse.ports.GitHubClient`); it does not change
  any locked requirement of that capability.

## Impact

- **Code**: new adapter under `src/osspulse/github/` (e.g. `client.py`); new tests under
  `tests/` (mocked httpx). No change to `models.py`/`ports.py` (contract already exists).
- **Dependencies**: `httpx` (already declared in the stack) becomes actually used.
- **Config**: introduces config-driven tunables on the Collector — `max_items_per_repo`
  (default 100), `page_size` (default 100), `base_url` (default `https://api.github.com`),
  and a `retry_policy` object (`max_retries` 3, `backoff_base_seconds` 1.0,
  `backoff_multiplier` 2.0, `jitter_seconds` 0.5, `backoff_ceiling_seconds` 60.0). All have
  defaults, none are hardcoded in the fetch loop; does not change the required config
  contract from S1.
- **Boundary**: must NOT call S4 (LLM) and must NOT touch S3 (State Store) — pure GitHub I/O.
- **Secrets**: consumes `GITHUB_TOKEN` from env (never from files, never logged).

---

## Assumptions

- `[CONFIRMED]` "New issue" = issue whose `created_at` is within the last `lookback_days`;
  pagination early-stops once items fall before the cutoff. (Clarification Q1 → A)
- `[CONFIRMED]` Pull requests are excluded — any item with a `pull_request` field is dropped.
  (Clarification Q2 → A)
- `[CONFIRMED]` Pagination is bounded by `max_items_per_repo` (default 100) OR the lookback
  cutoff, whichever comes first. (Clarification Q3 → A)
- `[CONFIRMED]` The Collector is pure I/O — it does not read/write the State Store; the
  pipeline owns record/delta. (Clarification Q4 → A)
- `[CONFIRMED]` Per-repo `404`/`410` → warn + skip + continue; `401`/`403` auth failure →
  fail fast (affects all repos). (Clarification Q5 → A)
- `[CONFIRMED]` GitHub issues are fetched with `state=all` (open + closed) and ordered
  `sort=created&direction=desc`, so created-desc ordering enables early-stop. (an issue
  opened then closed inside the window is still "new" — locked at S2.)
- `[CONFIRMED]` `RawItem` mapping: `item_id` = stringified issue `number`; `body` defaults to
  empty string when GitHub returns `null`; `created_at` kept as the raw ISO-8601 string (no
  reformatting). (locked against `models.RawItem` shape, foundation export.)
- `[CONFIRMED]` Default page size = 100 (GitHub max) to minimize request count — exposed as
  the config-driven `page_size` (not a hardcoded literal). (rate-limit efficiency.)
- `[CONFIRMED]` Retry policy is a single config object: `max_retries`=3,
  `backoff_base_seconds`=1.0, `backoff_multiplier`=2.0, `jitter_seconds`=0.5,
  `backoff_ceiling_seconds`=60.0, honoring `Retry-After`, on `429`/`5xx`/secondary-limit.
  All values config-driven and tunable at S3/S4 without touching the fetch loop. (locked at
  S2 per the SPEC LOCK NO-GO — no hardcoded retry constants.)
- `[CONFIRMED]` Every tunable (`max_items_per_repo`=100, `page_size`=100,
  `base_url`=`https://api.github.com`, and the retry-policy fields) is read from the
  Collector config object; `base_url` is GET-only and never built from untrusted input.
- `[CONFIRMED]` Timezone: the lookback cutoff is computed in UTC to match GitHub's ISO-8601
  `Z` timestamps. (avoids off-by-hours drift.)

## Out of Scope (Non-Goals)

- ❌ Discussions (GraphQL) and Releases — those are V2 (PROJECT_SPEC §5).
- ❌ Pull requests as a collected item type — explicitly excluded for V1.
- ❌ Delta filtering / "only new since last run" — the Collector returns all in-window items;
  delta is V2 and lives in the pipeline + State Store, not here.
- ❌ Writing or reading the State Store from the Collector (pure I/O boundary).
- ❌ Calling the LLM / summarizing — that is S4; the hard boundary forbids S2↔S4 coupling.
- ❌ Scanning beyond the watchlist or using GitHub Search API (watchlist-only principle).
- ❌ Caching GitHub responses (Redis cache is for LLM summaries, S4).
- ❌ Concurrency/parallel repo fetching — V1 is sequential; parallelism is a later optimization.

## Edge Cases

### Input Boundary
- EC-001: Repo has **zero** issues opened in the window → return `[]` (not an error).
- EC-002: `lookback_days` very large (e.g. 365) → fetch normally, but the `max_items_per_repo`
  cap still bounds the result; early-stop on cutoff still applies.
- EC-003: Invalid `repo` string reaching the Collector (`../x`, `a/b/c`, empty) → reject
  before issuing any request (defense-in-depth over S1 validation).

### State Transition
- EC-004: Issue **opened then closed** inside the window → still collected (`state=all`).
- EC-005: First page already contains items older than the cutoff → stop after that page; do
  not follow `rel=next`.

### Concurrency
- EC-006: A new issue is opened *during* pagination (shifts page boundaries) → acceptable
  drift; created-desc + cutoff means at worst one duplicate/missed boundary item; idempotency
  downstream (State Store) absorbs it. No locking.

### Data Integrity
- EC-007: Issue JSON has `body: null` → map to empty string, do not crash.
- EC-008: Issue JSON missing an expected field (`user`, `html_url`) → guard with safe
  defaults; never assume shape (data is untrusted).
- EC-009: Item carries a `pull_request` field → skip it (PR, not an issue).

### Permission / Auth
- EC-010: `GITHUB_TOKEN` missing/empty → already fails fast at S1 config load (not reached
  here); if a request returns `401`, fail fast with a clear message, token value never shown.
- EC-011: `403` with `X-RateLimit-Remaining: 0` (secondary rate limit) → treat as rate-limit
  backoff, not a permanent auth error.

### Integration Failure
- EC-012: Single repo returns `404`/`410` (renamed/deleted/private) → log warning, skip, keep
  processing the rest of the watchlist.
- EC-013: `5xx` / `429` transient error → back off and retry (bounded); if still failing after
  max retries, surface the error.
- EC-014: Network timeout / connection error → bounded retry; then surface a clear error.
- EC-015: `Link` header malformed or absent → treat as no next page (single-page result).

### UI/UX
- EC-016: Result hits the `max_items_per_repo` cap → log an info note that the cap was reached
  (so the operator knows the digest is truncated for that repo).

## Early Risk Flags

(Folded from `stride-threat-model.md` — gate **PASS**, 0 Critical.)

- 🟠 **High — Token leakage (T-I1)**: `GITHUB_TOKEN` must never appear in logs, error
  messages, or the digest. Drives AC-2-009. Cross-check `security.md`.
- 🟠 **High — Untrusted response data (T-T1)**: GitHub JSON is dirty; guard every field
  access. Drives AC-2-010/011.
- 🟠 **High — Rate-limit DoS (T-D1)**: unbounded pagination burns the 5000/hr budget; capped +
  backoff required. Drives AC-2-005/006/007.
- 🟡 **Medium — SSRF-shaped repo string (T-T2)**: `repo` builds the request path; validate
  strict `owner/name` in the Collector too. Drives AC-2-012.
- 🟡 **Medium — TLS / minimum scope (T-S1/T-E1)**: never disable TLS verify; GET-only,
  read-only token. Drives AC-2-013.

Figma: N/A — CLI tool, no UI.
