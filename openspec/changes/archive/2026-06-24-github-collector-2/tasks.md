# Tasks — github-collector-2 (S2 GitHub Collector, V1 issues)

> Order follows `context/architecture.md` layering: config/data → errors → shared helper →
> adapter logic → tests. Tests come after the code they cover (R10). Checkpoints are human
> review gates — STOP and wait for the user.

## 1. Config & data types (tunables — no hardcoded literals)

- [x] 1.1 Define `RetryPolicy` frozen dataclass with locked defaults (`max_retries=3`, `backoff_base_seconds=1.0`, `backoff_multiplier=2.0`, `jitter_seconds=0.5`, `backoff_ceiling_seconds=60.0`).
  File: `src/osspulse/github/config.py`
  _Requirements: AC-2-026, AC-2-027_
- [x] 1.2 Define `CollectorConfig` frozen dataclass (`max_items_per_repo=100`, `page_size=100`, `base_url="https://api.github.com"`, `retry: RetryPolicy = RetryPolicy()`); all values overridable, defaults applied when omitted.
  File: `src/osspulse/github/config.py`
  _Requirements: AC-2-024, AC-2-025, AC-2-027, BR-2-013, BR-2-014_

## 2. Error hierarchy (token-safe)

- [x] 2.1 Define `CollectorError` base + `InvalidRepoError`, `AuthError`, `RateLimitError`, `NetworkError`; messages composed from status + repo + a static reason only — never the token, request, or response headers (ADR-004).
  File: `src/osspulse/github/errors.py`
  _Requirements: AC-2-008, AC-2-009, AC-2-014, AC-2-023_

## 3. Shared repo-validation pattern (ADR-006)

- [x] 3.1 Promote `_REPO_RE` in config to a public module-level `REPO_PATTERN` constant (keep existing behavior + `_validate_repos` working); single source of truth for `owner/name`.
  File: `src/osspulse/config.py`
  _Requirements: AC-2-014, BR-2-011_

## 4. Checkpoint — foundation review

- [x] 4.1 CHECKPOINT (human review): config dataclasses + error hierarchy + shared pattern. Verify defaults match BR-2-013/014, error messages are token-free, and `config.py` still passes its existing tests. STOP for user sign-off before building the adapter.
  File: `src/osspulse/github/`
  _Requirements: AC-2-024, AC-2-025, AC-2-026, AC-2-027, BR-2-013, BR-2-014_

## 5. Collector adapter — construction & helpers

- [x] 5.1 `GitHubCollector.__init__(token, config=CollectorConfig(), *, client=None, sleep=time.sleep)`: build `httpx.Client(base_url=config.base_url, headers={Authorization, Accept, X-GitHub-Api-Version}, verify=True)` (GET-only usage, TLS never disabled); accept an injected client/transport for tests; token set on the client at construction, not stored elsewhere.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-009, AC-2-013, AC-2-025_
- [x] 5.2 `_validate_repo(repo)`: reject any value not matching `REPO_PATTERN` with `InvalidRepoError` before any request.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-014, BR-2-011_
- [x] 5.3 `_classify(response) -> OK|RETRY|SKIP_REPO|FAIL_FAST`: 200→OK; 404/410→SKIP_REPO; 403+`X-RateLimit-Remaining:0`→RETRY; 429/5xx→RETRY; other 401/403→FAIL_FAST(AuthError); other 4xx→FAIL_FAST (ADR-003).
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-008, AC-2-011, AC-2-019, AC-2-020, AC-2-021_
- [x] 5.4 `_request_with_retry(url)`: only httpx caller; bounded loop to `retry.max_retries`; wait = `Retry-After` if present else `min(base*mult**attempt + uniform(0,jitter), ceiling)`, capped by ceiling; retries on RETRY class + `httpx.TransportError`; raises `RateLimitError`/`NetworkError` when exhausted; uses injected `sleep`.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-019, AC-2-020, AC-2-021, AC-2-022, AC-2-023, AC-2-026, BR-2-007, BR-2-014_
- [x] 5.5 `_next_link(link_header)`: parse `rel="next"` absolute URL; missing/malformed → `None`.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-007, BR-2-004_
- [x] 5.6 `_map_item(raw, repo) -> RawItem | None`: guard every field — `item_id=str(raw["number"])`, `title=raw.get("title") or ""`, `body=raw.get("body") or ""`, `url=raw.get("html_url") or ""`, `created_at` raw ISO; return `None` (skip) when a mandatory field (`number`/`created_at`) is missing; never reformat `created_at`.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-010, AC-2-012, AC-2-016, AC-2-017, BR-2-010_

## 6. Collector adapter — fetch loop

- [x] 6.1 `fetch_items(repo, lookback_days) -> list[RawItem]`: compute `cutoff = now(UTC) - lookback_days` (tz-aware); validate repo; request `state=all&sort=created&direction=desc&per_page=page_size`; paginate via `_next_link`; per-item: drop `pull_request` items (AC-2-018), per-item cutoff early-stop (AC-2-005, not page-level), map + collect; stop at `max_items_per_repo` with an info truncation log (AC-2-006); SKIP_REPO → return `[]` (AC-2-011); pure I/O — no StateStore/LLM access.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-2-001, AC-2-002, AC-2-003, AC-2-004, AC-2-005, AC-2-006, AC-2-011, AC-2-015, AC-2-018, AC-2-024, BR-2-001, BR-2-002, BR-2-003, BR-2-005, BR-2-009, BR-2-012_
- [x] 6.2 Export `GitHubCollector` (and config types) from the package.
  File: `src/osspulse/github/__init__.py`
  _Requirements: AC-2-015_

## 7. Tests (MockTransport — no real API, ADR-005)

- [x] 7.1 Window & mapping: in-window returned, old excluded, empty→`[]`, opened-then-closed kept; `item_id=str(number)`, `created_at` unchanged.
  File: `tests/test_github_client.py`
  _Requirements: AC-2-001, AC-2-002, AC-2-003, AC-2-004, AC-2-016, AC-2-017_
- [x] 7.2 Pagination: cutoff early-stop at a page-2 boundary; cap reached → exactly N items + info truncation log; missing/malformed `Link` → single page; `per_page`/`max_items` honor injected config (not hardcoded).
  File: `tests/test_github_client.py`
  _Requirements: AC-2-005, AC-2-006, AC-2-007, AC-2-018, AC-2-024_
- [x] 7.3 Security — token leak (T-I1): on success and on a 401 error, assert the token value is absent from `caplog`, the raised exception text, and every returned `RawItem`.
  File: `tests/test_github_client.py`
  _Requirements: AC-2-009_
- [x] 7.4 Dirty data (T-T1): null `body`→`""`; missing `user`/`html_url`→safe default, item still returned; missing mandatory field → item skipped, no crash.
  File: `tests/test_github_client.py`
  _Requirements: AC-2-010, AC-2-012_
- [x] 7.5 Auth & isolation: 404/410→warn+`[]`+run continues; 401/other-403→`AuthError` fail-fast (token not shown); `403 + X-RateLimit-Remaining:0`→backoff not auth failure.
  File: `tests/test_github_client.py`
  _Requirements: AC-2-008, AC-2-011, AC-2-020_
- [x] 7.6 Retry/backoff (config-driven): 429 honors `Retry-After`; 5xx retried then succeeds; exhausted retries→error (bounded, no infinite loop); transport timeout retried then `NetworkError`; injected `RetryPolicy(max_retries=5,...)` changes attempts without code edits; injected `sleep` asserted (no real wait).
  File: `tests/test_github_client.py`
  _Requirements: AC-2-019, AC-2-021, AC-2-022, AC-2-023, AC-2-026, AC-2-027_
- [x] 7.7 SSRF/TLS/scope: malformed `repo` (`../x`, `a/b/c`, `""`)→`InvalidRepoError` before any request; only GET issued; TLS verify never disabled; `base_url` from config, `repo` only fills the path (never host/scheme).
  File: `tests/test_github_client.py`
  _Requirements: AC-2-013, AC-2-014, AC-2-025_

## 8. Checkpoint — final gate

- [x] 8.1 CHECKPOINT (human review): run `pytest --cov=osspulse` (≥80% lines, ≥90% diff per `sdlc.config.json`) + `ruff check`; confirm all 27 ACs are exercised, the token-leak test passes, no hardcoded tunables remain in `client.py`, and the Collector touches neither StateStore nor LLM. STOP for user sign-off before S5 QA.
  File: `tests/test_github_client.py`
  _Requirements: AC-2-009, AC-2-015, AC-2-022, AC-2-024, AC-2-026, BR-2-013, BR-2-014_
