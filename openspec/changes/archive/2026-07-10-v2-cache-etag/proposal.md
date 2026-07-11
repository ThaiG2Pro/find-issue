## Why

`osspulse run` currently calls the GitHub REST API on **every** run with **unconditional** requests —
it never sends `If-None-Match`/`If-Modified-Since`, so GitHub re-serves every issue and release page
in full and charges each response against the 5000-req/hr rate limit, even when nothing changed since
the last run. GitHub returns an `ETag` (and `Last-Modified`) on every REST response, and a
**`304 Not Modified`** reply to a conditional request **does not count against the rate limit**
(PROJECT_SPEC §5 V2: "Caching để tiết kiệm cả GitHub request lẫn token LLM"). For the common case —
a scheduled run over a watchlist where most repos had no new issues/releases in the window — sending
conditional requests turns almost every collection into a free `304`, and a `304` on the newest-first
first page is a provably-correct signal that there is **nothing new** for that endpoint (an empty
delta). This is the GitHub-request half of the V2 caching goal (the LLM/token half is already served
by the Redis summary cache).

## What Changes

- **New capability `conditional-cache`** — a small persistence component that records, between runs,
  the last-seen HTTP validator (`ETag`) per **repo + REST endpoint**:
  - A `ConditionalCache` **port** (`osspulse.ports`): `get(key) -> str | None`, `set(key, validator)`
    (in-memory), and `commit()` (durable, best-effort flush).
  - A `JsonFileETagStore` adapter persisting to a **separate `etags.json`** file (default
    `./.osspulse/etags.json`, alongside `state.json`), using the same atomic temp-write→`os.replace`
    discipline as the State Store.
  - Key format `"{repo}:{endpoint}"` (e.g. `"owner/name:issues"`, `"owner/name:releases"`).
  - **Best-effort semantics** (unlike the State Store): a missing/corrupt/unreadable `etags.json`
    degrades to an empty cache with a WARN and the run continues with unconditional fetches — it is a
    pure rate-limit optimization, so losing it never affects correctness (contrast: a corrupt
    `state.json` is fatal because it drives idempotency/delta).
- **Modify the GitHub Collector (`github-collector`)** — teach the REST paths (`fetch_items`,
  `fetch_releases`) to make **conditional** requests, without touching the pure-I/O boundary:
  - The collector gains an **injected** optional `ConditionalCache` (constructor arg, defaulting to a
    no-op null cache — so a collector built without one behaves exactly as today). It depends only on
    the **port** + `osspulse.models` + httpx; it never imports the concrete adapter or the State Store
    (AC-2-015 preserved).
  - On the **first page** of an endpoint, if a validator is cached for `"{repo}:{endpoint}"`, send
    `If-None-Match: <etag>`.
  - A **`304 Not Modified`** first-page response → return an **empty list** for that endpoint (empty
    delta) and make no further page requests. Correct because issues/releases are fetched
    newest-first (`sort=created&direction=desc`); any new item would appear at the top and change the
    first page's `ETag`, so a `304` means nothing new is in the window.
  - A **`200`** response → proceed with the existing unconditional pagination unchanged, and record
    the fresh first-page `ETag` into the cache via `set()` (in-memory only — see crash-safety below).
  - `_request_with_retry` gains an optional `extra_headers` so the conditional header rides the same
    single retry/`_classify` path; `_classify` maps `304` to the OK class so the fetch method can
    branch on `response.status_code == 304`.
  - **GraphQL / discussions are never conditional** — the GraphQL API does not support `ETag`;
    `fetch_discussions` is unchanged.
- **Wire it into the pipeline (`scheduler-cli`)**:
  - `run_pipeline` builds the `JsonFileETagStore` best-effort (null cache on any failure, mirroring
    `_build_cache` for Redis) and injects it into `GitHubCollector`.
  - **Crash-safety commit ordering (correctness-critical):** the collector's `set()` only mutates the
    in-memory cache; the pipeline calls `conditional_cache.commit()` **once, after the per-repo
    collection loop** — i.e. after every collected repo's items have been durably recorded by
    `mark_seen`. A run that aborts before that point (fatal `AuthError`/`StateError`) leaves
    `etags.json` **unchanged**, so the next run re-fetches and no item is ever skipped before it was
    recorded seen.
  - **Delta interaction:** conditional requests are gated by BOTH a new `etag_cache_enabled` config
    flag (default `true`) AND the existing `delta_enabled`. When `delta_enabled = false` the user
    explicitly wants every item every run, so conditional requests are **disabled** (a `304`-driven
    empty delta would violate that), and `etags.json` is left untouched.
  - New `[etag_cache]` config section (`enabled` bool default `true`, `path` default
    `./.osspulse/etags.json`) parsed and validated at load time (fail-fast on a non-boolean
    `enabled`, mirroring `[delta]`); `Config` gains `etag_cache_enabled: bool` and
    `etag_cache_path: str`.
- **Documentation**: README gains a short note that runs now send conditional GitHub requests to save
  rate-limit budget, where the ETag cache lives, and that it is a best-effort optimization safe to
  delete.

## Capabilities

### New Capabilities
- **`conditional-cache`** — the `ConditionalCache` port + `JsonFileETagStore` adapter: per-repo,
  per-endpoint persistence of HTTP validators (ETag) between runs, atomic writes, best-effort
  corrupt-tolerance, and the security invariant that only repo/endpoint keys + validator strings are
  stored (never the token, never response bodies). Spec: `specs/conditional-cache/spec.md`.

### Modified Capabilities
- **`github-collector`** — ADDED requirements only: the REST paths accept an injected
  `ConditionalCache`, send `If-None-Match` on the first page, treat a `304` as an empty delta for that
  endpoint, and record the fresh `ETag` on a `200`; the pure-I/O boundary and the frozen
  `GitHubClient` Protocol are reaffirmed unchanged; GraphQL stays unconditional. No existing issue,
  release, or discussion behavior changes on a cache miss (a collector with no cache, or an empty
  cache, behaves exactly as today). Delta spec: `specs/github-collector/spec.md`.
- **`scheduler-cli`** — MODIFIED: `run_pipeline` constructs and injects the `JsonFileETagStore`
  (best-effort), gates conditional requests on `etag_cache_enabled` AND `delta_enabled`, and commits
  the ETag cache only after `mark_seen`; `config.py` parses/validates the `[etag_cache]` section.
  Same pipeline-wiring home as v2-001/v2-003/v2-006 (`pipeline.py` only). Delta spec:
  `specs/scheduler-cli/spec.md`.

## Impact

- **New code**: `src/osspulse/cache/etag_store.py` (`JsonFileETagStore` + a `_NullConditionalCache`
  no-op); a `ConditionalCache` Protocol added to `src/osspulse/ports.py`; `_build_etag_cache(config)`
  in `pipeline.py` (mirrors `_build_cache`).
- **Touched code**: `src/osspulse/github/client.py` (`__init__` gains `conditional_cache`;
  `_request_with_retry` gains `extra_headers`; `_classify` maps `304`; `fetch_items` / `fetch_releases`
  send the conditional header on page 1 and branch on `304`); `src/osspulse/pipeline.py`
  (`_collect_all` receives the cache-bearing collector; `run_pipeline` builds+injects it and calls
  `commit()` after the loop); `src/osspulse/config.py` (parse `[etag_cache]`); `Config` gains two
  fields.
- **Config**: new `[etag_cache]` section (`enabled`, `path`), both optional with defaults.
- **External**: fewer GitHub requests counted against rate limit — a `304` costs 0 budget; a run over
  an unchanged watchlist trends toward ~0 rate-limit consumption. No new external dependency.
- **No change** to the Summarizer, Redis summary cache, Digest Renderer, Delivery, or the State
  Store's schema/behavior. The ETag store is a **new, separate** file; `state.json` (`version: 1`) is
  untouched.

---

## Non-Goals

- ❌ **No `If-Modified-Since` / `Last-Modified` path** — `ETag` + `If-None-Match` is the stronger,
  sufficient validator; storing/sending `Last-Modified` too is deferred (future, if ever needed).
- ❌ **No conditional requests for Discussions (GraphQL)** — the GraphQL API does not support `ETag`;
  `fetch_discussions` is unchanged and always fetched.
- ❌ **No conditional requests on pages 2..N** — only the newest-first first page carries
  `If-None-Match`; that is sufficient to detect "nothing new". Later pages paginate unconditionally
  exactly as today.
- ❌ **No merge of ETag state into `state.json`** — a separate `etags.json` avoids bumping the
  State Store's locked `version: 1` schema and keeps the two concerns (correctness vs optimization)
  independently deletable.
- ❌ **No caching of response bodies** — this stores only opaque validator strings; the summary cache
  (Redis) already handles content reuse. `etags.json` never contains issue/release content or the
  token.
- ❌ **No new rate-limit budgeting logic** — the existing retry/backoff and `X-RateLimit-Remaining`
  handling is unchanged; this change only *reduces* how often the budget is spent.
- ❌ **No ETag validation/parsing** — the validator is treated as an opaque string echoed verbatim
  into `If-None-Match` (works for both strong `"..."` and weak `W/"..."` forms).
- ❌ **No per-endpoint config toggle** — one `[etag_cache] enabled` switch governs all REST endpoints
  together; issues and releases are not independently toggleable.

## Assumptions

- **[CONFIRMED]** GitHub returns an `ETag` on REST issue/release responses and answers a matching
  `If-None-Match` with `304 Not Modified`, and a `304` **does not count against the rate limit**.
  *(Source: kickoff task + GitHub REST API conditional-requests docs.)*
- **[CONFIRMED]** Issues and releases are fetched newest-first (`sort=created&direction=desc` for
  issues; `/releases` is newest-first) — a new item appears on the first page and changes its `ETag`,
  so a first-page `304` provably means "nothing new in the window" → an empty delta for that endpoint.
  *(Source: living `github-collector` spec — bounded-pagination requirement + `client.py`
  `fetch_items`/`fetch_releases`.)*
- **[CONFIRMED]** GraphQL / Discussions do **not** support `ETag` and are excluded (REST-only).
  *(Source: kickoff task; GitHub GraphQL API.)*
- **[CONFIRMED]** ETag persistence belongs in a **separate** file, not in `state.json`, because the
  State Store enforces a locked `version: 1` schema and a distinct fatal-on-corruption contract; the
  ETag cache is best-effort. *(Source: `state/json_store.py` `_STATE_VERSION` + `StateError` on
  corruption; the two files have opposite corruption semantics.)*
- **[CONFIRMED]** The ETag cache is injected into the collector as an optional dependency defaulting
  to a no-op, mirroring how the Redis `SummaryCache` is injected into the Summarizer and built
  best-effort in `pipeline._build_cache`; a collector with no cache behaves exactly as V1/V2 today.
  *(Source: `pipeline._build_cache` / `_NullCache`; `ports.SummaryCache`.)*
- **[CONFIRMED]** Conditional requests must be gated by `delta_enabled`: when delta is off the user
  wants every item every run, so a `304`-driven empty delta would be wrong — conditional requests are
  disabled and `etags.json` is untouched. *(Source: v2-001 delta semantics — `delta_enabled=false`
  reproduces V1 "show everything".)*
- **[CONFIRMED]** The ETag for an endpoint must not be persisted until the items fetched under it are
  recorded seen; otherwise a crash after a `200` fetch but before `mark_seen` would make the next run
  `304`-skip items that were never rendered — a lost-item bug. Resolved by in-memory `set()` +
  post-`mark_seen` `commit()`. *(Analyst correctness analysis; see RISK-001. The exact commit
  wiring is an S3 design detail, but the behavior — never lose an item — is CONFIRMED and testable.)*
- **[ASSUMED]** A `200` response could omit the `ETag` header (proxies, edge cases) → the collector
  records nothing for that endpoint (or clears any stale entry) and the next run is unconditional; no
  crash. *(Analyst inference from dirty-data tolerance; validate at SPEC-LOCK.)*
- **[ASSUMED]** The single-instance run lock (v2-002) already serializes concurrent runs against the
  same state directory, so the ETag store needs atomicity (torn-read safety via temp+rename) but not
  its own cross-process lock. *(Source: `lock.py` / v2-002 `AC-V2-002-021`; validate at SPEC-LOCK.)*

## Edge Cases

1. **State/first run** — no `etags.json` (or no entry for the endpoint) → unconditional fetch; on the
   `200`, record the first-page `ETag`; behaves exactly as today.
2. **State transition/unchanged** — second run, nothing new → first-page conditional returns `304` →
   empty list for that endpoint, zero rate-limit budget consumed, stored `ETag` unchanged.
3. **State transition/new item** — second run, a new issue appeared → `200` (first-page `ETag`
   changed) → full unconditional pagination as today, fresh `ETag` recorded, delta filter renders
   only the genuinely new items.
4. **Data integrity** — `etags.json` is corrupt/unparseable → WARN, treat as empty cache,
   unconditional fetch, run continues (NOT fatal — contrast the State Store).
5. **Data integrity** — `200` response with no `ETag` header → record nothing / clear any stale entry
   for that endpoint; next run unconditional; no crash.
6. **Data integrity** — cached validator is a weak ETag (`W/"abc"`) → echoed verbatim in
   `If-None-Match`; never parsed or normalized.
7. **Integration/multi-endpoint** — for one repo, issues → `304` (empty) while releases → `200`
   (fetched): the two endpoints are keyed independently (`repo:issues` vs `repo:releases`) and behave
   independently.
8. **Integration/GraphQL** — discussions are fetched via GraphQL with **no** conditional request ever;
   `fetch_discussions` and its ETag-free behavior are unchanged.
9. **Integration/error** — first page returns `404`/`410` (repo gone) → skip repo as today (WARN +
   empty); the stored ETag for that repo is irrelevant/untouched; no crash.
10. **Integration/error** — conditional first-page request returns `429`/`5xx`/secondary-rate-limit →
    same retry/backoff as today (the conditional header rides the same `_request_with_retry`); a
    terminal `RateLimitError` still delivers partial results (AC-7-017).
11. **Concurrency** — two runs race → serialized by the existing single-instance lock; the ETag
    store's atomic temp+rename write guarantees a reader never sees a torn `etags.json`.
12. **Crash safety (correctness)** — a run gets `200`, collects items, then crashes/aborts before
    `mark_seen`/`commit` → `etags.json` is unchanged on disk → the next run re-fetches and renders
    those items; the ETag optimization NEVER skips an item before it is recorded seen. **[RISK-001]**
13. **Config** — `etag_cache_enabled = false` → never send `If-None-Match`; always full fetch (V2
    behavior); `etags.json` untouched.
14. **Config** — `delta_enabled = false` → conditional requests disabled regardless of
    `etag_cache_enabled` (a `304`-empty would violate "show everything"); `etags.json` untouched.
15. **Config** — `[etag_cache] enabled = "yes"` (non-boolean) → `load_config` raises `ConfigError`
    before the pipeline runs (fail-fast, mirroring `[delta]`).
16. **Security** — `etags.json` contains only `"{repo}:{endpoint}"` keys and opaque validator strings;
    the `GITHUB_TOKEN` and any response body NEVER appear in it, in a log, or in an error.
17. **Rate budget** — a run where every REST endpoint answers `304` consumes ~0 rate-limit budget and
    still delivers a valid "no new items" digest.

## Early Risk Flags

STRIDE gate: **SKIPPED** (`security.stride_analysis = auto`; this change adds **no new secret
handling, no PII, no upload, no admin, and no new auth surface** — it reuses the same authenticated
`GITHUB_TOKEN` on the same TLS-on httpx client, adds one request header, and persists only opaque
non-secret validator strings). The relevant invariants are reaffirmed rather than re-derived:

- **RISK-001 — Correctness / lost-item on crash (MEDIUM)**: persisting an `ETag` for items that were
  fetched but not yet recorded seen would make the next run `304`-skip un-rendered items — silent
  data loss, violating the "idempotent, never lose an item" non-negotiable. Mitigation: in-memory
  `set()` during fetch + a single post-`mark_seen` `commit()` in the pipeline; a crash before commit
  leaves `etags.json` unchanged. Covered by AC-V2-007-024/025; the top handoff watch item for S3.
- **RISK-002 — Correctness / stale 304 masking new items (LOW)**: sending `If-None-Match` on the wrong
  (not-newest-first) page could `304` while new items exist deeper. Mitigation: conditional request on
  the newest-first **first page only**; the "everything new appears at the top" guarantee holds only
  against `sort=created&direction=desc` — reaffirmed in AC-V2-007-010/012.
- **RISK-003 — Information disclosure (LOW, reaffirm)**: `etags.json` must contain only keys +
  validator strings; the token and response bodies must never be written there or logged. Mitigation:
  reuse the collector's token discipline (github-collector-2 ADR-004 / AC-2-009); AC-V2-007-006.
- **RISK-004 — Availability / corrupt cache (LOW)**: a corrupt `etags.json` must degrade to
  unconditional fetch, never abort the run (opposite of `state.json`). Mitigation: best-effort
  load → empty cache + WARN; AC-V2-007-004.

## Business Rules

- **BR-V2-007-001**: The `conditional-cache` capability SHALL persist, per `"{repo}:{endpoint}"` key,
  the last-observed first-page HTTP `ETag` validator for the REST endpoints `issues` and `releases`,
  and SHALL store nothing else (no token, no response body, no PII).
- **BR-V2-007-002**: The ETag cache SHALL be **best-effort**: a missing, empty, corrupt, or unreadable
  `etags.json` SHALL degrade to an empty cache with a WARN and the run SHALL continue with
  unconditional fetches — losing the cache SHALL NEVER change which items are collected/rendered.
- **BR-V2-007-003**: `JsonFileETagStore` SHALL persist to a file separate from `state.json` (default
  `./.osspulse/etags.json`), writing atomically (temp file in the same directory → `fsync` →
  `os.replace`), and SHALL NOT read, write, or alter the State Store's `state.json`.
- **BR-V2-007-004**: The Collector SHALL send `If-None-Match: <etag>` on the **first page only** of a
  REST endpoint when a validator is cached for `"{repo}:{endpoint}"`, and SHALL NOT send a conditional
  header on subsequent pages or on the GraphQL (discussions) path.
- **BR-V2-007-005**: A first-page `304 Not Modified` SHALL cause the Collector to return an empty list
  for that endpoint and make no further page requests (empty delta); this is sound only because the
  endpoint is fetched newest-first, so any new item would change the first page's `ETag`.
- **BR-V2-007-006**: On a first-page `200`, the Collector SHALL record the response's `ETag` (when
  present) into the cache via `set()` and proceed with the existing unconditional pagination; a `200`
  with no `ETag` header SHALL record nothing (or clear a stale entry) and NOT crash.
- **BR-V2-007-007**: The Collector SHALL depend only on the `ConditionalCache` **port**,
  `osspulse.models`, and httpx — it SHALL NOT import the concrete `JsonFileETagStore` or the State
  Store; the injected cache SHALL default to a no-op null cache so a collector built without one
  behaves exactly as today. The `GitHubClient` Protocol SHALL remain unchanged.
- **BR-V2-007-008**: `set()` SHALL update only the in-memory cache; the durable write SHALL occur only
  when the pipeline calls `commit()`, which the pipeline SHALL invoke only **after** the collected
  items have been recorded via `mark_seen` — so a run that aborts before that point leaves
  `etags.json` unchanged and the next run re-fetches (no item skipped before it is recorded seen).
- **BR-V2-007-009**: Conditional requests SHALL be enabled only when BOTH `etag_cache_enabled` is
  `true` AND `delta_enabled` is `true`; when either is `false` the run SHALL send no conditional
  header and SHALL leave `etags.json` untouched.
- **BR-V2-007-010**: `config.py` SHALL parse an optional `[etag_cache]` section (`enabled` boolean
  default `true`; `path` string default `./.osspulse/etags.json`), validate `enabled` at load time,
  and fail fast with a `ConfigError` on a non-boolean value; absence SHALL default to
  `etag_cache_enabled = true`.
- **BR-V2-007-011**: The conditional first-page request SHALL reuse the existing
  `_request_with_retry`/`_classify` machinery unchanged for transport errors (`429`/`5xx`/
  secondary-rate-limit → retry; non-rate-limit `401`/`403` → fail fast); only the `304` status and the
  `If-None-Match` request header are new. The `GITHUB_TOKEN` SHALL never appear in `etags.json`, a log,
  or an error on the conditional path.
- **BR-V2-007-012**: No conditional caching SHALL be applied to Discussions (GraphQL has no `ETag`);
  `fetch_discussions` SHALL remain unchanged and always fetch.

## Integration Points

- **INT-V2-007-001**: `GitHubCollector.__init__` accepts an injected `ConditionalCache`
  (`osspulse.ports`), used by `fetch_items` / `fetch_releases` for first-page conditional requests via
  the existing authenticated httpx client.
- **INT-V2-007-002**: `pipeline.run_pipeline` builds `JsonFileETagStore(config.etag_cache_path)`
  best-effort (null cache on failure, mirroring `_build_cache` for Redis) and injects it into
  `GitHubCollector`, then calls `conditional_cache.commit()` once after the per-repo collection loop
  (post-`mark_seen`).
- **INT-V2-007-003**: `JsonFileETagStore` persists to `etags.json` under `config.etag_cache_path`
  independently of `JsonFileStateStore` / `state.json` — the two never touch each other's file.
- **INT-V2-007-004**: `config.load_config` parses the `[etag_cache]` section into
  `Config.etag_cache_enabled` / `Config.etag_cache_path`, gated together with `Config.delta_enabled`.
- **INT-V2-007-005**: The single-instance run lock (v2-002) serializes concurrent runs so the ETag
  store needs only atomic-write torn-read safety, not its own lock.

## Figma
Figma: N/A (CLI tool — no visual design surface).

---
## _Structured Extract

### AC List
- AC-V2-007-001: [CONFIRMED] `ConditionalCache` port defines `get(key)->str|None`, `set(key,validator)`, `commit()`; `JsonFileETagStore` implements it
- AC-V2-007-002: [CONFIRMED] Store persists per-`"{repo}:{endpoint}"` validator to a separate `etags.json`; round-trips `set`→`commit`→(new instance)`get`
- AC-V2-007-003: [CONFIRMED] `commit()` writes atomically (temp in same dir → fsync → os.replace); a concurrent reader never sees a torn file
- AC-V2-007-004: [CONFIRMED] Missing/empty/corrupt/unreadable `etags.json` → empty cache + WARN, no raise (best-effort)
- AC-V2-007-005: [CONFIRMED] `set()` mutates in-memory only; nothing is written to disk until `commit()`
- AC-V2-007-006: [CONFIRMED] `etags.json` contains only keys + validator strings — never the token or any response body
- AC-V2-007-007: [CONFIRMED] A `_NullConditionalCache` no-op (`get`→None, `set`/`commit`→no-op) satisfies the port
- AC-V2-007-008: [CONFIRMED] The store never reads/writes `state.json`; the two files are independent
- AC-V2-007-009: [CONFIRMED] Collector accepts an injected `ConditionalCache` (default null); a collector with no cache behaves exactly as today
- AC-V2-007-010: [CONFIRMED] With a cached validator, `fetch_items`/`fetch_releases` send `If-None-Match:<etag>` on the FIRST page only
- AC-V2-007-011: [CONFIRMED] First-page `304` → return empty list for that endpoint, no further page requests (empty delta)
- AC-V2-007-012: [CONFIRMED] First-page `200` → record the fresh `ETag` via `set()` and paginate unconditionally as today; new items surface via the existing delta
- AC-V2-007-013: [CONFIRMED] Conditional header is sent on the first page only — pages 2..N are unconditional
- AC-V2-007-014: [CONFIRMED] A `200` with no `ETag` header records nothing / clears stale entry; no crash
- AC-V2-007-015: [CONFIRMED] Weak ETag `W/"..."` echoed verbatim in `If-None-Match`; never parsed/normalized
- AC-V2-007-016: [CONFIRMED] `_classify` maps `304` to the OK class so the fetch method branches on it; `429`/`5xx`/auth handling unchanged on the conditional request
- AC-V2-007-017: [CONFIRMED] GraphQL/discussions never send a conditional header; `fetch_discussions` unchanged
- AC-V2-007-018: [CONFIRMED] Collector still touches no State Store / LLM; `GitHubClient` Protocol unchanged; token never in any conditional-path log/error
- AC-V2-007-019: [CONFIRMED] `run_pipeline` builds `JsonFileETagStore` best-effort (null cache on any failure) and injects it into the collector
- AC-V2-007-020: [CONFIRMED] `[etag_cache]` section parsed: `enabled` bool default true, `path` default `./.osspulse/etags.json`; absent → enabled=true
- AC-V2-007-021: [CONFIRMED] Non-boolean `[etag_cache] enabled` → `ConfigError` at load, before the pipeline runs
- AC-V2-007-022: [CONFIRMED] Conditional requests active only when `etag_cache_enabled` AND `delta_enabled` are both true
- AC-V2-007-023: [CONFIRMED] `delta_enabled=false` OR `etag_cache_enabled=false` → no conditional header sent, `etags.json` untouched
- AC-V2-007-024: [CONFIRMED] Pipeline calls `commit()` only after the per-repo collection loop (post-`mark_seen`)
- AC-V2-007-025: [CONFIRMED] A run that aborts before commit (e.g. `mark_seen`/`AuthError`) leaves `etags.json` unchanged → next run re-fetches those items (no lost item)
- AC-V2-007-026: [CONFIRMED] End-to-end: run1 `200` records items+ETag; run2 (no new activity) first-page `304` → "no new items" digest delivered, exit 0, ~0 rate budget
- AC-V2-007-027: [CONFIRMED] End-to-end: run2 with a new issue → `200` → only the new item rendered (delta), fresh ETag stored
- AC-V2-007-028: [CONFIRMED] A corrupt `etags.json` at run start → WARN, unconditional fetch, run completes normally (exit 0)

### Business Rules
- BR-V2-007-001: Store only `{repo}:{endpoint}`→ETag for issues/releases; no token/body/PII
- BR-V2-007-002: Best-effort — missing/corrupt cache degrades to empty + WARN, never changes collected items
- BR-V2-007-003: Separate atomic `etags.json`; never touches `state.json`
- BR-V2-007-004: `If-None-Match` on first page only; never on later pages or GraphQL
- BR-V2-007-005: First-page `304` → empty delta for that endpoint (sound because newest-first)
- BR-V2-007-006: First-page `200` → record ETag (when present) + paginate as today; missing ETag → no crash
- BR-V2-007-007: Collector depends on the port only (default null cache); Protocol unchanged; no-cache == today
- BR-V2-007-008: `set()` in-memory; `commit()` durable, called only post-`mark_seen` (crash-safety)
- BR-V2-007-009: Conditional requests gated by `etag_cache_enabled` AND `delta_enabled`
- BR-V2-007-010: Parse/validate `[etag_cache]`; fail-fast on non-boolean `enabled`; default enabled=true
- BR-V2-007-011: Reuse `_request_with_retry`/`_classify` for transport errors; only `304`+`If-None-Match` new; token never leaked
- BR-V2-007-012: No conditional caching for Discussions (GraphQL has no ETag); `fetch_discussions` unchanged

### Integration Points
- INT-V2-007-001: Collector `__init__` gains injected `ConditionalCache`, used by REST fetch methods
- INT-V2-007-002: pipeline builds+injects `JsonFileETagStore` best-effort; calls `commit()` post-loop
- INT-V2-007-003: `etags.json` persisted independently of `state.json`
- INT-V2-007-004: `config.load_config` parses `[etag_cache]` → `Config.etag_cache_enabled`/`etag_cache_path`
- INT-V2-007-005: v2-002 single-instance lock serializes runs; store needs atomic write only

### Risk Flags
- RISK-001: Lost-item on crash if ETag committed before mark_seen — MEDIUM (in-memory set + post-mark_seen commit)
- RISK-002: Stale 304 masking new items — LOW (conditional on newest-first first page only)
- RISK-003: Token/body leakage into etags.json/logs — LOW (reaffirm ADR-004 token discipline)
- RISK-004: Corrupt etags.json — LOW (best-effort empty + WARN, never fatal — opposite of state.json)

### Metadata
ticket_id: V2-007
domain: conditional-cache, github-collector, scheduler-cli
has_figma: false
has_cms_ui: false
actors: [operator]
ac_count: 28
ac_confirmed: 28
ac_assumed: 0
ac_missing: 0
ac_unclear: 0
edge_cases: 17
stride_gate: SKIPPED
renderer_delta: NONE (no rendering change — a 304 yields the existing no-new-items doc)
scope: standard
rigor: lite
