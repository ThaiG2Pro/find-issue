# Tasks — v2-cache-etag (ticket V2-007)

> CR: add GitHub HTTP ETag conditional-request caching to the REST collector paths to save rate-limit
> budget. No HTTP API (no openapi.yaml). New capability `conditional-cache` = one port + one JSON-file
> adapter (sibling of the State Store); collector gains an injected optional cache; pipeline builds +
> injects it best-effort and commits post-`mark_seen`. GraphQL/discussions untouched.
> rigor=lite · scope=standard · test_scope=module · testcase_export=none.

## 1. ConditionalCache port + JSON-file adapter (data layer, foundational)

- [x] 1.1 Add the `ConditionalCache` Protocol to `ports.py`: `get(key: str) -> str | None`, `set(key: str, validator: str) -> None`, `commit() -> None`. Do NOT touch the frozen `GitHubClient` Protocol.
  File: `src/osspulse/ports.py`
  _Requirements: AC-V2-007-001_
- [x] 1.2 Create `JsonFileETagStore` in a new module: in-memory dict keyed `"{repo}:{endpoint}"`; lazy best-effort `load()` (missing/empty/whitespace/corrupt/unreadable → empty dict + WARN, NEVER raise — the deliberate opposite of `JsonFileStateStore`); `get`/`set` operate on the in-memory dict; `commit()` writes atomically via `tempfile.mkstemp(dir=path.parent)` → `fsync` → `os.replace` (mirror `json_store.save`). Store only keys + validator strings — never the token or bodies. Imports: stdlib + `osspulse.ports` only; NEVER import `state.json_store`.
  File: `src/osspulse/cache/etag_store.py`
  _Requirements: AC-V2-007-002, AC-V2-007-003, AC-V2-007-004, AC-V2-007-005, AC-V2-007-006, AC-V2-007-008_
- [x] 1.3 Add a `_NullConditionalCache` no-op (`get`→`None`, `set`/`commit`→no-op) satisfying the port, for the disabled/unavailable path so callers need no null checks.
  File: `src/osspulse/cache/etag_store.py`
  _Requirements: AC-V2-007-007_

## 2. CHECKPOINT — ETag store unit tests (mid-build gate)

- [x] 2.1 Unit tests for `JsonFileETagStore`: `set`→`commit`→fresh-instance `get` round-trip per repo+endpoint; miss returns `None`; `set` without `commit` is NOT durable (in-memory only); missing file → empty; corrupt/whitespace/unreadable file → empty + WARN (no raise); `commit` uses a temp file + `os.replace` in the same dir (torn-read safety); the persisted file contains only keys+validators (assert token sentinel absent); the store never opens `state.json`. Plus a `_NullConditionalCache` no-op test.
  File: `tests/cache/test_etag_store.py`
  _Requirements: AC-V2-007-002, AC-V2-007-003, AC-V2-007-004, AC-V2-007-005, AC-V2-007-006, AC-V2-007-007, AC-V2-007-008_
- [x] 2.2 **CHECKPOINT**: run `pytest tests/cache/test_etag_store.py -q` + coverage on `etag_store.py` (≥80% lines). STOP for human review of the best-effort/atomic-write invariants and the "never touches state.json" boundary before wiring the collector.
  File: `tests/cache/`
  _Requirements: AC-V2-007-004, AC-V2-007-005, AC-V2-007-008_

## 3. Collector conditional-request support (adapter, additive)

- [x] 3.1 Add an injected `conditional_cache: ConditionalCache | None = None` constructor arg to `GitHubCollector`, defaulting internally to `_NullConditionalCache()` so a collector built without one behaves exactly as today. Depend on the port only — do NOT import `JsonFileETagStore` or the State Store; keep the `GitHubClient` Protocol unchanged.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-007-009, AC-V2-007-018_
- [x] 3.2 Extend `_request_with_retry(..., *, extra_headers: dict | None = None)` so the conditional header rides the SAME single retry loop / `_classify` / backoff path (no duplicated logic); pass `headers=extra_headers` to the `get` call when present. Map `304` in `_classify` to the OK action so the caller can branch on `response.status_code == 304` (transport `429`/`5xx`/auth handling unchanged).
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-007-013, AC-V2-007-016_
- [x] 3.3 In `fetch_items` (endpoint `issues`) and `fetch_releases` (endpoint `releases`): on the FIRST page only, if `conditional_cache.get(f"{repo}:{endpoint}")` returns a validator, send `If-None-Match: <validator>` (echo verbatim — strong or weak `W/"..."`). On first-page `304` → return `[]` and request no further pages. On first-page `200` → `set(f"{repo}:{endpoint}", etag)` when the `ETag` header is present (record nothing / no crash when absent), then paginate unconditionally exactly as today (pages 2..N carry no conditional header). Never persist here — `set` is in-memory.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-007-010, AC-V2-007-011, AC-V2-007-012, AC-V2-007-013, AC-V2-007-014, AC-V2-007-015_
- [x] 3.4 Confirm `fetch_discussions` is untouched — no conditional header on the GraphQL POST, no `ConditionalCache` read/write on the discussion path.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-007-017_

## 4. CHECKPOINT — collector unit tests (mid-build gate)

- [x] 4.1 Unit tests with `httpx.MockTransport` + a fake `ConditionalCache`: null-cache collector issues unconditional requests + returns same items as today (regression); with a cached validator the first-page GET carries `If-None-Match: <etag>` (strong AND weak `W/"..."` verbatim); a first-page `304` → `[]` + no page-2 request + stored ETag unchanged; a first-page `200` → `set(...)` called with the fresh ETag + normal pagination + page-2 request carries NO `If-None-Match`; a `200` with no `ETag` header → no `set`/no crash; `429`/`5xx` on the conditional request still retry, `401` still fails fast; token sentinel never in any log/error; `fetch_discussions` sends no conditional header.
  File: `tests/github/test_conditional_requests.py`
  _Requirements: AC-V2-007-009, AC-V2-007-010, AC-V2-007-011, AC-V2-007-012, AC-V2-007-013, AC-V2-007-014, AC-V2-007-015, AC-V2-007-016, AC-V2-007-017, AC-V2-007-018_
- [x] 4.2 **CHECKPOINT**: run `pytest tests/github/ -q` + coverage on `client.py` (≥80% lines). STOP for human review that the conditional path reuses `_request_with_retry` (no duplicated backoff), the newest-first-first-page-only invariant holds, and the null-default preserves today's behavior.
  File: `tests/github/`
  _Requirements: AC-V2-007-010, AC-V2-007-011, AC-V2-007-013, AC-V2-007-018_

## 5. Config + pipeline wiring (orchestration)

- [x] 5.1 Parse the optional `[etag_cache]` section in `config.py`: `enabled` (bool, default `true`; non-boolean → `ConfigError` at load, mirror the `[delta]` bool-trap guard) and `path` (str, default `./.osspulse/etags.json`). Add `etag_cache_enabled: bool = True` and `etag_cache_path: str = "./.osspulse/etags.json"` to the `Config` dataclass.
  File: `src/osspulse/config.py`
  _Requirements: AC-V2-007-020, AC-V2-007-021_
- [x] 5.2 Add `_build_etag_cache(config)` in `pipeline.py` mirroring `_build_cache`: when `config.etag_cache_enabled AND config.delta_enabled` → construct `JsonFileETagStore(config.etag_cache_path)` (best-effort — any error → `_NullConditionalCache`); otherwise → `_NullConditionalCache` (and never send conditional headers / never write the file). Inject the result into `GitHubCollector`.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-007-019, AC-V2-007-022, AC-V2-007-023_
- [x] 5.3 In `run_pipeline`, after the `_collect_all` loop returns (every collected repo already `mark_seen`-recorded inside the loop), call `conditional_cache.commit()` exactly once. Ensure a fatal `AuthError`/`StateError` propagates out BEFORE the commit line so an aborted run leaves `etags.json` unchanged (the crash-safety invariant). Do NOT commit per-repo.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-007-024, AC-V2-007-025_

## 6. CHECKPOINT — pipeline/config tests + final gate

- [x] 6.1 Config tests: absent `[etag_cache]` → `etag_cache_enabled=True` + default path; `enabled="yes"` → `ConfigError` before the pipeline runs.
  File: `tests/test_config.py`
  _Requirements: AC-V2-007-020, AC-V2-007-021_
- [x] 6.2 Pipeline tests: `commit()` invoked exactly once after the loop (spy the injected cache); both flags true → conditional header sent; either flag false → no conditional header + `etags.json` never written; a fatal `AuthError` mid-loop → `commit()` NOT called and `etags.json` unchanged (crash-safety); best-effort build → a `JsonFileETagStore` ctor failure yields a null cache and the run still completes.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-007-019, AC-V2-007-022, AC-V2-007-023, AC-V2-007-024, AC-V2-007-025_
- [x] 6.3 End-to-end tests (mocked transport): run1 `200` records+commits ETags and renders items; run2 with no new activity → every REST first page `304` → "no new items" doc delivered, exit 0, only `304`-answered conditional requests issued; run2 with a new issue → issues `200` (changed ETag) → only the new item rendered via delta, fresh ETag committed; a corrupt `etags.json` at start → WARN + unconditional fetch + normal delivery + exit 0.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-007-026, AC-V2-007-027, AC-V2-007-028_
- [x] 6.4 **CHECKPOINT (final)**: full `pytest -q` green, coverage ≥80% lines on `etag_store.py` + `client.py` + `pipeline.py`, ruff lint clean on the touched modules, and a secret-scan confirming no token value in `etags.json`, any log, or any error across the conditional path. STOP for human sign-off before S4 exit.
  File: `tests/`
  _Requirements: AC-V2-007-006, AC-V2-007-018, AC-V2-007-024, AC-V2-007-025, AC-V2-007-026_
