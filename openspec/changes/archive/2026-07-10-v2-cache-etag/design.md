## Sketch — Gap Analysis

**No critical gaps found.** All 28 ACs are CONFIRMED, the touch points (`ports.py`,
`cache/etag_store.py` [new], `github/client.py`, `pipeline.py`, `config.py`, `models.py`) are
concrete, and every prior-run pattern this change mirrors already exists in the codebase
(`RedisSummaryCache`+`_NullCache` injection; `JsonFileStateStore.save` atomic write; `_validate_delta`
bool-trap). Cross-referencing the analyst `_handoff.md` §Risky Areas against the existing code
confirms the four risks are design-placement problems, not spec gaps:

- **RISK-001 (crash-safety, MEDIUM)** — the sole load-bearing design decision. The pipeline already
  calls `mark_seen` per-repo *inside* `_collect_all`; `commit()` must land *after* `_collect_all`
  returns in `run_pipeline`, unguarded, so a fatal `AuthError`/`StateError` propagates before it.
  Resolved in **ADR-004**.
- **RISK-002 (stale 304, LOW)** — the `304`=empty-delta soundness rests on the existing
  `sort=created&direction=desc` (issues) / newest-first (`/releases`) queries, which are unchanged.
  First-page-only conditional. Resolved in **ADR-003**.
- **RISK-003 (token leak, LOW)** — reaffirm the existing `_request_with_retry` token discipline; the
  new `etags.json` stores only keys+validators. Resolved in **ADR-002/§Security**.
- **RISK-004 (corrupt cache, LOW)** — `etag_store.py` must **invert** `json_store.py`'s
  raise-on-corrupt. Resolved in **ADR-001**.

Two [ASSUMED] items from S1 are resolved here as design decisions:
- **AC-V2-007-014** (`200` with no `ETag`): the collector calls `set()` only when the header is
  present → "record nothing"; no active clear needed (a stale entry is harmless — see ADR-005).
- **INT-V2-007-005** (no own lock): confirmed — `etag_cache_path` defaults to the same
  `./.osspulse/` dir the v2-002 `fcntl.flock` run-lock protects; the store needs only atomic
  temp+rename for torn-read safety, no cross-process lock.

No new AC-IDs invented. No S2 return required.

---

## Context

`osspulse run` currently issues **unconditional** GitHub REST requests on every run — GitHub re-serves
every issue/release page in full and charges each against the 5000-req/hr rate limit even when nothing
changed. GitHub returns an `ETag` on every REST response, and a `304 Not Modified` reply to a matching
`If-None-Match` request **does not count against the rate limit**. This change is the GitHub-request
half of the V2 caching goal (the LLM/token half is already served by the Redis summary cache).

Current state (verified in-repo):
- `github/client.py` — `_request_with_retry` is the **single** httpx caller (GET for REST, POST for
  GraphQL); `_classify` maps status→`_Action`; `fetch_items`/`fetch_releases` paginate newest-first;
  `fetch_discussions` uses GraphQL. Token set on client headers at ctor, never retained on `self`.
- `pipeline.py` — `_build_cache`/`_NullCache` best-effort Redis pattern; `_collect_all` calls
  `mark_seen` per-repo inside the loop; `run_pipeline` wires adapters as locals.
- `state/json_store.py` — `save()` atomic (`mkstemp(dir=parent)`→`fsync`→`os.replace`); `load()`
  **raises `StateError`** on corruption (the contract we must invert).
- `config.py` — `_validate_delta` bool-trap guard we mirror for `[etag_cache]`.

Constraints: collector stays pure-I/O (living AC-2-015 / BR-2-012 — no State Store import); the frozen
`GitHubClient` Protocol is unchanged; `state.json` `version: 1` schema untouched; no new external
dependency. rigor=lite · scope=standard · test_scope=module · testcase_export=none · STRIDE SKIPPED.

## Goals / Non-Goals

**Goals:**
- A `ConditionalCache` port (`get`/`set`-in-memory/`commit`-durable) + a best-effort corrupt-tolerant
  `JsonFileETagStore` adapter persisting to a **separate** `etags.json` (AC-V2-007-001..008).
- Teach the REST collector paths to send `If-None-Match` on the **first page only**, treat `304` as an
  empty delta, and record the fresh `ETag` on `200` — all via the existing retry path, with a null-cache
  default so a cache miss behaves exactly as today (AC-V2-007-009..018).
- Wire it into the pipeline best-effort, gated by `etag_cache_enabled AND delta_enabled`, committing the
  cache **once after `mark_seen`** for crash-safety (AC-V2-007-019..028).

**Non-Goals:** (from proposal §Non-Goals — reaffirmed)
- No `If-Modified-Since`/`Last-Modified`; no conditional requests on pages 2..N or on GraphQL
  discussions; no merge into `state.json`; no response-body caching; no ETag parsing/normalization; no
  per-endpoint toggle; no new rate-limit budgeting logic.

## Architecture Overview

New capability `conditional-cache` = **1 port + 1 adapter (+ a null no-op)**, injected into the
collector exactly as `SummaryCache` is injected into the Summarizer. Data flow is unchanged; only a
request header (out) and a validator string (persisted) are added.

```
run_pipeline (pipeline.py)
  ├─ _build_etag_cache(config) ──► JsonFileETagStore | _NullConditionalCache   [best-effort]
  │        (gate: etag_cache_enabled AND delta_enabled)
  ├─ GitHubCollector(token, conditional_cache=<above>)   ── port dependency only
  │        fetch_items/fetch_releases:
  │          page1: get("{repo}:{endpoint}") → If-None-Match
  │            304 → return []            (empty delta, no more pages)
  │            200 → set("{repo}:{endpoint}", etag)  [in-memory]  → paginate as today
  │          pages 2..N: unconditional (unchanged)
  │        fetch_discussions: UNCHANGED (GraphQL, no ETag)
  ├─ _collect_all ── per-repo loop ── mark_seen(items)  [durable, inside loop, unchanged]
  └─ conditional_cache.commit()   ◄── EXACTLY ONCE, after loop returns, UNGUARDED   [RISK-001]
```

**Dependency boundaries (verified against living specs):**
- Collector depends on `osspulse.ports.ConditionalCache` + `osspulse.models` + httpx only — never
  imports `JsonFileETagStore` or the State Store (BR-V2-007-007, living AC-2-015).
- `etag_store.py` imports stdlib + `osspulse.ports` only — never `state.json_store` (mirrors the
  boundary discipline of every other adapter).
- `pipeline.py` remains the only cross-stage importer (AC-7-002).
- **Reuse over reinvent** (search-first): the injection pattern, the atomic-write recipe, and the
  bool-trap validator all already exist — this change composes them, adding no new library.

## ADRs

### ADR-001 — `JsonFileETagStore` is best-effort corrupt-tolerant (invert `json_store.py`)

**Context:** `state.json` is **fatal** on corruption because it drives idempotency (a lost seen-record
= a duplicate digest). `etags.json` is a pure rate-limit optimization: losing it only costs one
unconditional refetch, never correctness. The two files must have deliberately **opposite** corruption
semantics (AC-V2-007-004, BR-V2-007-002).

**Options:**

| Option | Pros | Cons |
|---|---|---|
| **A. Best-effort: missing/empty/corrupt/unreadable → empty dict + WARN, never raise** | Matches spec; a corrupt cache never aborts a run; simple `try/except` around load | Diverges from `json_store.load()` — a reader must NOT copy that code |
| B. Reuse `json_store.load()` raise-on-corrupt | Code symmetry with State Store | **Wrong** — a corrupt `etags.json` would abort the run, violating BR-V2-007-002; the exact anti-pattern the handoff warns against |

**Decision:** **Option A.** `load()` catches `(OSError, json.JSONDecodeError)` (and a non-dict root) →
log WARN → return `{}`. `get` on an empty cache returns `None` → unconditional fetch. Never raise.

**Consequences:** A developer must resist "consistency" with `json_store.py`. The unit test asserts a
corrupt file yields `get()→None` + a WARN + **no raise** (AC-V2-007-004b). Documented at the top of
`etag_store.py` as an explicit "opposite of state.json" note.

### ADR-002 — In-memory `set()` + durable `commit()`; `_NullConditionalCache` no-op default

**Context:** Two needs: (1) the collector records ETags during fetch without touching disk per-item
(perf + crash-safety), and (2) callers need no `if cache is not None` null checks (BR-V2-007-008,
AC-V2-007-005/007). Mirrors how `_NullCache` lets the Summarizer treat "no Redis" transparently.

**Options:**

| Option | Pros | Cons |
|---|---|---|
| **A. `set()` mutates an in-memory dict; `commit()` is the sole disk write; a `_NullConditionalCache` no-op satisfies the port** | Enables the crash-safe commit-after-`mark_seen` ordering; no per-item I/O; null object removes branching | Two objects to maintain (store + null) — both tiny |
| B. `set()` writes through to disk immediately | "Simpler" mental model | **Breaks RISK-001** — an ETag persisted before `mark_seen` can strand un-rendered items; also N disk writes per run |
| C. Optional `cache: ConditionalCache | None` + null checks at every call site | No null class | Scatters `if cache:` across collector + pipeline; error-prone |

**Decision:** **Option A.** `set(key, validator)` and `get(key)` operate on `self._cache: dict[str,str]`
in memory; `commit()` does the atomic write of the whole dict. `_NullConditionalCache` (`get`→`None`,
`set`/`commit`→`pass`) is the default collector arg and the disabled/failed-build result.

**Consequences:** Durability is a single explicit pipeline call — which is *precisely* what makes the
crash-safety ordering (ADR-004) expressible. The collector never persists.

### ADR-003 — Conditional on the newest-first FIRST PAGE only; `304` = empty delta; `_classify` maps `304`→OK

**Context:** Sending `If-None-Match` on the wrong page could `304` while new items exist deeper
(RISK-002). Issues are fetched `sort=created&direction=desc` and `/releases` is newest-first, so any
new in-window item appears on page 1 and changes its `ETag` (AC-V2-007-010/011/013).

**Options:**

| Option | Pros | Cons |
|---|---|---|
| **A. `If-None-Match` on page 1 only; first-page `304`→`[]`+stop; pages 2..N unconditional; `_classify(304)`→`_Action.OK`, fetch branches on raw `response.status_code == 304`** | Provably sound against newest-first; reuses `_request_with_retry` verbatim; pages 2..N untouched | Correctness tied to the desc ordering — must stay linked in code comments |
| B. Conditional on every page | "More caching" | **Unsound** — a later page's `304` says nothing about newer items; and multi-page ETag bookkeeping is complex |
| C. New `_classify` action `NOT_MODIFIED` | Explicit | Over-engineered — `304` needs no retry/skip behavior; OK + a raw-status branch is enough (v2-006 lesson: branch on shape/status, not a new enum) |

**Decision:** **Option A.** Add `if status == 304: return _Action.OK` to `_classify`. In
`fetch_items`/`fetch_releases`, compute the endpoint's page-1 conditional header from
`conditional_cache.get(f"{repo}:{endpoint}")`; after the page-1 response, branch: `304` → `return []`;
`200` → `set(...)` if `ETag` present, then continue the existing pagination loop. A one-shot boolean
(`first_page`) ensures only page 1 carries the header.

**Consequences:** The desc-ordering invariant is load-bearing; a code comment links the conditional to
`sort=created&direction=desc`. `_classify` returning OK for both `200` and `304` means the fetch method
**must** distinguish them on the raw status, not on the `_Action` (handoff §4 tripwire).

### ADR-004 — `commit()` exactly once, after `_collect_all`, UNGUARDED (crash-safety)

**Context:** The single highest-risk decision (RISK-001). Persisting an ETag for items fetched but not
yet `mark_seen`-recorded would make the next run `304`-skip un-rendered items — silent data loss,
violating the "idempotent, never lose an item" non-negotiable (AC-V2-007-024/025). `_collect_all`
already calls `mark_seen` per-repo *inside* its loop.

**Options:**

| Option | Pros | Cons |
|---|---|---|
| **A. `run_pipeline` calls `conditional_cache.commit()` once, right after `_collect_all(...)` returns, with NO surrounding try/except** | An `AuthError`/`StateError`/crash during collection propagates *before* the commit line → `etags.json` unchanged → next run re-fetches; matches AC-V2-007-024/025 exactly | Relies on placement discipline — a future edit that wraps it or moves it earlier reintroduces the bug |
| B. Collector commits on each `200` | Local | **Breaks crash-safety** — persists before `mark_seen`; also per-item I/O |
| C. Per-repo `commit()` mid-loop | "Incremental durability" | Persists a repo's ETag after *its* `mark_seen` but a later fatal repo can't undo it — acceptable per-repo, but the spec pins a single post-loop commit and a mid-loop commit muddies the "unchanged on abort" guarantee for the whole run |

**Decision:** **Option A.** In `run_pipeline`:
```
all_items, stats = _collect_all(config, collector, state)   # mark_seen happens inside, per repo
conditional_cache.commit()                                   # once, unguarded — AFTER the loop
```
A fatal `AuthError` re-raised by `_collect_all` (AC-7-005) or a `StateError` from `mark_seen`
(AC-V2-001-009) propagates out of `run_pipeline` *before* `commit()` runs. A terminal `RateLimitError`
is caught *inside* `_collect_all` (it `break`s and returns partial results, AC-7-017), so `commit()`
*does* run for the repos that completed — correct, because those repos' items were `mark_seen`-recorded.

**Consequences:** `commit()` must NOT be wrapped in a broad `try/except` (would hide a `StateError`);
must NOT move earlier or per-repo. A pipeline test asserts `commit()` is called exactly once after the
loop, and **not** called when a fatal `AuthError` fires mid-loop (AC-V2-007-024/025). A code comment
marks the line as crash-safety-critical.

### ADR-005 — `set()` only on a present `ETag`; no active stale-clear (AC-V2-007-014)

**Context:** A `200` may omit the `ETag` header (proxies, edge cases). S1 left "record nothing / clear
stale" as [ASSUMED].

**Decision (scope allows a single reasonable approach — options condensed):** The collector calls
`set(key, etag)` **only when** `response.headers.get("ETag")` is present; when absent it does nothing.
A pre-existing stale entry is left in place — harmless: the next run would send it, and since the
resource evidently changed enough for GitHub to drop/alter the validator, a stale `If-None-Match`
simply yields a fresh `200`. Actively deleting the key adds code for no correctness gain. Rejected:
`set(key, "")` (an empty validator would send a malformed `If-None-Match:`).

**Consequences:** "record nothing, no crash" (AC-V2-007-014) is satisfied by the simple present-guard.
Test: `200` with no `ETag` → `set` not called, items returned normally, no raise.

## API Design

N/A — OSS Pulse is a CLI tool with **no HTTP API surface** (per `context/conventions.md`). No
`openapi.yaml` is produced for this change (R5 applies only when the change exposes an API). The
relevant contracts are the internal **port** signature and the **outbound** GitHub request header:

- **Port (new, `osspulse.ports.ConditionalCache`)** — `get(key: str) -> str | None`,
  `set(key: str, validator: str) -> None`, `commit() -> None`. Key = `"{repo}:{endpoint}"`,
  `endpoint ∈ {issues, releases}`.
- **Outbound request** — first page of a REST endpoint, when a validator is cached:
  `If-None-Match: <validator>` (verbatim; strong `"..."` or weak `W/"..."`). Reuses the existing
  authed httpx client, GET-only, TLS on. GraphQL POST is never conditional.
- **Config surface** — `[etag_cache] enabled` (bool, default `true`), `path`
  (str, default `./.osspulse/etags.json`). Non-boolean `enabled` → `ConfigError` at load.

## Data Schema

No database (V1/V2 are file-based). One new **on-disk file**, independent of `state.json`:

**`etags.json`** (default `./.osspulse/etags.json`) — a flat JSON object mapping the compound key to
the opaque validator string:
```json
{
  "owner/name:issues":   "\"abc123\"",
  "owner/name:releases": "W/\"def456\""
}
```
- Keys: `"{repo}:{endpoint}"` only. Values: opaque validator strings only. **Never** the token, a
  response body, or PII (BR-V2-007-001, AC-V2-007-006).
- No `version` field (deliberately schema-light — best-effort, so a future shape change just resets to
  empty rather than gating on a version like `state.json` does).
- `Config` (`models.py`) gains `etag_cache_enabled: bool = True` and
  `etag_cache_path: str = "./.osspulse/etags.json"`.

## Error Mapping

| Situation | Handling | AC |
|---|---|---|
| `etags.json` missing / empty / whitespace | Empty cache, no WARN needed for missing (normal first run); empty→`{}` | AC-V2-007-004a |
| `etags.json` corrupt / unreadable | WARN, treat as empty, **never raise** (invert State Store) | AC-V2-007-004b, AC-V2-007-028 |
| `commit()` write fails (OSError) | Best-effort — log WARN, swallow; the run already succeeded (optimization only). Temp file cleaned up | BR-V2-007-002 |
| First-page `304` | `_classify`→OK; fetch returns `[]` for that endpoint, no further pages, stored ETag unchanged | AC-V2-007-011 |
| First-page `200`, `ETag` present | `set(key, etag)` in-memory; paginate as today | AC-V2-007-012 |
| First-page `200`, no `ETag` header | Record nothing (no `set`); return items; no crash | AC-V2-007-014 |
| Conditional request `429`/`5xx`/secondary-rate-limit | Existing `_request_with_retry` backoff/retry — unchanged | AC-V2-007-016, BR-V2-007-011 |
| Conditional request non-rate-limit `401`/`403` | `AuthError` fail-fast — unchanged | AC-V2-007-016 |
| `404`/`410` on first page (repo gone) | Existing SKIP_REPO → WARN + `[]`; stored ETag irrelevant | (living AC-2-011) |
| `[etag_cache] enabled` non-boolean | `ConfigError` at load, before the pipeline runs | AC-V2-007-021 |
| `JsonFileETagStore` build fails | `_build_etag_cache` returns `_NullConditionalCache`; run continues unconditional | AC-V2-007-019 |

No new error class is introduced (no `ETagError` — best-effort means failures are swallowed, not
raised). This is intentional and the inverse of `StateError`.

## Sequence Flows

**Flow 1 — second run, endpoint unchanged (the money path, AC-V2-007-026):**
```
run_pipeline → _build_etag_cache → JsonFileETagStore (loads etags.json: {"r:issues":"E1"})
_collect_all → repo r:
  fetch_items: page1 get("r:issues")="E1" → GET issues?…desc  If-None-Match: E1
    → 304 → return []            (0 rate-limit budget, no ETag change)
  fetch_releases: similar → 304 → []
  items=[] → _partition_new=[] → mark_seen([]) (no-op)
loop ends → commit()  (etags.json rewritten identically)
render([]) → "no new items in the last N days" doc → deliver → exit 0
```

**Flow 2 — second run, a new issue appeared (AC-V2-007-027):**
```
fetch_items: page1 If-None-Match: E1 → 200 ETag: E2 (+ new issue on page 1)
  → set("r:issues","E2")  [in-memory] → paginate desc as today, cutoff early-stop
items=[new issue, …seen…] → _partition_new → only the new one is `new`
mark_seen(all fetched) → loop ends → commit()  (etags.json now has E2)
render([new issue]) → deliver → exit 0
```

**Flow 3 — crash-safety abort (RISK-001, AC-V2-007-025):**
```
_collect_all: repo A → 200, set("A:issues","Ea"), mark_seen(A items) OK
              repo B → AuthError (shared token revoked) → re-raise
run_pipeline: exception propagates BEFORE commit() → etags.json UNCHANGED on disk
next run: A:issues has NO committed Ea → unconditional (or prior) fetch → A items re-collected
          → no item skipped before it was recorded seen
```

## Edge Cases

Enumerated in proposal §Edge Cases (1–17). Design-relevant resolutions:
- **EC multi-endpoint (7)** — `issues` and `releases` keyed independently; one `304` + one `200` for
  the same repo behave independently. ✔ separate keys.
- **EC GraphQL (8)** — `fetch_discussions` untouched; never reads/writes the cache. ✔ ADR-003 scope.
- **EC weak ETag (6)** — echoed verbatim; no parsing. ✔ ADR-003.
- **EC `200` no-ETag (5)** — present-guard on `set`. ✔ ADR-005.
- **EC corrupt cache (4)** — WARN + empty + continue. ✔ ADR-001.
- **EC crash before commit (12)** — unguarded post-loop commit. ✔ ADR-004.
- **EC both-flag gate (13,14)** — `_build_etag_cache` returns null cache unless
  `etag_cache_enabled AND delta_enabled`; a null cache never sends a header and its `commit()` is a
  no-op, so `etags.json` is untouched. ✔ AC-V2-007-023.
- **EC concurrency (11)** — v2-002 run-lock serializes; atomic temp+rename gives torn-read safety. ✔

## Performance

- A run over an unchanged watchlist trends toward **~0 rate-limit budget** — every REST first page
  answers `304` (free) and no later pages are fetched (AC-V2-007-026). This is the whole point.
- `set()` is O(1) in-memory; `commit()` is a single atomic write of a small dict (one entry per
  repo×endpoint — bytes, not the item bodies). No per-item disk I/O.
- No added latency on the hot path beyond one request header. GraphQL discussions unchanged.
- No new memory pressure — the cache dict holds at most `2 × len(watched_repos)` short strings.

## Security

STRIDE **SKIPPED** (proposal §Early Risk Flags — no new secret/PII/auth/upload/admin surface; reuses
the same authenticated `GITHUB_TOKEN` on the same TLS-on httpx client, adds one request header).
Reaffirmed invariants:

- **Token discipline (RISK-003, AC-V2-007-006/018)** — `etags.json` contains only keys + opaque
  validators. The token is set on the httpx client headers at ctor and never retained; the conditional
  header is `If-None-Match: <validator>` (no token). Error messages on the conditional path reuse the
  existing status+repo+static-reason composition — never `str(exc)`, never the token/URL
  (github-collector-2 ADR-004, and the v2-005 memory lesson). A test asserts a token sentinel never
  appears in `etags.json`, any log line, or any error across the conditional path.
- **No body persisted** — only validator strings; response bodies never touch `etags.json`.
- **TLS on, GET-only for REST, `base_url` from config only** — unchanged (living AC-2-013/025).

## Risk Assessment

| Risk | Severity | Mitigation | ADR / AC |
|---|---|---|---|
| RISK-001 lost-item on crash | MEDIUM | in-memory `set()` + single unguarded post-`mark_seen` `commit()` | ADR-004 / AC-V2-007-024/025 |
| RISK-002 stale `304` masks new items | LOW | first-page-only conditional against newest-first desc query | ADR-003 / AC-V2-007-010/011/013 |
| RISK-003 token/body leak into `etags.json`/logs | LOW | keys+validators only; reuse token discipline; sentinel test | §Security / AC-V2-007-006/018 |
| RISK-004 corrupt `etags.json` aborts run | LOW | best-effort empty+WARN, never raise (invert State Store) | ADR-001 / AC-V2-007-004/028 |
| Regression: null-cache changes today's behavior | LOW | `_NullConditionalCache` default; regression test vs current collector | ADR-002 / AC-V2-007-009 |
| Future edit re-orders/guards `commit()` | MEDIUM | code comment marking crash-safety; explicit pipeline test | ADR-004 |

## Implementation Guide

**Recommended order** (data → adapter → orchestration → tests, per `context/architecture.md` layering;
matches tasks.md §1→§6):

1. **Port** (`ports.py`) — add `ConditionalCache` Protocol. Do **not** touch `GitHubClient`.
2. **Adapter** (`cache/etag_store.py`, new) — `JsonFileETagStore` (best-effort load, in-memory
   `get`/`set`, atomic `commit`) + `_NullConditionalCache`. **Mirror** `json_store.save()` for the
   atomic write; **invert** `json_store.load()` for corruption (ADR-001).
3. **CHECKPOINT** — store unit tests (best-effort/atomic/never-touches-state.json).
4. **Collector** (`github/client.py`) — ctor arg `conditional_cache=_NullConditionalCache()`;
   `_request_with_retry(..., *, extra_headers=None)`; `_classify(304)→OK`; page-1 conditional +
   `304`/`200` branch in `fetch_items`/`fetch_releases`; confirm `fetch_discussions` untouched.
5. **CHECKPOINT** — collector unit tests (MockTransport + fake cache).
6. **Config** (`config.py` + `models.py`) — parse/validate `[etag_cache]`; add two `Config` fields.
7. **Pipeline** (`pipeline.py`) — `_build_etag_cache` (best-effort + two-flag gate); inject into
   collector; `commit()` once, unguarded, after `_collect_all`.
8. **CHECKPOINT (final)** — config+pipeline+e2e tests, coverage ≥80%, ruff, secret-scan.

**Patterns to follow (with file paths):**
- Atomic write → copy `src/osspulse/state/json_store.py` `save()` (`mkstemp(dir=self._path.parent)`
  → `os.fdopen` → `json.dump` → `flush` → `os.fsync` → `os.replace`; `finally` unlink orphan temp).
- Best-effort build + null object → mirror `src/osspulse/pipeline.py` `_build_cache` / `_NullCache`.
- Bool-trap config validation → mirror `src/osspulse/config.py` `_validate_delta`
  (`type(value) is not bool`, **not** `isinstance` — `isinstance(True,int)` is `True`).
- Single retry caller → extend `src/osspulse/github/client.py` `_request_with_retry` with
  `extra_headers` (pass `headers=` to the `get` call); do **not** add a second call site.
- Token-safe errors → reuse the existing status+repo+static-reason message composition; never
  `str(exc)`.

**Gotchas:**
- ⚠️ **`commit()` placement is crash-safety-critical (ADR-004)** — after `_collect_all` returns,
  unguarded. Do NOT wrap in try/except; do NOT move earlier or per-repo. This is the #1 review item.
- ⚠️ **Invert, don't copy, `json_store.load()`** — a corrupt `etags.json` must WARN+empty, never raise.
- ⚠️ **Branch on raw `status_code == 304`**, not on `_Action` (both `200` and `304` map to OK).
- ⚠️ **First page only** — a `first_page` boolean gates the conditional header; pages 2..N unconditional.
- ⚠️ **Newest-first is load-bearing** — keep the conditional linked to `sort=created&direction=desc`;
  do not reorder the issues query.
- ⚠️ **Collector imports the port only** — never `JsonFileETagStore` or the State Store.
