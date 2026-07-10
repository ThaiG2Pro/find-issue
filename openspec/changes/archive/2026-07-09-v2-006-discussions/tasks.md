# Tasks — v2-006-discussions (ticket V2-006)

> No HTTP API — no openapi.yaml (ADR-005). No DB/schema layer (JSON state store, item_type-agnostic).
> Work order follows the architecture layering: transport helper → mapping/classify helpers → adapter
> method → pipeline wiring → tests. No new module, no new port, no new error class, no
> renderer/state/config/delta change. rigor=lite · scope=standard · test_scope=module.

## 1. Transport generalization (foundational)

- [x] 1.1 Generalize `_request_with_retry(self, url, repo, *, json_body: dict | None = None)`: keep `self._client.get(url)` when `json_body is None` (every existing REST caller — issues, releases — unchanged, GET-only invariant preserved); issue `self._client.post(url, json=json_body)` when `json_body is not None`. The retry loop, `_classify`, `_backoff_seconds`, and static error messages are shared verbatim — no duplicated backoff logic (ADR-002).
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-015, AC-V2-006-016_

## 2. Discussion mapping + GraphQL payload classification (data layer)

- [x] 2.1 Add the module constant `_DISCUSSIONS_QUERY` — the fixed, non-mutating GraphQL query selecting `repository(owner,name).discussions(first,after,orderBy:{field:CREATED_AT,direction:DESC})` with `nodes { number title body url createdAt }` and `pageInfo { hasNextPage endCursor }`. Never built from untrusted input; only `owner`/`name`/`first`/`after` are variables (ADR-004).
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-016_
- [x] 2.2 Add `_map_discussion(self, node: dict, repo: str) -> RawItem | None`, mirroring `_map_release`. Map `item_type="discussion"`, `item_id=str(number)`, `title=title or ""`, `body=body or ""` (markdown `body`, not `bodyText` — ADR-004), `url=url or ""`, `created_at=createdAt` (raw ISO string, never reformatted). Return `None` when `number` is missing.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-005, AC-V2-006-006, AC-V2-006-007, AC-V2-006-008, AC-V2-006-009, AC-V2-006-010_
- [x] 2.3 Add `_classify_graphql(self, payload: dict, repo: str)` — shape-first ordered classification (ADR-003), the RISK-003 decision point: (1) `data.repository is None` OR `data.repository.discussions is None` → signal SKIP_REPO; (2) else non-empty top-level `errors` → raise (`RateLimitError` when a `RATE_LIMITED` error type is present, else `CollectorError` — static message, no token); (3) else return the `discussions` connection (`nodes` + `pageInfo`). The null-shape check MUST precede the errors-raise check. Do NOT hardcode an `errors[].type` string to detect disabled Discussions — key on the null connection shape.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-003, AC-V2-006-014_

## 3. Discussion fetch + cursor pagination (adapter method)

- [x] 3.1 Add `fetch_discussions(self, repo: str, lookback_days: int) -> list[RawItem]`, mirroring `fetch_releases`. Compute `cutoff = now(UTC) - lookback_days`; call `_validate_repo(repo)`; split `owner, name = repo.split("/", 1)`; build `url = f"{base_url}/graphql"`; loop calling `_request_with_retry(url, repo, json_body={"query": _DISCUSSIONS_QUERY, "variables": {...}})` then `_classify_graphql`. On SKIP_REPO → WARN + return `[]`.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-001, AC-V2-006-003, AC-V2-006-004, AC-V2-006-018_
- [x] 3.2 Implement the ADR-001 cursor loop body: per node, early-stop with `return items` when `_parse_created(createdAt) < cutoff` (created-desc order — inclusion and ordering share `createdAt`, no skew); call `_map_discussion` and append non-`None`; cap at `max_items_per_repo` with an info truncation log; advance via `pageInfo.endCursor` while `hasNextPage`, using `first = page_size` (config tunables, no literals); stop requesting pages after the cutoff or cap is hit.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-002, AC-V2-006-011, AC-V2-006-012, AC-V2-006-013_
- [x] 3.3 Confirm the discussion path reuses the existing security + retry contract with NO new machinery: same authed httpx client (token stays on headers, never in the query body or any log/error), TLS on, `base_url`-derived `/graphql` URL only (never from `repo`/response), same `RetryPolicy` object and `_classify` HTTP-status handling (429/5xx/secondary-rate-limit → retry; 401/non-rate-limit 403 → `AuthError` fail fast), same `CollectorError` hierarchy (no new error class); the `GitHubClient` Protocol in `ports.py` stays unchanged (adapter-only method); no state/LLM access.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-006-015, AC-V2-006-017, AC-V2-006-018_

## 4. CHECKPOINT — collector unit tests (mid-build human gate)

- [x] 4.1 Unit tests for `_map_discussion`: each field-mapping + null case — `item_id=str(number)`, `title`/`body`/`url` null→`""`, `body` maps the markdown field, `created_at=createdAt` unchanged, and skip (None) when `number` is missing.
  File: `tests/github/test_map_discussion.py`
  _Requirements: AC-V2-006-005, AC-V2-006-006, AC-V2-006-007, AC-V2-006-008, AC-V2-006-009, AC-V2-006-010_
- [x] 4.2 Unit tests for `fetch_discussions` using `httpx.MockTransport` + injected `sleep`: in-window returned; older-than-cutoff excluded; enabled-but-empty repo → `[]`; config tunables drive `first`/cap (not literals); cursor early-stop mid-pagination (multi-page mock); truncation info-log at `max_items_per_repo`; transport rate-limit retried then terminal; the request is a POST to `/graphql` carrying a `query` (never a `mutation`) with only owner/name/cursor variables; token value never appears in any log/error line.
  File: `tests/github/test_fetch_discussions.py`
  _Requirements: AC-V2-006-001, AC-V2-006-002, AC-V2-006-004, AC-V2-006-011, AC-V2-006-012, AC-V2-006-013, AC-V2-006-015, AC-V2-006-016, AC-V2-006-017_
- [x] 4.3 RISK-003 tests (ADR-003 — the 200-with-errors 3-way): (a) `data.repository.discussions == null` + a matching `errors` entry → WARN + `[]` (disabled/not-found skip, run continues); (b) `data.repository == null` → also skip; (c) a 200 with a non-disabled top-level `errors` array (malformed query, and separately a `RATE_LIMITED` type) → raises (not a silent `[]`). Assert the null-shape is detected FIRST and no `errors[].type` string is hardcoded.
  File: `tests/github/test_fetch_discussions.py`
  _Requirements: AC-V2-006-003, AC-V2-006-014_
- [x] 4.4 Regression test for ADR-002 (GET-only not regressed): assert an issue/release fetch still issues a `GET` with no body, while `fetch_discussions` issues exactly one `POST` per page — the shared `_request_with_retry` routes on `json_body`.
  File: `tests/github/test_fetch_discussions.py`
  _Requirements: AC-V2-006-016_
- [x] 4.5 **CHECKPOINT**: run `pytest tests/github/ -q` + coverage on `client.py` (≥80% lines). STOP for human review of the collector before wiring the pipeline. Confirm the ADR-003 classify order, ADR-002 GET-only-not-regressed, and the no-new-error-class / frozen-Protocol invariants hold.
  File: `tests/github/`
  _Requirements: AC-V2-006-003, AC-V2-006-014, AC-V2-006-016, AC-V2-006-018_

## 5. Pipeline wiring (orchestration)

- [x] 5.1 In `_collect_all`, inside the existing per-repo `try`, after the release inner-guard, add a second narrow inner `try/except` around `collector.fetch_discussions(repo_name, config.lookback_days)`: on `(InvalidRepoError, NetworkError)` → WARN + `discussions = []`; on other `CollectorError` → re-raise if `isinstance(exc, (AuthError, RateLimitError))` (fatal/terminal reach the outer arms), else WARN + `discussions = []`. Issues and releases already collected survive (AC-V2-006-022). Mirror the release guard exactly.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-006-022_
- [x] 5.2 Concatenate `items = issues + releases + discussions`, then keep the existing R1 sequence unchanged: `new, seen = _partition_new(items, state)` BEFORE `state.mark_seen(items)` (full list, never `new`); `all_items.extend(new if config.delta_enabled else items)`. Update the per-repo stats/log to count all three sources.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-006-019, AC-V2-006-020_

## 6. CHECKPOINT — pipeline tests + final gate

- [x] 6.1 Pipeline test: a repo returning 2 issues + 1 release + 3 discussions yields 6 `RawItem`s (2 `issue`, 1 `release`, 3 `discussion`) concatenated into one list before the delta step.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-006-019_
- [x] 6.2 Pipeline test: a discussion rendered+recorded on run 1 (`repo+"discussion"+number`) is suppressed on run 2 with `delta_enabled=true`; renders under the existing `### Discussion (N)` group with no renderer change.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-006-020, AC-V2-006-021_
- [x] 6.3 Pipeline isolation test (AC-022): a repo whose `fetch_discussions` raises a recoverable error while `fetch_items`/`fetch_releases` succeeded — assert the repo's issues and releases are still delivered, other repos unaffected, exit 0; and a count-invariant assertion that `mark_seen` is called exactly once per repo with `len(issues)+len(releases)+len(discussions)` items (R1 tripwire). Also assert an `AuthError` from `fetch_discussions` is fatal (not swallowed by the inner guard).
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-006-022, AC-V2-006-019_
- [x] 6.4 **CHECKPOINT (final)**: full `pytest -q` green, coverage ≥80% lines on `client.py` + `pipeline.py`, ruff lint clean on the touched modules, and a secret-scan confirming no token value in any log/error across the discussion (GraphQL) path. STOP for human sign-off before S4 exit.
  File: `tests/`
  _Requirements: AC-V2-006-015, AC-V2-006-017, AC-V2-006-019, AC-V2-006-020, AC-V2-006-021, AC-V2-006-022_
