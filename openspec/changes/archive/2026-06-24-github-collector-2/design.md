## Sketch — Gap Analysis

**No critical gaps found.** The spec deltas (27 ACs / 14 BRs / 3 INTs, all CONFIRMED) map
cleanly onto the existing ports/adapters architecture. The `GitHubClient` Protocol and the
`RawItem`/`Config`/`WatchedRepo` models already exist; this change only adds the concrete
`github/` adapter that implements the port.

Two minor technical decisions are resolved below as ADRs (not spec gaps — no S2 return):

- **Where collector tunables live (BR-2-013/014).** The port signature
  `fetch_items(repo, lookback_days)` does NOT carry config, and the frozen `Config`
  dataclass has no collector fields. Resolved by **ADR-001**: inject a `CollectorConfig`
  (with a nested `RetryPolicy`) through the adapter constructor (dependency injection),
  leaving the port signature and the S1 `Config` contract untouched.
- **How to mock httpx in tests.** `respx` is not in the dependency set. Resolved by
  **ADR-005**: use httpx `MockTransport` (no new dependency).

Sketch summary:
- **Outbound calls**: 1 — `GET {base_url}/repos/{owner}/{repo}/issues` (INT-2-002). No HTTP
  API surface is exposed (CLI tool) → **no `openapi.yaml`** for this change (see ADR-007).
- **DB tables**: none — the Collector is pure I/O and never touches the State Store
  (AC-2-015, BR-2-012).
- **Key flow**: `fetch_items()` → validate repo → paginate (Link `rel=next`,
  `per_page=page_size`) with a retry wrapper per request → map each issue to `RawItem`
  (guarding every field) → early-stop on cutoff or `max_items_per_repo` → return
  `list[RawItem]`.

---

## Context

OSS Pulse is a self-hosted CLI that watches a list of GitHub repos and produces an
LLM-summarized Markdown digest of newly-opened issues. The pipeline
(Config → **Collector** → State → Summarizer → Render → Delivery) currently has a bare
`GitHubClient` Protocol stub and no way to actually fetch from GitHub. This change adds the
first real external integration: an httpx-based GitHub REST adapter under
`src/osspulse/github/`.

**Current state (verified by reading the code):**
- `src/osspulse/ports.py` — `GitHubClient` Protocol: `fetch_items(repo, lookback_days) -> list[RawItem]`.
- `src/osspulse/models.py` — `RawItem` (frozen dataclass: `repo, item_type, item_id, title, body, url, created_at`, all `str`); `Config` (frozen, holds `github_token`, `lookback_days`); `WatchedRepo`.
- `src/osspulse/config.py` — already validates `owner/name` via `_REPO_RE = ^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` and resolves `GITHUB_TOKEN` from env.
- `src/osspulse/github/__init__.py` — empty; the adapter goes here.
- Stack: Python 3.13, `httpx>=0.27`, pytest + pytest-cov (fail_under 80), ruff. `ports.py` and `pipeline.py` are excluded from coverage.

**Constraints (from `context/architecture.md` + `context/conventions.md`):**
- Core depends only on port interfaces; adapters depend on core models, never on each other.
- **S2 (GitHub I/O) and S4 (LLM I/O) must never call each other** — pure I/O boundary.
- Outbound error policy: 4xx permanent (no blind retry); 5xx/429/rate-limit retryable with
  backoff honoring `X-RateLimit-Remaining`/`Retry-After`.
- Secrets only from env; never logged.
- No new heavy dependencies (no DB, queue, web framework in V1).

## Goals / Non-Goals

**Goals:**
- Implement `GitHubCollector` (the `GitHubClient` adapter) fetching newly-opened issues for
  one repo within `lookback_days`, returning `list[RawItem]`.
- All tunables config-driven (BR-2-013/014): `max_items_per_repo`, `page_size`, `base_url`,
  and a single `RetryPolicy` object — no hardcoded literals in the fetch loop.
- Guarantee the `GITHUB_TOKEN` never reaches logs, errors, or returned data (AC-2-009).
- Tolerate dirty response data (AC-2-010/012); bounded pagination with early-stop
  (AC-2-005/006); rate-limit handling + per-repo error isolation (AC-2-008/011/019-023).

**Non-Goals:**
- Discussions / Releases / GraphQL (V2); pull requests as items; delta filtering; the
  watchlist loop (lives in the pipeline); concurrency; caching GitHub responses;
  reading/writing the State Store; any LLM call. (All per proposal § Out of Scope.)

## Architecture Overview

Ports/adapters (hexagonal-lite). The Collector is a single adapter implementing one port.

```
pipeline (core)                 github/ adapter (this change)
   │  builds CollectorConfig         ┌─────────────────────────────┐
   │  + token from Config            │ GitHubCollector              │
   └────────────────────────────────▶│   .fetch_items(repo, days)  │
                                      │     ├─ _validate_repo()      │  AC-2-014
                                      │     ├─ _paginate()  ◀────────┼─ Link rel=next, per_page
                                      │     │    └─ _request_with_retry()  AC-2-019..023
                                      │     ├─ _map_item()  ◀────────┼─ guard every field  AC-2-010/012/016/017
                                      │     └─ early-stop (cutoff / max_items)  AC-2-005/006
                                      └──────────────┬──────────────┘
                                                     │ httpx.Client(base_url, verify=True)
                                                     ▼
                                          GET /repos/{owner}/{repo}/issues
```

**Dependencies (cross-change):**
- Consumes `project-foundation` exports only: `osspulse.models.RawItem`,
  `osspulse.ports.GitHubClient`. Does NOT modify any locked requirement of that capability.
- Reuses the repo-pattern intent from `osspulse.config._REPO_RE` (see ADR-006 — shared regex).

**Module layout (new):**
```
src/osspulse/github/
  __init__.py
  config.py     # CollectorConfig + RetryPolicy dataclasses (defaults)
  errors.py     # CollectorError hierarchy (token-safe messages)
  client.py     # GitHubCollector (the adapter)
tests/
  test_github_client.py
```

## Decisions (ADRs)

### ADR-001: Inject collector tunables via a `CollectorConfig` constructor argument

**Context.** BR-2-013/014 require every tunable to be config-driven, but the port
`fetch_items(repo, lookback_days)` takes no config and the S1 `Config` dataclass is a frozen
contract with no collector fields. We must thread `max_items_per_repo`, `page_size`,
`base_url`, and the retry policy somewhere without breaking the port or S1.

| Option | Pros | Cons |
|--------|------|------|
| A. Add fields to S1 `Config` dataclass | one config object | mutates a locked S1 contract; couples Collector tunables into global config; frozen dataclass churn |
| B. New `CollectorConfig` (+ nested `RetryPolicy`) injected via `GitHubCollector.__init__` | port + S1 untouched; tunables localized to the adapter; trivially testable with overrides; matches DI used elsewhere | one more small dataclass |
| C. Pass tunables as `fetch_items` kwargs | no new type | breaks the `GitHubClient` Protocol signature (INT-2-001 violation) |

**Decision: B.** Define `CollectorConfig` and `RetryPolicy` (frozen dataclasses with the
locked defaults) in `github/config.py`; the constructor takes
`GitHubCollector(token: str, config: CollectorConfig = CollectorConfig())`. The pipeline
builds it from env + (future) user config. Satisfies BR-2-013/014, keeps INT-2-001 intact.

**Consequences.** Tunables are overridable per-construction (AC-2-024/026/027); tests
inject tiny configs (e.g. `page_size=2`) to exercise pagination without large fixtures. The
token is a separate constructor arg (not inside `CollectorConfig`) so config objects are
safe to log/repr (ADR-004).

### ADR-002: One `RetryPolicy` object + a single `_request_with_retry` wrapper

**Context.** BR-2-014/AC-2-026 require retry behavior behind ONE config object, not
constants scattered per call site. Every HTTP GET (first page + each `rel=next`) must share
the same bounded backoff and 429/5xx/secondary-limit handling.

| Option | Pros | Cons |
|--------|------|------|
| A. Inline retry/sleep at each call site | "simple" | violates BR-2-014; duplicated logic; AC-2-026 fails |
| B. Single `_request_with_retry(url) -> Response` wrapping ALL GETs, driven by `RetryPolicy` | one place to tune; honors AC-2-026; testable in isolation | must thread policy into the helper |

**Decision: B.** `_request_with_retry` is the only method that calls `httpx`. Wait formula:
`min(backoff_base * multiplier**(attempt-1) + uniform(0, jitter), ceiling)`, with
`Retry-After` taking precedence when present (still capped by `ceiling`). Retries on
`429`, `5xx`, `403 + X-RateLimit-Remaining: 0`, and transport errors
(`httpx.TransportError`), up to `max_retries`; then raises.

**Consequences.** Tuning = change `RetryPolicy` fields, no loop edits (AC-2-026). Sleep is
injected (a `sleep` callable defaulting to `time.sleep`) so tests assert backoff without
real delays.

### ADR-003: HTTP-status → behavior decision table (single classifier)

**Context.** The 403 branch is ambiguous (AC-2-008 vs AC-2-020) and per-repo isolation
(AC-2-011) vs fail-fast (AC-2-008) must be deterministic. Mis-routing a status either aborts
a whole run on a transient limit or silently swallows a real auth failure.

| Option | Pros | Cons |
|--------|------|------|
| A. Branch inline as statuses are seen | fewer functions | scattered logic; hard to test the 403 split; easy to drift |
| B. One `_classify(response)` → enum {OK, RETRY, SKIP_REPO, FAIL_FAST} consumed by both the request wrapper and the paginate loop | single source of truth; directly testable per status; mirrors the Error/Outcome table | one helper |

**Decision: B.** Classification:

| Condition | Class | Action |
|-----------|-------|--------|
| `200` | OK | map + continue |
| `404` / `410` | SKIP_REPO | warn, return `[]` for the repo (AC-2-011) |
| `403` + `X-RateLimit-Remaining: 0` | RETRY | backoff (AC-2-020) |
| `429`, `5xx` | RETRY | backoff (AC-2-019/021) |
| other `401` / `403` | FAIL_FAST | raise `AuthError` (AC-2-008) |
| other `4xx` | FAIL_FAST | raise (4xx permanent, conventions.md) |
| transport error | RETRY then FAIL_FAST | bounded retry then `NetworkError` (AC-2-023) |

**Consequences.** The 403 split is one tested branch keyed on the header. SKIP_REPO returns
empty for that repo without aborting the run; the pipeline loop (not the Collector) keeps
going.

### ADR-004: Token isolation — never in config repr, logs, or errors

**Context.** T-I1 (High, AC-2-009): the token must never appear in logs, exception text, or
returned data. The risk is any code path that stringifies the request, headers, or config.

| Option | Pros | Cons |
|--------|------|------|
| A. Hope no log statement prints it | none | one careless `f"{request}"` leaks it (T-I1) |
| B. Token kept out of any `repr`-able object; auth set on the httpx client at construction; errors reference failure CLASS + status only, never request/headers; explicit redaction test | structurally prevents leakage; testable | requires discipline + a dedicated test |

**Decision: B.** The token is passed to `httpx.Client(headers={"Authorization": ...})` once
at construction and is NOT stored on `self` as a plain attribute beyond what httpx holds;
`CollectorConfig` never contains the token; `CollectorError` messages include only the
status code, repo, and a static reason string — never the response body's auth echo or
headers. A test (AC-2-009) asserts the token string is absent from `caplog`, the raised
exception text, and every returned `RawItem`.

**Consequences.** Logging the config object or an error is safe by construction. Adds one
mandatory security test (Risky Area #1).

### ADR-005: Mock httpx with `MockTransport` (no new dependency)

**Context.** All tests must mock GitHub (no real API — stack rule). `respx` is not a
declared dependency.

| Option | Pros | Cons |
|--------|------|------|
| A. Add `respx` dev dep | ergonomic route mocking | new dependency for a single adapter; pinning/maintenance |
| B. `httpx.MockTransport(handler)` | zero new deps; full control over status/headers/Link; first-class httpx | handler is slightly more verbose |

**Decision: B.** Inject an `httpx.Client(transport=httpx.MockTransport(handler))` in tests; a
handler function returns canned `httpx.Response`s keyed on URL/page, including `Link`
headers, `X-RateLimit-Remaining`, `Retry-After`, null bodies, and PR items.

**Consequences.** No dependency change. The adapter must accept an optional injected client
(or transport) for testability — `GitHubCollector(token, config, *, client=None)`.

### ADR-006: Reuse the repo-validation pattern, don't redefine it

**Context.** AC-2-014/BR-2-011 require the Collector to reject non-`owner/name` repos.
`config.py` already has `_REPO_RE`. Two regexes drifting apart is a latent bug.

| Option | Pros | Cons |
|--------|------|------|
| A. Re-declare a regex in the Collector | no import coupling | drift risk; two sources of truth |
| B. Promote the pattern to a shared constant and reuse it | one source of truth | a small refactor of `config.py` |

**Decision: B.** Expose the pattern as `osspulse.config.REPO_PATTERN` (module-level constant;
the existing `_REPO_RE` compiles it) and have the Collector validate against the same
pattern. The spec's `^[\w.-]+/[\w.-]+$` and config's
`^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` are equivalent for this purpose; the shared constant is
authoritative.

**Consequences.** A tiny, low-risk edit to `config.py` (rename to a public constant, keep
behavior). Collector raises `InvalidRepoError` before any request (AC-2-014, T-T2).

### ADR-007: No `openapi.yaml` for this change

**Context.** R5 normally requires a separate `openapi.yaml`. OSS Pulse exposes **no HTTP
API** (`context/conventions.md`: "N/A — no HTTP API"); the only HTTP is the *outbound* GitHub
call, which is GitHub's own contract, not ours to define.

| Option | Pros | Cons |
|--------|------|------|
| A. Author an openapi.yaml describing GitHub's `/issues` | satisfies R5 literally | documents a third-party API we don't own; misleading; no inbound surface to spec |
| B. Omit openapi.yaml; document the outbound call in § API Design + Error Mapping | honest to the architecture; conventions.md says N/A | deviates from R5 |

**Decision: B**, citing R5 deviation justified by `context/conventions.md` (no HTTP API
surface). The outbound GitHub call is fully specified in § API Design and § Error Mapping
instead.

**Consequences.** Cross-artifact audit should treat openapi.yaml as N/A for this change; the
internal contract is the typed `fetch_items` signature + `RawItem` dataclass.

### ADR-008: `Authorization: Bearer <token>` + recommend a fine-grained read-only PAT

**Context.** The auth header can be `token <t>` (classic PATs only) or `Bearer <t>` (both
classic and fine-grained; required for fine-grained). The operator is a normal single user
reading public-repo issues, and STRIDE T-E1 (AC-2-013) wants least privilege.

| Option | Pros | Cons |
|--------|------|------|
| A. `Authorization: token <t>` | familiar with classic PATs | does NOT work with fine-grained PATs; pushes the operator toward broad classic scopes |
| B. `Authorization: Bearer <t>` + recommend a fine-grained read-only PAT | works for BOTH PAT types; required for fine-grained; aligns with least-privilege (T-E1) | none material |

**Decision: B**, confirmed with the user. Use `Bearer`; document that the operator should
create a **fine-grained PAT with read-only access** (public-repo issue reads need minimal
scope). Reading the tunables from TOML is explicitly deferred (out of scope) — V1 runs on
`CollectorConfig` defaults, no change to the S1 config contract.

**Consequences.** One header value; works regardless of PAT type. README (S6) should note
the recommended token type + minimum scope.

## API Design

**No inbound HTTP API.** Internal contract (INT-2-001):

```python
class GitHubCollector:  # implements osspulse.ports.GitHubClient
    def __init__(self, token: str, config: CollectorConfig = CollectorConfig(),
                 *, client: httpx.Client | None = None, sleep=time.sleep) -> None: ...
    def fetch_items(self, repo: str, lookback_days: int) -> list[RawItem]: ...
```

**Outbound call (INT-2-002):**
- `GET {config.base_url}/repos/{owner}/{repo}/issues`
- Query: `state=all`, `sort=created`, `direction=desc`, `per_page={config.page_size}`
  (BR-2-002, AC-2-024).
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
  `X-GitHub-Api-Version: 2022-11-28`. TLS verify always on (AC-2-013). `Bearer` works for
  both classic and fine-grained PATs and is required for fine-grained (ADR-008); the
  operator is advised to use a **fine-grained read-only PAT** (least privilege, T-E1).
  Reading the tunables from TOML is deferred — V1 runs on `CollectorConfig` defaults
  (out of scope, confirmed; does not change the S1 config contract).
- Pagination: follow `Link` header `rel="next"` absolute URL; missing/malformed → stop
  (BR-2-004, AC-2-007).

**`CollectorConfig` / `RetryPolicy` (locked defaults — BR-2-013/014; defaults apply when omitted, explicit values override without code change AC-2-027):**

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    jitter_seconds: float = 0.5
    backoff_ceiling_seconds: float = 60.0

@dataclass(frozen=True)
class CollectorConfig:
    max_items_per_repo: int = 100
    page_size: int = 100
    base_url: str = "https://api.github.com"
    retry: RetryPolicy = RetryPolicy()
```

**RawItem mapping (AC-2-016, AC-2-017, BR-2-010):**

| RawItem field | Source | Guard |
|---------------|--------|-------|
| `repo` | the validated `owner/repo` arg | — |
| `item_type` | constant `"issue"` | — |
| `item_id` | `str(item["number"])` | KeyError → skip item (number is mandatory identity) |
| `title` | `item.get("title") or ""` | null/missing → `""` |
| `body` | `item.get("body") or ""` | null → `""` (AC-2-010) |
| `url` | `item.get("html_url") or ""` | missing → `""` (AC-2-012) |
| `created_at` | `item["created_at"]` (raw ISO) | mandatory for cutoff; missing → skip item |

## DB Schema

**N/A.** The Collector is pure I/O and never touches the State Store (AC-2-015, BR-2-012).
No tables, no migrations.

## Error Mapping

`github/errors.py`:

```
CollectorError(Exception)              # base; message = status + repo + static reason, never token/headers
├─ InvalidRepoError                    # repo fails ^[\w.-]+/[\w.-]+$  → AC-2-014 (pre-request)
├─ AuthError                           # 401 / non-rate-limit 403       → AC-2-008 (fail fast, all repos)
├─ RateLimitError (internal/retry)     # 429 / 403+remaining0 / 5xx     → AC-2-019/020/021 (retried, surfaced if exhausted)
└─ NetworkError                        # transport error past retries   → AC-2-023
```

| Outcome | Mapping | AC |
|---------|---------|----|
| Invalid repo | `InvalidRepoError`, raised before any HTTP | AC-2-014 |
| 404/410 one repo | warn log + return `[]` (no exception) | AC-2-011 |
| 401 / other 403 | `AuthError`, run stops, token absent from message | AC-2-008, AC-2-009 |
| 429 / 403+remaining0 / 5xx | retry per policy; if exhausted → `RateLimitError` | AC-2-019/020/021/022 |
| transport timeout | retry per policy; if exhausted → `NetworkError` | AC-2-023 |
| cap reached | info log "truncated at N for {repo}" (no token/PII) | AC-2-006 |

CLI surfacing (conventions.md): these raise to the pipeline; the CLI prints
`Error: <message>` to stderr and exits non-zero for fail-fast classes.

## Sequence Flows

**Happy path + early-stop (AC-2-001, AC-2-002, AC-2-003, AC-2-004, AC-2-005):**
```
fetch_items(repo, lookback_days)
  cutoff = now(UTC) - lookback_days                      # BR-2-009, tz-aware
  _validate_repo(repo)                                   # AC-2-014
  url = base_url/repos/{repo}/issues?state=all&sort=created&direction=desc&per_page=page_size
  items = []
  while url and len(items) < max_items_per_repo:         # AC-2-006 cap (config)
    resp = _request_with_retry(url)                      # ADR-002
    cls = _classify(resp)                                # ADR-003
    if cls is SKIP_REPO: return []                       # AC-2-011
    for raw in resp.json():
      if "pull_request" in raw: continue                 # AC-2-018
      created = raw.get("created_at")
      if created is None: continue                       # dirty guard
      if parse(created) < cutoff:                        # AC-2-005 per-item cutoff (handoff §3)
        return items                                     # early-stop, no more pages
      item = _map_item(raw, repo)                         # AC-2-010/012/016/017
      if item is not None: items.append(item)
      if len(items) >= max_items_per_repo:
        log.info("truncated at %d for %s", max_items_per_repo, repo)  # AC-2-006
        return items
    url = _next_link(resp.headers.get("Link"))           # BR-2-004, AC-2-007
  return items
```

**Retry (AC-2-019, AC-2-020, AC-2-021, AC-2-022, AC-2-023):**
```
_request_with_retry(url):
  for attempt in 0..max_retries:
    try: resp = client.get(url)
    except httpx.TransportError: classify=RETRY (network)
    else: classify = _classify(resp)
    if classify in {OK, SKIP_REPO, FAIL_FAST}: return/raise accordingly
    if attempt == max_retries: raise RateLimitError/NetworkError    # AC-2-022 bounded
    wait = retry_after if present else min(base*mult**attempt + U(0,jitter), ceiling)
    sleep(min(wait, ceiling))
```

## Edge Cases

Covers proposal EC-001..016. Notable mappings:
- EC-005 first page already past cutoff → return after that page, no `rel=next` follow.
- EC-006 issue opened mid-pagination → accepted drift; created-desc + per-item cutoff bound it.
- EC-008 missing `user`/`html_url` → safe default `""` (AC-2-012), item still returned.
- EC-011 `403 + X-RateLimit-Remaining: 0` → RETRY, not AuthError (ADR-003).
- EC-015 malformed/absent `Link` → `_next_link` returns `None` → single-page (AC-2-007).
- EC-016 cap reached → info truncation log (AC-2-006), token/PII-free.

## Performance

- Sequential, one repo at a time (V1; concurrency out of scope). Cost = ceil(min(in-window,
  max_items)/page_size) requests/repo; default ≤ 1 page for ≤100 items.
- `per_page=page_size` (default 100, GitHub max) minimizes request count → protects the
  5000/hr budget (T-D1).
- Early-stop on cutoff avoids fetching the long tail of old issues.
- Backoff ceiling (60s) bounds worst-case wait; `max_retries=3` bounds total attempts
  (no infinite retry, AC-2-022).

## Security

Addresses every Critical/High STRIDE threat (gate PASS; see `stride-threat-model.md`):

| Threat | Sev | Mitigation in this design | AC |
|--------|-----|---------------------------|----|
| T-I1 token leak | High | ADR-004: token never in config/repr/logs/errors; redaction test | AC-2-009 |
| T-T1 dirty data | High | `_map_item` guards every field; PRs/typeless items dropped; mandatory-field misses skip the item | AC-2-010/012 |
| T-D1 rate-limit DoS | High | config cap + per-item early-stop + bounded backoff respecting Retry-After | AC-2-005/006/019-022 |
| T-T2 SSRF-shaped repo | Med | `_validate_repo` pre-request (ADR-006); `base_url` constant, repo only fills path (AC-2-025) | AC-2-014/025 |
| T-S1/T-E1 TLS/scope | Med | TLS verify never disabled; GET-only; base_url from config never untrusted input | AC-2-013/025 |

No new inbound surface. No secrets stored on disk. Base URL overridable (GitHub Enterprise)
but only from config, never from `repo` or response data (AC-2-025).

## Risk Assessment

- [Token leak via an error path] → ADR-004 + a dedicated `caplog`/exception/return-value
  assertion test; review every `raise`/`log` in the adapter for header/body interpolation.
- [Page arrives unsorted, early-stop under-collects] → guard the cutoff **per item**, not
  per page (handoff §3); test a page-2-boundary fixture (AC-2-005).
- [Two repo regexes drift] → ADR-006 single shared constant.
- [Infinite retry] → `max_retries` hard bound + injected `sleep` asserted in tests (AC-2-022).
- [Mutating a frozen S1 `Config`] → avoided by ADR-001 (separate `CollectorConfig`).

## Implementation Guide

**Recommended order** (foundational → adapter → tests, per `context/architecture.md`):
1. `github/config.py` — `RetryPolicy` + `CollectorConfig` frozen dataclasses (defaults).
2. `github/errors.py` — `CollectorError` hierarchy (token-safe messages).
3. `config.py` — promote `_REPO_RE` to a public `REPO_PATTERN` constant (ADR-006), keep behavior.
4. `github/client.py` — `GitHubCollector`: `__init__` (build httpx client, inject transport/sleep),
   `_validate_repo`, `_classify`, `_request_with_retry`, `_next_link`, `_map_item`, `fetch_items`.
5. `tests/test_github_client.py` — MockTransport-driven tests covering all 27 ACs.

**Patterns to follow:**
- Ports/adapters: implement `osspulse.ports.GitHubClient`; depend only on `osspulse.models`
  + httpx (`context/architecture.md`).
- Frozen dataclasses for config (match `models.py` style).
- httpx auth on the client at construction (`headers=`), TLS `verify=True` (default).
- Error messages: status + repo + static reason only (ADR-004); never f-string the request.
- Reuse `osspulse.config.REPO_PATTERN`; don't redefine.

**Gotchas:**
- Per-item cutoff check, NOT page-level — created-desc is load-bearing but not trusted blindly.
- `Retry-After` overrides the computed backoff but is still capped by `backoff_ceiling_seconds`.
- The 403 split keys ONLY on `X-RateLimit-Remaining: 0` → RETRY; every other 403 → fail fast.
- `item_id = str(number)` — never the GitHub global `id` (cache-key stability, handoff §2).
- Inject `sleep` so retry tests don't actually wait.
- `_map_item` returns `None` when a mandatory field (`number`, `created_at`) is missing →
  skip that item rather than crash (dirty-data tolerance) while still honoring AC-2-016/017.
