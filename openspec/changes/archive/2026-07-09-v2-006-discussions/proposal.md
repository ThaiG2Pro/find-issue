## Why

The V1+V2 pipeline (`osspulse run`) collects, summarizes, renders and delivers new **issues** and
**releases** for each watched repo. PROJECT_SPEC §5 (V2) calls for **Discussions** to become a
first-class source alongside issues and releases so the operator sees "what the community is
debating" (RFCs, Q&A, announcements) in the same digest — the project's "understanding over speed"
principle: a contributor evaluating a repo needs to know its active discussions to contribute with
depth (PROJECT_SPEC §3 story B [P1], §4 flow "Discussion nóng").

Like Releases (v2-003), the pipeline downstream of the collector was deliberately built
**item-type-agnostic**, so the incremental cost of a new source is small and concentrated in the
Collector:

- **State Store** (state-store-3) keys seen-state on `repo + item_type + item_id` — already accepts
  any `item_type`, so delta/idempotency work for `"discussion"` with **no change**.
- **Delta filter** (v2-001-delta-filter) lives in `pipeline.py` and filters any `item_type`, so
  discussions are suppressed on re-run with **no change**.
- **Summarizer** (summarizer-llm-4) summarizes any `RawItem` from `title`+`body` and already
  truncates the input at an 8000-char `input_char_cap`, so a long discussion body is capped
  automatically with **no collector-side truncation**.
- **Digest Renderer** (digest-renderer-5) already ships `"discussion"` in `GROUP_ORDER` with the
  `Discussion` label (living AC-5-006 / AC-5-011); discussions render under `### Discussion (N)` with
  **no renderer change**.

So the delta is: teach the **Collector** to fetch + map GitHub discussions, and wire **one extra
call** into `pipeline.run_pipeline` so each repo is collected for issues, releases *and* discussions.

**The one thing that is genuinely new** (vs the REST issue/release paths): GitHub Discussions are
**only** available through the **GraphQL API** — there is no REST endpoint. GraphQL uses a single
`POST https://api.github.com/graphql` endpoint with a query+variables body, **cursor-based**
pagination (not the REST `Link` header), and a **`200 OK` response that can still carry an `errors`
array** (e.g. `repo.discussions` is `null` when Discussions are disabled). This breaks three
assumptions baked into the existing collector — GET-only, `Link`-header pagination, and
"non-200 == failure" — so those must be handled without regressing the issue/release paths.

## What Changes

- Add discussion collection to the **GitHub Collector**: a `fetch_discussions(repo, lookback_days)`
  adapter method that issues a GraphQL `POST https://api.github.com/graphql` query for a repo's
  discussions ordered by `CREATED_AT DESC`, paginates via GraphQL cursors (`pageInfo.hasNextPage` /
  `endCursor`, reusing the existing `max_items_per_repo` + `page_size` caps), and maps each
  discussion to a `RawItem` with `item_type = "discussion"`.
- **Discussion inclusion (Approach A)** is decided by `createdAt` within the lookback window (UTC) —
  the same "newly created within `lookback_days`" rule as issues. Discussions created before the
  cutoff are excluded; created-desc ordering enables the same per-item early-stop as issues.
- **Discussion → RawItem mapping**: `item_id = number` (as a string — renders as `#42`, stable +
  human-readable per repo), `title = title`, `body = body` (markdown, `""` when null), `url = url`
  (`""` when null), `created_at = createdAt` (raw ISO string, used for the cutoff).
- **Repos with Discussions disabled** are handled gracefully: a GraphQL `200` whose payload has
  `data.repository.discussions == null` (with a matching `errors` entry) SHALL be treated like a
  skipped repo — WARN + return an empty list for that repo — never crash the run.
- **New collector cross-cutting behavior for the GraphQL transport**, additive and isolated from the
  REST paths:
  - a `POST` to the GraphQL endpoint (the existing REST invariant is "only GET"; this change scopes
    that to the REST paths and adds "the GraphQL path issues exactly one POST kind, to the fixed
    GraphQL endpoint, with the query+variables in the body — never a mutation, never a
    caller-controlled query");
  - GraphQL **cursor pagination** (not `Link`);
  - GraphQL **error-model classification**: a `200` carrying a top-level `errors` array or a `null`
    `discussions` connection is classified (repo-disabled/not-found → skip that repo; otherwise a
    clear error), so `_classify` HTTP-status logic still governs the transport-level `429`/`5xx`/auth.
  - Reuse **unchanged**: the same authenticated httpx client + token discipline (token never logged),
    the same retry/backoff policy (429 / 5xx / secondary rate limit), the same TLS-on posture, and
    the same `base_url`-from-config-only rule (the GraphQL URL is derived from the configured
    `base_url`, never from the `repo` argument).
- **Wire discussions into the pipeline** (`scheduler-cli` capability): `run_pipeline` now collects
  issues, releases *and* discussions per repo and concatenates them into the single `list[RawItem]`
  that flows into the existing delta → summarize → render → deliver path. No stage module imports
  another (AC-7-002 preserved); `pipeline.py` remains the only cross-stage importer. A per-repo
  discussion-fetch failure is isolated exactly like a release-fetch failure.
- Documentation: README gains a short note that the digest now includes Discussions, that this uses
  the GraphQL API, and that repos with Discussions disabled are silently skipped.

## Capabilities

### New Capabilities
- None. This change adds requirements to existing capabilities (no new pipeline stage, no new port).

### Modified Capabilities
- **`github-collector`** — ADDED requirements only: fetch discussions via GraphQL, map discussion
  JSON → `RawItem`, discussion cutoff/cursor-pagination, the GraphQL transport/error-model contract
  (POST to the GraphQL endpoint, 200-with-errors classification, Discussions-disabled → skip), and
  reaffirmation that the new path reuses the existing auth / rate-limit / pure-I/O contract. No
  existing issue or release requirement changes behavior; the delta is purely additive. Delta spec:
  `specs/github-collector/spec.md`.
- **`scheduler-cli`** — MODIFIED requirement: the `run_pipeline` orchestration now collects
  discussions in addition to issues and releases per repo and concatenates them before the
  delta/summarize/render steps. Same pipeline-wiring home as v2-001/v2-003 (`pipeline.py` only).
  Delta spec: `specs/scheduler-cli/spec.md`.

> **Explicitly NOT modified — `digest-renderer`.** The living renderer already renders `"discussion"`
> items under `### Discussion (N)` (`GROUP_ORDER = ["issue","discussion","release"]`, AC-5-006 /
> AC-5-011). Adding a MODIFIED renderer delta would either be a no-op (rejected by `openspec
> validate`, which requires a MODIFIED requirement to actually differ) or misrepresent existing
> behavior. The renderer is already discussion-ready. See Assumptions / Handoff. (This mirrors the
> v2-003-releases decision and the recorded memory lesson: "when the pipeline was built
> item_type-agnostic, a new source is collector-only — do NOT write a no-op renderer delta".)

## Impact

- **New code**: `GitHubCollector.fetch_discussions(repo, lookback_days)` + a `_map_discussion()`
  helper + a small GraphQL POST/paginate helper in `src/osspulse/github/client.py` (mirrors the
  existing `fetch_releases` / `_map_release`). The `GitHubClient` Protocol is **unchanged** —
  `fetch_discussions` is an adapter-only method, following summarizer-llm-4 ADR-005 / v2-003
  BR-V2-003-003 (batch/extra helper on the adapter, not on the frozen Protocol).
- **Touched code**: `pipeline._collect_all` calls `collector.fetch_discussions(repo_name,
  lookback_days)` alongside `fetch_items` / `fetch_releases` and extends the per-repo item list
  before `_partition_new` / `mark_seen`, inside the same per-repo isolation try/except used for
  releases.
- **Config**: **no new `Config` field** — discussions are always-on in V2, and discussion fetching
  reuses the existing `CollectorConfig` tunables (`max_items_per_repo`, `page_size`, `base_url`,
  `retry`) with no new field (per the v2-003 discipline "no new `Config` field to pass adapter
  tunables").
- **External**: one additional GitHub **GraphQL** call (possibly a few, when paginating) per repo per
  run, authenticated with the same `GITHUB_TOKEN`. GraphQL shares the same 5000-points/hr budget;
  negligible for a personal watchlist. GraphQL cost is point-based (not 1 req = 1 unit), noted as a
  minor watch item for very large watchlists.
- **No change** to state store, delta filter, summarizer, renderer, or delivery.

---

## Non-Goals

- ❌ **No digest-renderer change** — the renderer already handles `"discussion"` (AC-5-006 / AC-5-011).
- ❌ **No "hot / active discussion" ranking** (by comment count, reactions, or recent activity). PROJECT_SPEC §4 mentions "Discussion nóng", but this change implements **Approach A** (user-confirmed):
  newly-*created* discussions within `lookback_days`, exactly like issues. Activity-based selection
  (`updatedAt`, comment volume) is a deliberate future scope — it needs a different ordering/inclusion
  field and would repeat the v2-003 RISK-002 ordering-skew trap.
- ❌ **No comment/thread collection** — only the discussion's own `title` + `body` are collected and
  summarized; replies, answers, and comment threads are not fetched (keeps the GraphQL query small and
  the summarizer input bounded, consistent with issues collecting only the issue body).
- ❌ **No per-source enable/disable config toggle** (`[sources]`) in this change — discussions are
  collected by default (always-on), same as issues and releases. A future toggle is possible but out
  of scope.
- ❌ **No new summarization behavior for discussions** — a discussion is summarized exactly like an
  issue/release (title + body via `summarize_items`), reusing the 8000-char input cap.
- ❌ **No discussion category filtering** — discussions of every category (Q&A, Ideas,
  Announcements, etc.) are collected; category is not used to include/exclude.
- ❌ **No change to group ordering in the digest** — the fixed group order Issues → Discussions →
  Releases (AC-5-006) is preserved by the unchanged renderer.
- ❌ **No general-purpose GraphQL client** — the collector issues exactly one fixed, hardcoded
  discussions query with the `repo` (owner/name) and pagination cursor as the only variables; the
  query string is never built from untrusted input.

## Assumptions

- **[CONFIRMED]** Discussions are fetched via the GitHub **GraphQL API** (`POST .../graphql`) —
  there is no REST endpoint for Discussions. *(Source: kickoff task + GitHub API; PROJECT_SPEC §8
  "GraphQL khi tới Discussions".)*
- **[CONFIRMED]** **Approach A**: inclusion is by `createdAt` within `lookback_days` (newly-created
  discussions), the same rule as issues — NOT activity/hotness-based. *(User-confirmed at kickoff;
  `_state.json` watch item.)*
- **[CONFIRMED]** The digest renderer needs no change — it already emits `### Discussion (N)` for
  `item_type = "discussion"`. *(Source: digest-renderer living spec AC-5-006 / AC-5-011 +
  `renderer.py` `GROUP_ORDER`/`GROUP_LABELS`.)*
- **[CONFIRMED]** State store, delta filter and summarizer accept `item_type = "discussion"`
  unchanged. *(Source: state-store-3 key contract; v2-001 pipeline delta; summarizer-llm-4 8000-char
  cap.)*
- **[CONFIRMED]** `RawItem.item_id = number` (the per-repo discussion number, stringified — renders as
  `#42`), rather than the GraphQL global node `id` (an opaque base64 string that would render as an
  ugly `#D_kwDO...`). This mirrors the issue mapping (`item_id = number`) and keeps the renderer
  unchanged. *(User-confirmed at SPEC-LOCK 2026-07-09; matches the issue mapping AC-2-016 + renderer
  line format `- #{item_id}`. A discussion `number` is stable per repo.)*
- **[ASSUMED]** A repo with **Discussions disabled** returns a GraphQL `200` whose payload has
  `data.repository.discussions == null` and a top-level `errors` entry — this is treated as a
  skipped repo (WARN + empty list), the same user-visible outcome as a `404` repo on the REST path.
  *(Analyst inference from GitHub GraphQL behavior; validate at SPEC-LOCK — the exact detection key
  is a design detail for S3, but the *behavior* — skip gracefully, never crash — is CONFIRMED.)*
- **[CONFIRMED]** Discussions ordered `CREATED_AT DESC` (newest-first) so the same per-item
  early-stop-at-cutoff pagination used for issues applies; because inclusion and ordering use the
  **same** `createdAt` field, there is **no** ordering-vs-inclusion skew (this is simpler than
  v2-003 releases, which had a `published_at`/`created_at` skew — RISK-002 there does not recur
  here). *(User-confirmed at SPEC-LOCK 2026-07-09; GraphQL `discussions(orderBy: {field: CREATED_AT, direction: DESC})`.)*
- **[ASSUMED]** `body` may be `null` (a discussion with an empty body) → coerced to `""`, like issue
  and release bodies. *(Analyst inference from dirty-data tolerance AC-2-010 / AC-V2-003-008.)*
- **[CONFIRMED]** Discussions are always-on in V2 (no per-source config toggle); reuse the existing
  `CollectorConfig` with no new field. *(Consistent with v2-003 BR-V2-003-006.)*

## Edge Cases

1. **State/input** — discussion created inside the window → included as `RawItem(item_type="discussion")`.
2. **State/input** — discussion created before the cutoff → excluded (created-desc early-stop).
3. **State transition** — Discussions **disabled** for a repo (`data.repository.discussions == null`
   + `errors`) → WARN + empty list for that repo, run continues (graceful skip).
4. **State** — repo with Discussions enabled but zero discussions in the window → empty list, no error.
5. **Data integrity** — discussion with `null` body → `body = ""` (no crash; summarizer/renderer degrade).
6. **Data integrity** — discussion with `null`/missing `url` → `url = ""` (renderer omits the `[link]`).
7. **Data integrity** — discussion node missing `number` → skipped (cannot key), no crash (dirty-data).
8. **Input boundary** — very long discussion `body` → truncated to 8000 chars by the summarizer's
   existing `input_char_cap`; the Collector does no truncation of its own.
9. **Integration / GraphQL error model** — a `200 OK` carrying a top-level `errors` array that is NOT
   a disabled/not-found case (e.g. `RATE_LIMITED` type, or a malformed-query error) → surfaced as a
   clear error, not silently returned as empty.
10. **Integration / pagination** — discussions span multiple GraphQL pages → follow
    `pageInfo.hasNextPage` + `endCursor` until cutoff or `max_items_per_repo`, whichever first.
11. **Integration** — transport-level `401`/`403` (non-rate-limit) on the GraphQL POST → fail fast
    (shared token invalid), same as the REST paths.
12. **Integration** — transport-level `429`/`5xx`/secondary-rate-limit (`403` + `X-RateLimit-Remaining: 0`)
    on the GraphQL POST → same backoff/retry policy as issues/releases; terminal `RateLimitError` →
    partial results still delivered (reuses AC-7-017).
13. **State transition** — a discussion already seen on a prior run → suppressed by the delta filter
    (identity `repo + "discussion" + number`), inherited from v2-001.
14. **Concurrency / isolation** — one repo's `fetch_discussions` fails while its `fetch_items` /
    `fetch_releases` succeed → the failure is isolated (WARN + skip discussions for that repo);
    issues/releases already collected are not lost.
15. **Rate budget** — adding the GraphQL call adds GitHub API usage per repo per run; fine under the
    5000-points/hr authenticated budget for a watchlist; GraphQL is point-based, noted for very large
    watchlists.
16. **Security** — the GraphQL query is a fixed constant; only `owner`, `name`, and the pagination
    cursor are variables → no injection surface; the `GITHUB_TOKEN` must never appear in any
    GraphQL-path log/error (same discipline as the REST paths).
17. **Config** — `delta_enabled = false` → all discussions render every run (no suppression), exactly
    like V1 issue behavior; inherited from v2-001.

## Early Risk Flags

STRIDE gate: **SKIPPED** (`security.stride_analysis = auto`; this change adds a new *transport verb*
— a POST to the GraphQL endpoint — but **no new secret handling, no PII, no upload, no admin, no new
auth surface**: it reuses the same authenticated `GITHUB_TOKEN`, the same TLS-on httpx client, and a
fixed non-mutating query). The relevant invariants are reaffirmed rather than re-derived:

- **RISK-001 — Information disclosure (LOW, reaffirm)**: the GraphQL path must never write the
  `GITHUB_TOKEN` into logs/errors/returned data. Mitigation: reuse the same httpx client + error
  discipline (github-collector-2 ADR-004, AC-2-009); a test asserts the token never appears in any
  discussion-path log/error (BR-V2-006-005).
- **RISK-002 — Tampering / SSRF-shaped request (LOW, reaffirm)**: the GraphQL endpoint URL derives
  only from the configured `base_url`; the `repo` fills only the query `owner`/`name` variables,
  never the URL host/scheme; the query string is a fixed constant (no caller-built query). Mitigation:
  reuse `_validate_repo` + base-url-from-config discipline (AC-2-025), BR-V2-006-006.
- **RISK-003 — Correctness / GraphQL error model (MEDIUM)**: a GraphQL `200` can carry an `errors`
  array or a `null` connection (Discussions disabled). Treating every `200` as success (the REST
  assumption) would crash on `null.discussions` or silently drop real errors. Mitigation: an explicit
  GraphQL-payload classification step (disabled/not-found → skip repo; other errors → raise) —
  AC-V2-006-003 / AC-V2-006-013..015, resolved in spec, refined in S3 design.
- **RISK-004 — Rate budget (LOW)**: GraphQL point-based cost + extra call per repo. Negligible at
  5000 points/hr; noted for large watchlists.

## Business Rules

- **BR-V2-006-001**: A discussion SHALL be represented as a `RawItem` with `item_type = "discussion"`
  and identity `repo + "discussion" + number` (the per-repo discussion number as a string), reusing
  the `item_type`-agnostic state-store key contract so delta/idempotency apply unchanged.
- **BR-V2-006-002**: Discussion **inclusion** SHALL be decided by `createdAt` within the lookback
  window (`now(UTC) - lookback_days`) — Approach A, the same rule as issues; hotness/activity ranking
  is out of scope.
- **BR-V2-006-003**: Discussion fetching SHALL reuse the existing `CollectorConfig` tunables
  (`max_items_per_repo`, `page_size`, `base_url`, `retry`) with no new config field, and SHALL be
  exposed as an adapter method `fetch_discussions` — the `GitHubClient` Protocol SHALL NOT gain a new
  method (frozen, mirroring summarizer-llm-4 ADR-005 / v2-003 BR-V2-003-003).
- **BR-V2-006-004**: The digest renderer SHALL remain unchanged — discussions render under the
  existing `### Discussion (N)` group (`GROUP_ORDER` already includes `"discussion"`, AC-5-006 /
  AC-5-011); this change SHALL NOT add a digest-renderer delta.
- **BR-V2-006-005**: All existing collector security invariants SHALL apply unchanged on the
  discussion (GraphQL) path: the `GITHUB_TOKEN` is never logged/leaked, TLS verification is never
  disabled, and the GraphQL endpoint URL comes only from the configured `base_url` (never from the
  `repo` argument or response data). *(github-collector-2 ADR-004 / AC-2-009 / AC-2-013 / AC-2-025.)*
- **BR-V2-006-006**: The GraphQL request SHALL be a single fixed, non-mutating query with only
  `owner`, `name`, and a pagination cursor as variables — the query string SHALL NEVER be built from
  untrusted input, and the collector SHALL NOT issue any GraphQL mutation.
- **BR-V2-006-007**: A GraphQL `200` response whose payload indicates Discussions are disabled or the
  repo is not found (`data.repository` or `data.repository.discussions` is `null`, with a matching
  `errors` entry) SHALL be treated as a skipped repo (WARN + empty list), never a crash; any other
  top-level `errors` payload SHALL surface a clear error.
- **BR-V2-006-008**: Discussions SHALL be collected by default (always-on) in V2; this change SHALL
  NOT add a per-source enable/disable config field.
- **BR-V2-006-009**: A discussion-fetch failure for one repo SHALL be isolated exactly like a
  release-fetch failure (recoverable → WARN + skip that repo's discussions + continue; `AuthError` →
  fatal; terminal `RateLimitError` → deliver partial), never aborting items already collected.
- **BR-V2-006-010**: The transport-level HTTP classification (`429`/`5xx`/secondary-rate-limit →
  retry; non-rate-limit `401`/`403` → fail fast) SHALL be reused unchanged on the GraphQL POST; only
  the GraphQL **payload**-level error model (BR-V2-006-007) is new.

## Integration Points

- **INT-V2-006-001**: Collector issues `POST {base_url-derived}/graphql` with a fixed discussions
  query on the existing authenticated httpx client (github-collector-2), reusing its
  retry/error-isolation machinery for transport-level errors.
- **INT-V2-006-002**: `pipeline.run_pipeline` (`scheduler-cli`) calls `collector.fetch_discussions`
  alongside `collector.fetch_items` / `collector.fetch_releases` per repo and concatenates the
  results into the single `list[RawItem]` before the delta → summarize → render → deliver path
  (pipeline is the only cross-stage importer; AC-7-002 preserved).
- **INT-V2-006-003**: Discussions consume `JsonFileStateStore.is_seen` / `mark_seen` unchanged
  (`repo + "discussion" + number`); the v2-001 delta filter suppresses previously-seen discussions
  with no change.
- **INT-V2-006-004**: Discussions consume `LiteLLMSummarizer.summarize_items` unchanged; long
  discussion bodies are truncated by the existing 8000-char `input_char_cap` (summarizer-llm-4), so
  no collector-side truncation is required.
- **INT-V2-006-005**: Discussions render through the unchanged `MarkdownDigestRenderer` under the
  existing `### Discussion (N)` group (`GROUP_ORDER`/`GROUP_LABELS` already include `"discussion"`).

## Figma
Figma: N/A (CLI tool — no visual design surface).

---
## _Structured Extract

### AC List
- AC-V2-006-001: [CONFIRMED] Collector fetches discussions via GraphQL `POST .../graphql`, returns `RawItem`s with `item_type = "discussion"`
- AC-V2-006-002: [CONFIRMED] Discussions with `createdAt` inside the lookback window are returned (Approach A); older ones excluded
- AC-V2-006-003: [CONFIRMED] Repo with Discussions disabled (`data.repository.discussions == null` + errors) → WARN + empty list, run continues
- AC-V2-006-004: [CONFIRMED] Repo with Discussions enabled but no discussions in window → empty list, no error
- AC-V2-006-005: [CONFIRMED] `RawItem.item_id = number` (stringified discussion number), not the GraphQL global node id
- AC-V2-006-006: [CONFIRMED] `title = discussion title`
- AC-V2-006-007: [CONFIRMED] `body = discussion body`, empty string when null
- AC-V2-006-008: [CONFIRMED] `url = discussion url`, empty string when null
- AC-V2-006-009: [CONFIRMED] `created_at = createdAt`, preserved as the raw ISO string
- AC-V2-006-010: [CONFIRMED] Discussion node missing `number` is skipped, no crash
- AC-V2-006-011: [CONFIRMED] Discussion pagination uses GraphQL cursors (`pageInfo.hasNextPage`/`endCursor`), bounded by `max_items_per_repo`/`page_size` from config
- AC-V2-006-012: [CONFIRMED] Discussions returned newest-first (`CREATED_AT DESC`); early-stop when `createdAt` < cutoff (no ordering-vs-inclusion skew — same field)
- AC-V2-006-013: [CONFIRMED] Info-level truncation log when `max_items_per_repo` is reached for discussions
- AC-V2-006-014: [CONFIRMED] A GraphQL `200` with a non-disabled/non-not-found top-level `errors` array surfaces a clear error (not silently empty)
- AC-V2-006-015: [CONFIRMED] Transport `429`/`5xx`/secondary-rate-limit on the GraphQL POST reuses the same retry/backoff; `401`/`403` non-rate-limit → fail fast
- AC-V2-006-016: [CONFIRMED] GraphQL request is a fixed non-mutating query; only `owner`/`name`/cursor are variables; query never built from untrusted input
- AC-V2-006-017: [CONFIRMED] Discussion requests reuse the authenticated client; token never logged; TLS on; endpoint URL from config `base_url` only
- AC-V2-006-018: [CONFIRMED] Discussion fetch touches no state/LLM; `GitHubClient` Protocol unchanged (`fetch_discussions` adapter-only)
- AC-V2-006-019: [CONFIRMED] `run_pipeline` collects issues, releases AND discussions per repo, concatenated into one list
- AC-V2-006-020: [CONFIRMED] Discussions flow through the existing delta filter and are marked seen like any item (`repo + "discussion" + number`)
- AC-V2-006-021: [CONFIRMED] Discussions render under the existing `### Discussion (N)` group; no renderer change
- AC-V2-006-022: [CONFIRMED] A per-repo discussion-fetch failure is isolated (WARN + skip), not aborting collected items

### Business Rules
- BR-V2-006-001: Discussion identity `repo + "discussion" + number`, reuses state-store key contract
- BR-V2-006-002: Inclusion by `createdAt` in window (Approach A); no hotness ranking
- BR-V2-006-003: Reuse `CollectorConfig`; `fetch_discussions` adapter-only; Protocol frozen
- BR-V2-006-004: Renderer unchanged — discussions use the existing Discussion group
- BR-V2-006-005: Existing security invariants apply unchanged on the GraphQL path
- BR-V2-006-006: Fixed non-mutating query; only owner/name/cursor variables; no query from untrusted input
- BR-V2-006-007: 200-with-errors: disabled/not-found → skip repo; other errors → raise
- BR-V2-006-008: Discussions always-on; no per-source config toggle
- BR-V2-006-009: Per-repo discussion-fetch failure isolated like releases
- BR-V2-006-010: Transport-level HTTP classification reused unchanged; only GraphQL payload error model is new

### Integration Points
- INT-V2-006-001: Collector → `POST .../graphql` fixed discussions query (existing authed client)
- INT-V2-006-002: pipeline → `fetch_discussions` alongside `fetch_items`/`fetch_releases`, concatenated
- INT-V2-006-003: discussions → state-store `is_seen`/`mark_seen` unchanged (delta from v2-001)
- INT-V2-006-004: discussions → summarizer `summarize_items` unchanged (8000-char cap covers body)
- INT-V2-006-005: discussions → renderer `### Discussion (N)` group unchanged

### Risk Flags
- RISK-001: Token leakage on the GraphQL path — LOW (reaffirm github-collector-2 ADR-004)
- RISK-002: SSRF-shaped request / query injection — LOW (fixed query, base_url from config, _validate_repo)
- RISK-003: GraphQL 200-with-errors / null-connection error model — MEDIUM (explicit classification step)
- RISK-004: GraphQL point-based rate budget + extra call per repo — LOW (fine at 5000/hr)

### Metadata
ticket_id: V2-006
domain: github-collector, scheduler-cli
has_figma: false
has_cms_ui: false
actors: [operator]
ac_count: 22
ac_confirmed: 22
ac_assumed: 0
ac_missing: 0
ac_unclear: 0
edge_cases: 17
stride_gate: SKIPPED
renderer_delta: NONE (already discussion-ready — AC-5-006/AC-5-011)
scope: standard
rigor: lite
