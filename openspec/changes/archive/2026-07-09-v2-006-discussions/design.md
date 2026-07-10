## Sketch — Gap Analysis

**No critical gaps found.** The change is fully satisfiable against the existing codebase. The
work concentrates in one adapter method (`fetch_discussions`) + one private mapper (`_map_discussion`)
+ a small GraphQL POST/paginate/classify helper, plus one pipeline wiring call — mirroring
v2-003-releases, but over a **new GraphQL transport** (POST, cursor pagination, 200-with-errors).

Codebase grounding (read at sketch):
- `src/osspulse/github/client.py` — `fetch_items`/`fetch_releases` + `_map_item`/`_map_release` are
  the mirrors for the new `fetch_discussions` + `_map_discussion`. Reusable as-is: `_validate_repo`,
  `_backoff_seconds`, `_parse_created`, the `_Action` classification enum, the `RetryPolicy`. The
  retry loop `_request_with_retry` is **GET-only** and must be generalized to also issue a POST
  without regressing the REST paths (ADR-002).
- `src/osspulse/pipeline.py` — `_collect_all` per-repo `try/except` is the wiring site; the v2-001
  **R1 partition-before-mark_seen** invariant and the v2-003 **inner-guard** pattern (wrap only the
  new fetch, one partition + one mark_seen) both live here and MUST be preserved.
- `src/osspulse/render/renderer.py` — `GROUP_ORDER = ["issue","discussion","release"]` with
  `GROUP_LABELS["discussion"] = "Discussion"` (confirmed); **no renderer delta** (BR-V2-006-004).
- `src/osspulse/github/config.py` — `CollectorConfig` (`max_items_per_repo`, `page_size`, `base_url`,
  `retry`) reused with **no new field** (BR-V2-006-003).
- `src/osspulse/github/errors.py` — `CollectorError` hierarchy reused; the payload-classification
  step raises the **existing** `RateLimitError`/`CollectorError` — no new error class.
- `src/osspulse/ports.py` — `GitHubClient` Protocol declares only `fetch_items`; stays **frozen**
  (`fetch_discussions` is adapter-only, AC-V2-006-018).
- `src/osspulse/models.py` — `RawItem.item_type` doc already lists `"discussion"`; no model change.

Non-gaps explicitly classified (per governance conflict handling):
- **RISK-003 (200-with-errors)** is a *design decision* (ADR-003 below), not a spec ambiguity.
  AC-V2-006-003 / AC-V2-006-014 are CONFIRMED and mandate the 3-way outcome; the classification
  algorithm is resolved here.
- **`body` vs `bodyText`** (handoff §3 watch item) is resolved in ADR-004 (pick `body` — markdown).
- **Disabled-Discussions null-shape** (handoff §2 watch item) — the *detection key* is designed
  defensively in ADR-003 (null `repository` OR null `discussions`, guarded so either shape skips
  gracefully; classification does NOT hardcode an assumed `errors[].type` string).
- **No `openapi.yaml`** — OSS Pulse is a CLI tool with **no HTTP API** (internal stage contracts are
  Python dataclasses). Every prior change ships no `openapi.yaml`. The design-rule "keep a SEPARATE
  openapi.yaml" is conditional ("*if the change has an API*") — documented non-deviation in
  §Architecture Overview and ADR-005, not a gap.

---

## Context

The V1+V2 pipeline (`osspulse run`) collects, summarizes, renders, and delivers new **issues** and
**releases** per watched repo. This change adds **discussions** as a first-class source
(PROJECT_SPEC §5 / V2) so the digest shows "what the community is debating" alongside issues and
releases — the "understanding over speed" principle.

The pipeline downstream of the collector was deliberately built **item-type-agnostic** (same premise
as v2-003):
- State store keys on `repo + item_type + item_id` — accepts `"discussion"` unchanged.
- The v2-001 delta filter (`_partition_new` in `pipeline.py`) filters any `item_type`.
- The summarizer caps input at 8000 chars (`input_char_cap`) — long discussion bodies handled.
- The renderer already ships `"discussion"` in `GROUP_ORDER` with the `Discussion` label.

So the delta is: teach the **Collector** to fetch + map GitHub discussions, and wire **one extra
call** into `pipeline._collect_all`. All downstream artifacts are reused unchanged.

**The one thing genuinely new** (vs the REST issue/release paths): GitHub Discussions are available
**only** through the **GraphQL API** — a single `POST .../graphql` with a query+variables body,
**cursor-based** pagination (not the REST `Link` header), and a **`200 OK` that can carry an
`errors` array** (e.g. `repository.discussions == null` when Discussions are disabled). This breaks
three assumptions baked into the existing collector — GET-only, `Link`-header pagination, and
"non-200 == failure" — which must be handled without regressing the issue/release paths.

Constraints (from `context/architecture.md`, prior ADRs, and architect memory):
- `GitHubClient` Protocol is **frozen** — the new fetch method goes on the adapter only
  (summarizer-llm-4 ADR-005 / v2-003 ADR-002 discipline).
- **No new `Config`/`CollectorConfig` field** — reuse existing tunables (v2-003 discipline).
- `pipeline.py` is the **only** cross-stage importer (AC-7-002); no stage imports another.
- The v2-001 **R1 invariant**: partition new items BEFORE `mark_seen`; `mark_seen` always records
  the FULL fetched list, never just `new`.
- Per-module one-error-class convention: the collector's `CollectorError` hierarchy is reused;
  **no new error class**.
- v2-003 memory lesson: "add a second fetch to an isolated per-repo loop → wrap ONLY the new fetch,
  keep one partition + one mark_seen"; "inner-guard specs must explicitly exclude fatal subclasses
  (AuthError ⊂ CollectorError)".

## Goals / Non-Goals

**Goals:**
- Add `GitHubCollector.fetch_discussions(repo, lookback_days) -> list[RawItem]` (adapter-only) that
  issues a fixed GraphQL `POST` query ordered `CREATED_AT DESC`, cursor-paginates, and maps each
  discussion to a `RawItem` with `item_type="discussion"`.
- Map discussion JSON → `RawItem`, null-safe on every field; skip nodes missing `number`.
- Generalize the transport helper to issue a POST with a JSON body **without** regressing the
  REST GET-only invariant, reusing the retry/backoff/auth/security machinery unchanged.
- Classify the GraphQL **payload** (200-with-errors) into the 3 outcomes: map / skip-repo / raise.
- Wire discussions into `pipeline._collect_all` under the SAME per-repo isolation boundary as
  releases, preserving the R1 partition-before-mark_seen invariant.

**Non-Goals:**
- No digest-renderer delta (BR-V2-006-004 — already discussion-ready).
- No `openapi.yaml` (no HTTP API — CLI tool; ADR-005).
- No new `Config`/`CollectorConfig` field, no per-source enable/disable toggle (BR-V2-006-008).
- No `GitHubClient` Protocol change (AC-V2-006-018).
- No hotness/activity ranking (Approach A only — created-within-window).
- No comment/thread collection, no category filtering, no general-purpose GraphQL client.
- No new error class — discussions reuse the `CollectorError` hierarchy.
- No new summarization behavior — discussions summarize like issues/releases (8000-char cap).

## Architecture Overview

**Layer touched:** the GitHub Collector adapter (`src/osspulse/github/`) + the pipeline orchestrator
(`src/osspulse/pipeline.py`). No new module, no new port, no new stage, no new error class.

```
run_pipeline
  └─ _collect_all(config, collector, state)              # pipeline.py — wiring site
       for repo in watched_repos:
         try:
           issues   = collector.fetch_items(repo, lookback_days)        # existing (REST GET)
           releases = <inner guard> collector.fetch_releases(...)       # v2-003 (REST GET)
           discussions = <inner guard> collector.fetch_discussions(...) # NEW (GraphQL POST)
           items    = issues + releases + discussions                   # concatenate (AC-019)
           new, seen = _partition_new(items, state)   # R1: BEFORE mark_seen (AC-022 safe)
           state.mark_seen(items)                      # full list, never `new`
           all_items.extend(new if delta_enabled else items)
         except AuthError:        raise               # fatal (AC-7-005)
         except RateLimitError:   break               # partial deliver (AC-7-017)
         except (InvalidRepoError, NetworkError, CollectorError): skip repo (AC-7-004 / AC-022)
```

**Reused (no change):**
- State store `is_seen`/`mark_seen` (`repo + "discussion" + number`) — INT-V2-006-003.
- v2-001 delta filter `_partition_new` — item_type-agnostic (AC-V2-006-020).
- Summarizer `summarize_items` (8000-char cap covers long bodies) — INT-V2-006-004.
- Renderer `### Discussion (N)` group — AC-V2-006-021.

**Dependencies (from prior changes):** `RawItem` (models), `CollectorConfig` (github-collector-2),
`_partition_new` + R1 invariant (v2-001), the v2-003 inner-guard pattern (`_collect_all`),
`GROUP_ORDER` (digest-renderer-5).

**Transport reuse note:** `fetch_discussions` shares the **one** `httpx.Client` instance (held on
`self._client`) and therefore the **one** retry budget per collector — the pipeline constructs a
single `GitHubCollector` per run. The Authorization header, Accept, and API-version headers are
already set on that client at construction; the GraphQL POST reuses them unchanged (token discipline
preserved). The GraphQL endpoint URL is `{base_url}/graphql`, derived only from config `base_url`
(never from `repo` or response data).

**API surface:** none. OSS Pulse is a CLI tool; internal contracts are Python dataclasses. No
`openapi.yaml` is produced (ADR-005). The only external HTTP is the outbound GitHub GraphQL call,
which is not an API this project *exposes*.

## ADRs

### ADR-001 — Cursor pagination with `CREATED_AT DESC` early-stop

**Context.** Discussions are fetched newest-first (`orderBy: {field: CREATED_AT, direction: DESC}`,
AC-V2-006-012 CONFIRMED). Inclusion is by `createdAt` within the lookback window (Approach A,
AC-V2-006-002). GraphQL paginates by connection cursor (`pageInfo.hasNextPage` / `pageInfo.endCursor`,
AC-V2-006-011), NOT the REST `Link` header. Crucially — unlike v2-003 releases, where the sort key
(`created_at`) differed from the inclusion key (`published_at`) and produced the RISK-002 skew — here
**inclusion and ordering key on the same field** (`createdAt`), so the per-item early-stop is exact:
once a discussion with `createdAt < cutoff` is seen, every later one is older too.

**Options.**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Cursor loop, early-stop on first out-of-window `createdAt`, bounded by `max_items_per_repo`** (chosen) | Request `first: page_size` after `endCursor`; per item include when `createdAt >= cutoff`, else STOP and request no further page; cap at `max_items_per_repo` with an info truncation log | Exact (same field for order+include, no skew); mirrors `fetch_items` control-flow one-to-one; bounded pages; reuses config tunables | Requires a GraphQL cursor loop distinct from `_next_link` (new small helper) |
| **B. Fetch all pages, filter by `createdAt`, bound only by `max_items_per_repo`** | No early-stop | Simpler loop condition | Contradicts the CONFIRMED early-stop intent (AC-V2-006-012); unbounded page walks on active repos → wasted GraphQL points (RISK-004) |
| **C. Page-level stop (stop after a page whose last item is out-of-window)** | Coarser | Fewer comparisons | Over-fetches up to a full page past the cutoff; AC-V2-006-012 asks for per-item stop ("stops after detecting the first out-of-window discussion") |

**Decision.** **Option A** — per-item early-stop on `createdAt` under a cursor loop, bounded by
`max_items_per_repo`. Because order and inclusion share `createdAt`, there is no ordering-vs-inclusion
skew (the v2-003 RISK-002 trap does not recur — this is simpler than releases). The loop mirrors
`fetch_items`: iterate nodes, stop on the first `createdAt < cutoff`, `continue`-append otherwise,
cap with a truncation log.

**Consequences.** A new tiny cursor-advance is needed (`endCursor`/`hasNextPage`) in place of
`_next_link` — it lives inside `fetch_discussions`. `page_size` maps to the GraphQL `first:` argument
and `max_items_per_repo` caps the accumulated list. Tests assert: in-window included, out-of-window
early-stop mid-pagination, and truncation at the cap.

### ADR-002 — POST transport: generalize `_request_with_retry` without regressing GET-only

**Context.** `_request_with_retry` is the ONLY httpx caller and currently issues `self._client.get(url)`.
GraphQL needs a `POST {base_url}/graphql` with a JSON `{query, variables}` body. The existing REST
paths (issues, releases) MUST remain GET-only (the security invariant "only GET is issued", AC-2-013),
while the GraphQL path issues exactly one fixed non-mutating POST (BR-V2-006-006, BR-V2-006-010). The
retry/backoff/auth classification (`_classify`, `_backoff_seconds`) must be identical on both.

**Options.**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Parameterize `_request_with_retry` with an optional `json_body`; GET when None, POST when provided** (chosen) | `def _request_with_retry(self, url, repo, *, json_body=None)`; `if json_body is None: client.get(url) else: client.post(url, json=json_body)` | One retry loop, one classification path, one token discipline — no duplicated backoff logic (BR-V2-006-010); REST callers unchanged (default `None` = GET); minimal diff | The single method now knows two verbs (documented; guarded by the default) |
| **B. Add a parallel `_post_with_retry`** | Separate method | Clear GET/POST split | Duplicates the entire retry/backoff/classify loop → two places to keep in sync (the exact anti-pattern BR-V2-006-010 forbids: "reuse transport classification unchanged") |
| **C. Pass a full `httpx.Request` object into a verb-agnostic sender** | Most general | Over-engineered for one fixed POST; invites arbitrary requests (weakens the fixed-query invariant) | Larger surface, harder to assert "only GET on REST, one fixed POST on GraphQL" |

**Decision.** **Option A** — add a keyword-only `json_body: dict | None = None` parameter.
`json_body is None` → `client.get(url)` (every existing REST caller, unchanged behavior);
`json_body is not None` → `client.post(url, json=json_body)` (the GraphQL path only). The retry loop,
`_classify`, `_backoff_seconds`, and error messages are shared verbatim — the transport-level
HTTP classification (429/5xx/secondary-rate-limit → retry; 401/non-rate-limit 403 → fail fast) is
reused unchanged (BR-V2-006-010, AC-V2-006-015).

**Consequences.** The GET-only invariant is now scoped precisely: REST callers pass no body (GET);
the sole POST is the fixed GraphQL query. A test asserts the REST paths still issue GET (no body) and
the discussion path issues exactly one POST to `/graphql` with a `query` (never a `mutation`)
—AC-V2-006-016. `_classify` on a POST response works identically (status-based). Token stays on the
client headers, never in the body or a log (RISK-001).

### ADR-003 — GraphQL 200-with-errors: 3-way payload classification (RISK-003)

**Context.** A GraphQL `200 OK` can carry a top-level `errors` array and/or a `null` connection. Three
outcomes must be distinguished from ONE 200 (AC-V2-006-003 / AC-V2-006-014, BR-V2-006-007):
(a) `data.repository.discussions` present → **map** the nodes;
(b) repo not found / Discussions disabled (`data.repository == null` OR `data.repository.discussions == null`)
→ **skip repo** (WARN + empty list, run continues);
(c) any other top-level `errors` (e.g. malformed query, `RATE_LIMITED`) → **raise** a clear error.
Treating every 200 as success (the REST assumption) would either crash on a `null` deref or silently
drop a repo/real error. The handoff (§2/§4) flags this as the hardest correctness area and warns:
do NOT hardcode an assumed `errors[].type` string — key on the response *shape* (the null connection),
which is robust regardless of GitHub's exact error message wording.

**Options.**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Shape-first classification: check `data.repository`/`.discussions` for null → skip; else if top-level `errors` present → raise; else map** (chosen) | Parse JSON; `repo_node = data.get("repository")`; if `repo_node is None` or `repo_node.get("discussions") is None` → WARN + return `[]`; elif payload has non-empty `errors` → raise `CollectorError`; else map nodes | Robust to GitHub's exact error wording (keys on shape, not a string — per handoff warning); the null-connection case is unambiguous; no crash path | Must order the checks correctly (null-shape BEFORE the generic errors-raise, since a disabled repo carries BOTH a null connection AND an errors entry) |
| **B. Match `errors[].type == "..."` string for the disabled case** | String-match the error type | Explicit | Brittle — hardcodes an assumed GitHub error string (exactly what the handoff warns against); a wording change silently reclassifies disabled→raise |
| **C. Treat any `errors` present as skip-repo** | Coarse | Simple | WRONG — silently drops a real `RATE_LIMITED`/malformed-query error as an empty list (violates AC-V2-006-014) |

**Decision.** **Option A** — shape-first, ordered classification in a small `_classify_graphql(payload, repo)`
helper (or inline in `fetch_discussions`):
1. Read `data = payload.get("data") or {}`; `repo_node = data.get("repository")`.
2. **skip-repo** if `repo_node is None` OR `repo_node.get("discussions") is None` → WARN + return `[]`
   (AC-V2-006-003). This is checked FIRST so a disabled repo (null connection + a matching errors
   entry) is skipped, not raised.
3. **raise** if `payload.get("errors")` is a non-empty list (and step 2 did not fire) → clear
   `CollectorError` with a static message (no token) (AC-V2-006-014).
4. **map** otherwise: `repo_node["discussions"]["nodes"]` + `pageInfo`.

The check order (null-shape → errors-raise → map) is load-bearing: it is the single point where
RISK-003's three outcomes diverge. A disabled repo is detected by the null connection SHAPE, never by
a hardcoded error-type string.

**Consequences.** Three explicit tests (AC-V2-006-003 disabled→skip, AC-V2-006-004 enabled-empty→[],
AC-V2-006-014 other-errors→raise) pin all three outcomes. The raise reuses an existing `CollectorError`
subclass — a `RATE_LIMITED` GraphQL error maps to `RateLimitError` (so the pipeline's partial-deliver
arm handles it consistently), a malformed-query/other error maps to `CollectorError` (recoverable →
skip that repo at the pipeline). No new error class. The skip-repo path emits the same user-visible
outcome as a REST 404 (WARN + empty list).

### ADR-004 — `body` (markdown) not `bodyText`; identity = discussion `number`

**Context.** The GraphQL `Discussion` type exposes both `body` (raw markdown) and `bodyText` (plain
text). The summarizer and renderer treat item bodies as markdown (issues/releases store the markdown
body). The handoff §3 flags "pick the markdown body". Identity: AC-V2-006-005 (CONFIRMED) mandates
`item_id = number` (stringified), not the opaque GraphQL global node `id`.

**Options.** Only one approach is genuinely consistent with the existing issue/release mapping, so per
R8's scope exception this ADR states the decision with a one-line rationale rather than a full options
table — the alternatives are recorded inline.

**Decision.** Query and map `body` (markdown), coerced to `""` when null — consistent with the issue
`body` and release `body` mapping (`raw.get("body") or ""`); `bodyText` is rejected because it would
strip markdown the summarizer/renderer expect. `item_id = str(number)` — rejected alternative: the
global node `id` (renders as an ugly `#D_kwDO...`; AC-V2-006-005 locks `number` → renders `#42`).

**Consequences.** `_map_discussion` mirrors `_map_item`: `item_id=str(number)`, `title=title or ""`,
`body=body or ""`, `url=url or ""`, `created_at=createdAt` (raw ISO string, never reformatted). A node
missing `number` returns `None` (skip) — cannot be keyed (AC-V2-006-010). The GraphQL query selects
`number title body url createdAt` on each node.

### ADR-005 — No `openapi.yaml` for a CLI-only change

**Context.** The architect S3 rules / R5 say "keep a SEPARATE openapi.yaml … *if the change has an
API*". OSS Pulse exposes **no HTTP API**; internal stage contracts are Python dataclasses. This
mirrors v2-003 ADR-004 exactly.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| **A. Produce no `openapi.yaml`; document the internal `fetch_discussions` contract in §API Design** (chosen) | Truthful — no HTTP surface; consistent with all prior changes (none ship openapi.yaml); avoids a misleading artifact | R5 mentions openapi.yaml (but conditionally) |
| **B. Author an openapi.yaml describing the outbound GitHub GraphQL call** | Satisfies R5 literally | Misrepresents an *outbound consumed* API as an API this project *exposes*; no consumer; pure ceremony |

**Decision.** **Option A.** The conditional in R5 ("if the change has an API") is not met. §API Design
documents the internal Python method contract (signature, GraphQL query, mapping, errors) instead. A
documented, rule-cited non-deviation, not an omission.

**Consequences.** The DESIGN REVIEW cross-artifact-audit runs over spec deltas + design.md + tasks.md
(no openapi.yaml row). `openspec change validate` does not require openapi.yaml.

## API Design

No HTTP API. The change adds one **internal adapter method**, one **private mapper**, one **private
payload classifier**, and generalizes one existing helper:

```python
# src/osspulse/github/client.py  (on GitHubCollector)

def fetch_discussions(self, repo: str, lookback_days: int) -> list[RawItem]:
    """Fetch discussions created within the last `lookback_days` for `repo`, via GraphQL.

    Pure I/O. Issues a fixed non-mutating GraphQL POST to {base_url}/graphql ordered
    CREATED_AT DESC; cursor-paginates (pageInfo.hasNextPage/endCursor); early-stops
    per-item when createdAt < cutoff (ADR-001); caps at max_items_per_repo with an info
    truncation log. Classifies the 200 payload (ADR-003): disabled/not-found → WARN + [];
    other top-level errors → raise; else map. Reuses the same authed client, retry policy,
    and CollectorError hierarchy as fetch_items.
    """

def _map_discussion(self, node: dict, repo: str) -> RawItem | None:
    """Map a GraphQL discussion node to RawItem; guard every field.

    Returns None (skip) when `number` is missing (cannot key). item_id=str(number);
    title=title or ""; body=body or ""; url=url or ""; created_at=createdAt (raw ISO,
    unchanged).
    """

def _classify_graphql(self, payload: dict, repo: str) -> _GraphQLAction | list[dict]:
    """Classify a GraphQL 200 payload (ADR-003), shape-first ordered:
    null repository/discussions → SKIP_REPO; else non-empty top-level errors → raise
    (RateLimitError for RATE_LIMITED, else CollectorError); else return the nodes+pageInfo.
    """
```

**Generalized helper (ADR-002):**
```python
def _request_with_retry(self, url: str, repo: str, *, json_body: dict | None = None) -> httpx.Response:
    # json_body is None → self._client.get(url)   (every REST caller, unchanged)
    # json_body is not None → self._client.post(url, json=json_body)   (GraphQL only)
```

**Outbound GraphQL request (consumed, not exposed):**
`POST {base_url}/graphql` with body `{"query": <fixed constant>, "variables": {"owner","name","first","after"}}`.
Same `Authorization: Bearer <token>`, `Accept`, `X-GitHub-Api-Version` headers as the REST paths (set
on the shared client at construction). The fixed query (never built from untrusted input, never a
mutation — AC-V2-006-016, BR-V2-006-006):

```graphql
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: $first, after: $after,
                orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { number title body url createdAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```
`repo` is split into `owner`/`name` variables only — never interpolated into the query string or the
URL host/scheme (RISK-002). `first = page_size`; `after = endCursor` (None on the first page).

**Discussion node → RawItem field map (AC-005..010):**

| RawItem field | Source | Null/empty rule | AC |
|---|---|---|---|
| `repo` | validated `owner/repo` arg | — | AC-V2-006-001 |
| `item_type` | literal `"discussion"` | — | AC-V2-006-001 |
| `item_id` | `str(number)` | if `number` missing → **skip node** (return None) | AC-V2-006-005 / AC-V2-006-010 |
| `title` | `title` | `null` → `""` | AC-V2-006-006 |
| `body` | `body` (markdown, ADR-004) | `null` → `""` | AC-V2-006-007 |
| `url` | `url` | `null`/missing → `""` | AC-V2-006-008 |
| `created_at` | `createdAt` | raw ISO string, never reformatted | AC-V2-006-009 |

## Error Mapping

Two layers: transport (HTTP status, reused unchanged — BR-V2-006-010) and payload (GraphQL
200-with-errors, new — ADR-003). Both reuse the existing `CollectorError` hierarchy — no new class.

**Transport layer (`_classify`, reused verbatim on the POST):**

| HTTP / condition | `_classify` action | Raised | Pipeline handling | AC |
|---|---|---|---|---|
| 200 | OK | → payload layer (below) | — | AC-V2-006-001 |
| 429 / 5xx / 403+`X-RateLimit-Remaining:0` | RETRY | `RateLimitError` after budget | terminal → partial deliver; mid-budget → backoff+retry | AC-V2-006-015 |
| 401 / non-rate-limit 403 | FAIL_FAST | `AuthError` | fatal — abort run, no token in message | AC-V2-006-015 |
| transport error | RETRY | `NetworkError` after budget | recoverable → skip repo's discussions | AC-V2-006-022 |

**Payload layer (`_classify_graphql`, new — only on a 200, ADR-003):**

| GraphQL payload shape | Outcome | Raised | AC |
|---|---|---|---|
| `data.repository == null` OR `data.repository.discussions == null` | SKIP_REPO — WARN + `[]` | — | AC-V2-006-003 |
| non-empty top-level `errors` (not the null-shape above), `RATE_LIMITED` type | raise | `RateLimitError` | AC-V2-006-014 / AC-V2-006-015 |
| non-empty top-level `errors` (not the null-shape), other | raise | `CollectorError` | AC-V2-006-014 |
| `discussions.nodes` present, no blocking errors | map nodes | — | AC-V2-006-001 |

Security invariant on every arm: messages carry **status + repo + static reason only** — never the
token, request body, or headers (reused from `errors.py` construction; AC-V2-006-017).

Pipeline-level (in `_collect_all`, inner guard around `fetch_discussions`, ADR = v2-003 pattern):

| Condition | Handling | AC |
|---|---|---|
| recoverable (`InvalidRepoError`/`NetworkError`/non-fatal `CollectorError`) | WARN + skip **discussions only**, issues+releases survive | AC-V2-006-022 |
| `AuthError` | propagate to outer arm → fatal (all repos share token) | AC-7-005 |
| terminal `RateLimitError` | propagate to outer arm → break + partial deliver | AC-7-017 |

## Sequence Flows

**Flow 1 — `fetch_discussions` happy path + early-stop + payload classify (ADR-001/003):**
```
fetch_discussions(repo, lookback_days)
  cutoff = now(UTC) - lookback_days
  _validate_repo(repo)                              # reuse; path-traversal guard
  owner, name = repo.split("/", 1)
  url = "{base_url}/graphql"
  items = []; after = None
  while len(items) < max_items_per_repo:
    body = {"query": _DISCUSSIONS_QUERY,
            "variables": {"owner": owner, "name": name, "first": page_size, "after": after}}
    resp = _request_with_retry(url, repo, json_body=body)     # reuse retry/backoff/auth (POST)
    # _classify(resp) here only sees 200 (non-200 already raised/retried in the helper)
    payload = resp.json()
    result = _classify_graphql(payload, repo)         # ADR-003 shape-first
    if result is SKIP_REPO: WARN; return []           # disabled/not-found (AC-003)
    # (other errors already raised inside _classify_graphql)
    conn = result                                     # {"nodes": [...], "pageInfo": {...}}
    for node in conn["nodes"]:
      created = node.get("createdAt")
      if isinstance(created, str) and _parse_created(created) < cutoff:
        return items                                  # created-desc early-stop (AC-012)
      item = _map_discussion(node, repo)              # may return None (AC-010)
      if item is not None: items.append(item)
      if len(items) >= max_items_per_repo:
        logger.info("discussions truncated at %d for %s", ...); return items    # (AC-013)
    page = conn["pageInfo"]
    if not page.get("hasNextPage"): break
    after = page.get("endCursor")
  return items
```

**Flow 2 — pipeline per-repo isolation across THREE fetches (v2-003 pattern, AC-022):**
```
for repo in watched_repos:
  try:
    issues = collector.fetch_items(repo_name, lookback_days)          # existing
    try:
      releases = collector.fetch_releases(repo_name, lookback_days)   # v2-003
    except (InvalidRepoError, NetworkError) as exc: WARN; releases = []
    except CollectorError as exc:
      if isinstance(exc, (AuthError, RateLimitError)): raise
      WARN; releases = []
    try:
      discussions = collector.fetch_discussions(repo_name, lookback_days)   # NEW
    except (InvalidRepoError, NetworkError) as exc: WARN; discussions = []
    except CollectorError as exc:
      if isinstance(exc, (AuthError, RateLimitError)): raise    # exclude fatal subclasses
      WARN; discussions = []
    items = issues + releases + discussions                     # (AC-019)
    new, seen = _partition_new(items, state)                    # R1: BEFORE mark_seen
    state.mark_seen(items)                                      # full list (BR-V2-001-002)
    all_items.extend(new if delta_enabled else items)          # (AC-020)
    ...stats...
  except AuthError: raise                                       # fatal (AC-7-005)
  except RateLimitError: break                                  # partial (AC-7-017)
  except (InvalidRepoError, NetworkError, CollectorError) as exc:
    stats["skipped"] += 1; logger.warning("skipped %s: %s", repo_name, type(exc).__name__)
```
Note (memory lesson): the inner guard must EXCLUDE `AuthError`/terminal `RateLimitError` (both ⊂
`CollectorError`) so they reach the outer arms — the `isinstance(exc, (AuthError, RateLimitError)):
raise` line is the explicit exclusion, mirroring the release guard exactly.

## Edge Cases

Mapped from the 17 proposal edge cases:
1. Discussion created in-window → included as `RawItem(item_type="discussion")` — AC-V2-006-001/002.
2. Discussion created before cutoff → excluded (created-desc early-stop) — AC-V2-006-002/012.
3. Discussions **disabled** (`data.repository.discussions == null` + errors) → WARN + `[]`, run
   continues — AC-V2-006-003 (ADR-003 shape-first, skip checked FIRST).
4. Discussions enabled, zero in window → `[]`, no error — AC-V2-006-004.
5. `body == null` → `body = ""` — AC-V2-006-007.
6. `url == null`/missing → `url = ""` — AC-V2-006-008.
7. Node missing `number` → `_map_discussion` returns None, skipped — AC-V2-006-010.
8. Very long body → no collector truncation; summarizer 8000-char cap applies — INT-V2-006-004.
9. 200 with non-disabled `errors` (e.g. malformed query, `RATE_LIMITED`) → raise, not silent `[]`
   — AC-V2-006-014 (ADR-003).
10. Discussions span multiple pages → cursor loop until cutoff or `max_items_per_repo` — AC-V2-006-011.
11. Transport 401/403 non-rate-limit on the POST → `AuthError`, fail fast — AC-V2-006-015.
12. Transport 429/5xx/secondary-rate-limit on the POST → same backoff/retry; terminal → partial
    deliver — AC-V2-006-015 / AC-7-017.
13. Discussion seen on prior run → suppressed by delta filter (`repo+"discussion"+number`) — AC-V2-006-020.
14. One repo's `fetch_discussions` fails while issues/releases succeed → discussions skipped, others
    survive — AC-V2-006-022 (Flow 2 inner guard).
15. +1 GraphQL call per repo → shared client + retry budget; fine at 5000 points/hr — RISK-004.
16. Fixed query, only owner/name/cursor variables → no injection surface; token never in any
    log/error on the GraphQL path — AC-V2-006-016/017.
17. `delta_enabled == false` → all discussions render every run (inherited v2-001) — AC-V2-006-020.

## Performance

- +1 GitHub **GraphQL** call per repo per run (a few when paginating). GraphQL is point-based and
  shares the same 5000-points/hr authenticated budget; negligible for a single-operator watchlist
  (RISK-004). All three fetches share one `httpx.Client` and one retry budget.
- Pagination bounded by `max_items_per_repo` (cap) AND created-desc early-stop (cutoff) — same bound
  as `fetch_items`/`fetch_releases`. No unbounded page walks.
- No new state/LLM/render work per discussion beyond what any `RawItem` already incurs.

## Security

STRIDE gate: **SKIPPED** at S2 (`security.stride_analysis=auto`; a new transport *verb* — POST to the
GraphQL endpoint — but no new secret handling, no PII, no upload, no admin, no new auth surface) —
reaffirmed here. Reaffirmed invariants (all reused from github-collector-2, no new code path for the
security machinery):
- **RISK-001 (Info disclosure, LOW):** the `GITHUB_TOKEN` is never written to logs/errors/returned
  data on the GraphQL path. The token stays on the shared client headers (never in the query body);
  error messages are composed from status + repo + static reason only (`errors.py`). A test asserts
  the token value never appears in any discussion-path log/error line (BR-V2-006-005, AC-V2-006-017).
- **RISK-002 (Tampering/SSRF-shaped request, LOW):** the GraphQL endpoint URL derives only from the
  configured `base_url` (`{base_url}/graphql`); `repo` fills only the `owner`/`name` query variables,
  never the URL host/scheme; `_validate_repo` (path-traversal guard) runs before any request; the
  query string is a fixed constant, never built from caller input, never a mutation (BR-V2-006-006,
  AC-V2-006-016).
- TLS verification never disabled; POST is the sole non-GET, scoped to `/graphql` with a fixed query
  (ADR-002). No new secret, no new config surface.

## Risk Assessment

| Risk | Severity | Mitigation | AC/ADR |
|---|---|---|---|
| RISK-003 200-with-errors misclassification (crash on null / silent drop) | MEDIUM | ADR-003 shape-first ordered classification (null-shape → skip; else errors → raise; else map); 3 explicit tests | ADR-003 / AC-V2-006-003/014 |
| RISK-001 token leak on the GraphQL path | LOW | reuse authed client + static error messages; token stays out of body; token-absence test | ADR-002 / §Security / AC-V2-006-017 |
| RISK-002 SSRF-shaped request / query injection | LOW | fixed query, `base_url` from config, `_validate_repo`, owner/name variables only | §Security / AC-V2-006-016 |
| POST regresses GET-only REST invariant | MEDIUM-if-regressed | ADR-002 `json_body=None` default keeps REST callers GET; test asserts REST=GET, GraphQL=one POST | ADR-002 / AC-V2-006-016 |
| RISK-004 +1 GraphQL call per repo (point-based) | LOW | shared client + retry budget; negligible at 5000/hr | §Performance |
| R1 violation (partition after mark_seen) | HIGH-if-regressed | one partition + one mark_seen per repo across three sources; count-invariant test | Flow 2 / v2-001 |
| Inner guard swallows AuthError/terminal RateLimitError | HIGH-if-regressed | explicit `isinstance(exc,(AuthError,RateLimitError)): raise` exclusion (memory lesson) | Flow 2 |

## Implementation Guide

**Recommended order** (helper generalization → mapper → classifier → adapter method → pipeline wiring → tests):
1. Generalize `_request_with_retry` with `*, json_body: dict | None = None` (ADR-002) — GET when None
   (REST unchanged), POST when provided. File: `src/osspulse/github/client.py`.
2. Add the module constant `_DISCUSSIONS_QUERY` (the fixed GraphQL query) + `_map_discussion(node, repo)`
   helper — mirror `_map_item`; null-guards + skip-when-`number`-missing (ADR-004). Same file.
3. Add `_classify_graphql(payload, repo)` — shape-first ordered classification (ADR-003): null
   repository/discussions → skip signal; else non-empty `errors` → raise (`RateLimitError` for
   `RATE_LIMITED`, else `CollectorError`); else return the connection. Same file.
4. Add `fetch_discussions(repo, lookback_days)` — cursor loop (ADR-001) calling `_request_with_retry`
   with `json_body`, `_classify_graphql`, `_map_discussion`; early-stop on `createdAt < cutoff`; cap
   with info truncation log. Same file.
5. Wire into `pipeline._collect_all` — a second inner `try/except` around `fetch_discussions` mirroring
   the release guard; concatenate `issues + releases + discussions`; keep `_partition_new` BEFORE a
   single `mark_seen(items)` (R1). File: `src/osspulse/pipeline.py`.
6. Unit tests for `_map_discussion` (each null/skip case) + `fetch_discussions` (window, early-stop,
   truncation, cursor pagination, disabled→skip, enabled-empty→[], other-errors→raise, rate-limit,
   token-absence, POST-verb assertion).
7. Pipeline tests: three-source concatenation (AC-019), delta suppression (AC-020), discussion-fetch
   isolation preserves issues+releases (AC-022), mark_seen count-invariant.

**Patterns to follow (with file paths):**
- Mirror `GitHubCollector.fetch_releases` / `_map_release` in `src/osspulse/github/client.py` — same
  control flow, same helpers, same error semantics; swap Link→cursor and add the payload classify.
- Reuse `_parse_created` (`client.py`) for the `createdAt` stop comparison.
- Reuse `_validate_repo`, `_classify`, `_backoff_seconds`, `RetryPolicy` unchanged.
- Preserve the v2-001 R1 pattern + v2-003 inner-guard pattern in `src/osspulse/pipeline.py`:
  `_partition_new` BEFORE one `mark_seen(items)` on the full concatenated list; inner guard EXCLUDES
  `AuthError`/terminal `RateLimitError`.
- Mock the httpx layer with `MockTransport` + injected `sleep` (github-collector-2 ADR-005) so
  retries never wait; the transport can return a 200 with a GraphQL `errors` body to test ADR-003.

**Gotchas:**
- `_classify_graphql` check ORDER is load-bearing: null-shape (skip) BEFORE errors-raise — a disabled
  repo carries BOTH a null connection AND an `errors` entry; check the shape first (ADR-003).
- Do NOT hardcode a GitHub `errors[].type` string to detect disabled Discussions — key on the null
  connection shape (handoff §2 warning).
- Early-stop compares `createdAt` (order == inclusion field here) — no skew, unlike v2-003.
- Do NOT stop pagination inside `_classify_graphql`; the cursor loop stops on `hasNextPage`/cutoff/cap.
- `_request_with_retry` default `json_body=None` MUST keep issuing GET for the REST callers — do not
  change their call sites (ADR-002); assert REST=GET in a test.
- The inner guard must NOT swallow `AuthError`/terminal `RateLimitError` — keep the explicit
  `isinstance(...): raise` exclusion (memory lesson from v2-003).
- `mark_seen` exactly once per repo with issues+releases+discussions — a second call or passing `new`
  violates R1 (v2-001 count-invariant test).
- Query `body` not `bodyText` (markdown for the summarizer/renderer) — ADR-004.
- Do NOT open a digest-renderer delta — the renderer is already discussion-ready (BR-V2-006-004).
