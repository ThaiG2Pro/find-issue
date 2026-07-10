## Why

The V1 pipeline (`osspulse run`) collects, summarizes, renders and delivers new **issues** for each
watched repo. PROJECT_SPEC §5 (V2) calls for **Releases** to become a first-class source alongside
issues so the operator sees "what shipped" (new tags + changelog) in the same digest, not just
"what's being discussed". A contributor evaluating a repo needs to know its release cadence and
recent changelog to understand the project deeply (the project's "understanding over speed"
principle). This change adds the Releases source to the existing pipeline.

The pipeline downstream of the collector was deliberately built **item-type-agnostic**, so the
incremental cost of a new source is small and concentrated in the Collector:

- **State Store** (state-store-3) keys seen-state on `repo + item_type + item_id` — already accepts
  any `item_type`, so delta/idempotency work for `"release"` with **no change**.
- **Delta filter** (v2-001-delta-filter) lives in `pipeline.py` and filters any `item_type`, so
  releases are suppressed on re-run with **no change**.
- **Summarizer** (summarizer-llm-4) summarizes any `RawItem` from `title`+`body` and already
  truncates the input at an 8000-char `input_char_cap`, so a long changelog body is capped
  automatically with **no collector-side truncation**.
- **Digest Renderer** (digest-renderer-5) already ships `"release"` in `GROUP_ORDER` with the
  `Release` label (living AC-5-006 / AC-5-011); releases render under `### Release (N)` with **no
  renderer change**.

So the delta is: teach the **Collector** to fetch + map GitHub releases, and wire **one extra call**
into `pipeline.run_pipeline` so each repo is collected for issues *and* releases.

## What Changes

- Add release collection to the **GitHub Collector**: a `fetch_releases(repo, lookback_days)`
  adapter method that calls the GitHub REST endpoint `GET /repos/{owner}/{repo}/releases`, paginates
  (reusing the existing `Link`-header + `max_items_per_repo` + `page_size` machinery), and maps each
  release to a `RawItem` with `item_type = "release"`.
- **Release inclusion** is decided by `published_at` within the lookback window (UTC); **draft**
  releases (`published_at == null`) are excluded; prereleases are included.
- **Release → RawItem mapping**: `item_id = tag_name` (stable, human-readable — renders as `#v1.2.0`),
  `title = name` (falling back to `tag_name` when null/empty), `body = body` (changelog, `""` when
  null), `url = html_url` (`""` when null), `created_at = published_at` (raw ISO string, used for the
  cutoff).
- Reuse **all** existing collector cross-cutting behavior on the release path unchanged: the same
  authenticated GET-only httpx client (token never logged), the same retry/backoff policy
  (429 / 5xx / secondary rate limit), the same per-repo error isolation (404/410 → skip; 401/403 →
  fatal), and the same dirty-data tolerance.
- **Wire releases into the pipeline** (`scheduler-cli` capability): `run_pipeline` now collects both
  issues and releases per repo and concatenates them into the single `list[RawItem]` that flows into
  the existing delta → summarize → render → deliver path. No stage module imports another (AC-7-002
  preserved); `pipeline.py` remains the only cross-stage importer.
- Documentation: README gains a short note that the digest now includes Releases and how release
  identity/lookback works.

## Capabilities

### New Capabilities
- None. This change adds requirements to existing capabilities (no new pipeline stage, no new port).

### Modified Capabilities
- **`github-collector`** — ADDED requirements only: fetch releases, map release JSON → `RawItem`,
  release cutoff/pagination, and reaffirmation that the new path reuses the existing auth /
  rate-limit / error-isolation / pure-I/O contract. No existing issue requirement changes behavior;
  the delta is purely additive. Delta spec: `specs/github-collector/spec.md`.
- **`scheduler-cli`** — MODIFIED requirement: the `run_pipeline` orchestration now collects releases
  in addition to issues per repo and concatenates them before the delta/summarize/render steps. This
  is the pipeline-wiring home, consistent with the cross-spec rule that orchestration logic lives in
  `pipeline.py` only (same placement as v2-001-delta-filter). Delta spec: `specs/scheduler-cli/spec.md`.

> **Explicitly NOT modified — `digest-renderer`.** The living renderer already renders `"release"`
> items under `### Release (N)` (`GROUP_ORDER = ["issue","discussion","release"]`, AC-5-006 /
> AC-5-011). Adding a MODIFIED renderer delta would either be a no-op (rejected by `openspec
> validate`, which requires a MODIFIED requirement to actually differ) or misrepresent existing
> behavior. This deviates from the kickoff task note ("digest-renderer MODIFIED delta") on purpose —
> the renderer is already release-ready. See Assumptions / Handoff.

## Impact

- **New code**: `GitHubCollector.fetch_releases(repo, lookback_days)` + a `_map_release()` helper in
  `src/osspulse/github/client.py` (mirrors the existing `fetch_items` / `_map_item`). The
  `GitHubClient` Protocol is **unchanged** — `fetch_releases` is an adapter-only method, following
  summarizer-llm-4 ADR-005 (batch helper on the adapter, not on the frozen Protocol).
- **Touched code**: `pipeline._collect_all` calls `collector.fetch_releases(repo_name, lookback_days)`
  alongside `fetch_items` and extends the per-repo item list before `_partition_new` / `mark_seen`.
- **Config**: **no new `Config` field** — releases are always-on in V2, and release fetching reuses
  the existing `CollectorConfig` tunables (per the constraint "no new `Config` field to pass adapter
  tunables — use pipeline-level derivation"; matches github-collector-2 ADR-001 discipline).
- **External**: one additional GitHub REST call per repo per run (`/releases`), authenticated with
  the same `GITHUB_TOKEN`. At 5000 req/hr this is negligible for a personal watchlist.
- **No change** to state store, delta filter, summarizer, renderer, or delivery.

---

## Non-Goals

- ❌ **No digest-renderer change** — the renderer already handles `"release"` (AC-5-006 / AC-5-011).
- ❌ **No per-source enable/disable config toggle** (`[sources]`) in this change — releases are
  collected by default (always-on). A future toggle is possible but out of scope here (avoids adding
  `Config` surface for a feature the spec asks to simply "add").
- ❌ **No Discussions source** — Discussions (GraphQL) are a separate V2 change; this change is
  Releases (REST) only.
- ❌ **No release-asset / binary download** — only the release metadata + changelog `body` text are
  collected; downloadable assets are ignored.
- ❌ **No new summarization behavior for releases** — a release is summarized exactly like an issue
  (title + body via `summarize_items`), reusing the 8000-char input cap.
- ❌ **No change to release ordering vs issues in the digest** — the fixed group order
  Issues → Discussions → Releases (AC-5-006) is preserved; releases appear after issues per repo.

## Assumptions

- **[CONFIRMED]** Releases are fetched from the GitHub REST endpoint
  `GET /repos/{owner}/{repo}/releases`. *(Source: kickoff task + GitHub REST API.)*
- **[CONFIRMED]** The digest renderer needs no change — it already emits `### Release (N)` for
  `item_type = "release"`. *(Source: digest-renderer living spec AC-5-006 / AC-5-011 + `renderer.py`
  `GROUP_ORDER`.)*
- **[CONFIRMED]** State store, delta filter and summarizer accept `item_type = "release"` unchanged.
  *(Source: state-store-3 key contract; v2-001 pipeline delta; summarizer-llm-4 8000-char cap.)*
- **[CONFIRMED]** Release **inclusion** is decided by `published_at` within the lookback window;
  **draft** releases (`published_at == null`) are excluded because a draft is not a published
  release. *(User-confirmed at SPEC-LOCK, 2026-07-06.)*
- **[CONFIRMED]** **Prereleases** are included (a prerelease is still a release the contributor should
  see). *(User-confirmed at SPEC-LOCK, 2026-07-06.)*
- **[CONFIRMED]** `RawItem.item_id = tag_name` for releases (stable, unique-per-repo, human-readable —
  renders as `#v1.2.0`), rather than the numeric release `id` (which would render as an opaque
  `#123456789`). This keeps the renderer unchanged while producing a readable line. *(User-confirmed
  at SPEC-LOCK, 2026-07-06. Tradeoff: a deleted-then-recreated tag collides as "previously-seen";
  accepted as rare — RISK-004.)*
- **[CONFIRMED]** `RawItem.created_at = published_at` (raw ISO string), used for the lookback cutoff.
  *(User-confirmed at SPEC-LOCK, 2026-07-06.)*
- **[CONFIRMED]** The `/releases` endpoint returns releases newest-first (created-desc), so the same
  per-item early-stop-at-cutoff pagination used for issues applies. **User-confirmed at SPEC-LOCK
  (2026-07-06): early-stop is accepted.** Because inclusion keys on `published_at` while ordering is
  by `created_at`, a release created long ago but **published** recently could in principle be missed
  by early-stop; this remains flagged as **RISK-002 for the architect to resolve at S3** (accept the
  small risk under the `max_items_per_repo` bound, or disable early-stop for releases and filter each
  page by `published_at`). The AC is CONFIRMED; the ordering-strategy tradeoff is a design decision
  deferred to S3, not a spec ambiguity.

## Edge Cases

1. **State/input** — draft release (`published_at == null`) → skipped (not a published release).
2. **State/input** — prerelease → included (still a release).
3. **Data integrity** — release with `null` name → `title` falls back to `tag_name`.
4. **Data integrity** — release with `null` body → `body = ""` (no crash; summarizer/renderer degrade).
5. **Data integrity** — release with `null` `html_url` → `url = ""` (renderer omits the `[link]`).
6. **Data integrity** — release JSON missing BOTH `tag_name` and `id` → skipped (cannot key), no crash.
7. **Input boundary** — very long changelog `body` (e.g. 50 KB) → truncated to 8000 chars by the
   summarizer's existing `input_char_cap`; the Collector does no truncation of its own.
8. **State** — repo with releases disabled / zero releases → empty list, no error.
9. **Integration** — `404`/`410` on `/releases` (repo gone/renamed) → skip repo, run continues.
10. **Integration** — rate limit hit on `/releases` → same backoff; terminal `RateLimitError` →
    partial results still delivered (reuses AC-7-017).
11. **Integration / ordering** — a release created long ago but published within the window could be
    missed by created-desc early-stop (RISK-002); architect resolves the ordering strategy.
12. **State transition** — a release already seen on a prior run → suppressed by the delta filter
    (identity `repo + "release" + tag_name`), inherited from v2-001.
13. **Data integrity** — a tag deleted then recreated with the same name → treated as previously-seen
    (identity collision); accepted as rare for a single-operator tool.
14. **Concurrency / isolation** — two repos, one's `/releases` fetch fails while its `/issues`
    succeeds → the failure is isolated (WARN + skip releases for that repo); issues already collected
    are not lost.
15. **Rate budget** — adding `/releases` doubles the GitHub calls per repo (2 endpoints); fine under
    the 5000 req/hr authenticated limit for a watchlist, noted for very large watchlists.
16. **Config** — `delta_enabled = false` → all releases render every run (no suppression), exactly
    like V1 issue behavior; inherited from v2-001.

## Early Risk Flags

STRIDE gate: **SKIPPED** (`security.stride_analysis = auto`; this change adds **no new attack
surface** — it reuses the existing authenticated, GET-only, TLS-on GitHub client from
github-collector-2, no new token handling, no PII, no upload, no admin). The relevant existing
invariants are reaffirmed rather than re-derived:

- **RISK-001 — Information disclosure (LOW, reaffirm)**: the new release-fetch path must never write
  the `GITHUB_TOKEN` into logs/errors/returned data. Mitigation: it reuses the same httpx client and
  error-message discipline (github-collector-2 ADR-004, AC-2-009); a test asserts the token value
  never appears in any release-path log/error (BR-V2-003-005).
- **RISK-002 — Correctness / missed data (MEDIUM)**: `published_at`-inclusion vs `created_at`-ordering
  skew could drop a late-published old release from early-stop pagination. Mitigation: architect
  chooses at S3 — accept the small risk bounded by `max_items_per_repo`, or disable early-stop for
  releases and filter each fetched page by `published_at`.
- **RISK-003 — Rate budget / DoS-ish (LOW)**: +1 GitHub call per repo per run. Negligible at
  5000 req/hr; noted for large watchlists.
- **RISK-004 — Data integrity (LOW)**: tag-based identity collision on tag delete+recreate →
  previously-seen suppression. Accepted (rare, single-operator tool).

## Business Rules

- **BR-V2-003-001**: A release SHALL be represented as a `RawItem` with `item_type = "release"` and
  identity `repo + "release" + tag_name`, reusing the state-store key contract (which is
  `item_type`-agnostic) so delta/idempotency apply unchanged.
- **BR-V2-003-002**: Release **inclusion** SHALL be decided by `published_at` within the lookback
  window (`now(UTC) - lookback_days`); a **draft** release (`published_at == null`) SHALL be excluded,
  and a prerelease SHALL be included.
- **BR-V2-003-003**: Release fetching SHALL reuse the existing `CollectorConfig` tunables
  (`max_items_per_repo`, `page_size`, `base_url`, `retry`) with no new config field, and SHALL be
  exposed as an adapter method `fetch_releases` — the `GitHubClient` Protocol SHALL NOT gain a new
  method (frozen, mirroring summarizer-llm-4 ADR-005).
- **BR-V2-003-004**: The digest renderer SHALL remain unchanged — releases render under the existing
  `### Release (N)` group (`GROUP_ORDER` already includes `"release"`, AC-5-006 / AC-5-011); this
  change SHALL NOT add a digest-renderer delta.
- **BR-V2-003-005**: All existing collector security invariants SHALL apply unchanged on the
  release-fetch path: the `GITHUB_TOKEN` is never logged/leaked, only `GET` is issued, TLS
  verification is never disabled, and `base_url` comes only from config (never from the `repo`
  argument or response data). *(github-collector-2 ADR-004 / AC-2-009 / AC-2-013 / AC-2-025.)*
- **BR-V2-003-006**: Releases SHALL be collected by default (always-on) in V2; this change SHALL NOT
  add a per-source enable/disable config field.
- **BR-V2-003-007**: A release-fetch failure for one repo SHALL be isolated exactly like an
  issue-fetch failure (recoverable → WARN + skip that repo's releases + continue; `AuthError` →
  fatal; terminal `RateLimitError` → deliver partial), never aborting items already collected.

## Integration Points

- **INT-V2-003-001**: Collector issues `GET /repos/{owner}/{repo}/releases` on the existing
  authenticated httpx client (github-collector-2), reusing its retry/error-isolation machinery.
- **INT-V2-003-002**: `pipeline.run_pipeline` (`scheduler-cli`) calls `collector.fetch_releases`
  alongside `collector.fetch_items` per repo and concatenates the results into the single
  `list[RawItem]` before the delta → summarize → render → deliver path (pipeline is the only
  cross-stage importer; AC-7-002 preserved).
- **INT-V2-003-003**: Releases consume `JsonFileStateStore.is_seen` / `mark_seen` unchanged
  (`repo + "release" + item_id`); the v2-001 delta filter suppresses previously-seen releases with no
  change.
- **INT-V2-003-004**: Releases consume `LiteLLMSummarizer.summarize_items` unchanged; long changelog
  bodies are truncated by the existing 8000-char `input_char_cap` (summarizer-llm-4), so no
  collector-side truncation is required.

## Figma
Figma: N/A (CLI tool — no visual design surface).

---
## _Structured Extract

### AC List
- AC-V2-003-001: [CONFIRMED] Collector fetches releases via `GET /repos/{owner}/{repo}/releases`, returns `RawItem`s with `item_type = "release"`
- AC-V2-003-002: [CONFIRMED] Releases with `published_at` inside the lookback window are returned; older ones excluded
- AC-V2-003-003: [CONFIRMED] Draft releases (`published_at == null`) are skipped
- AC-V2-003-004: [CONFIRMED] Prereleases are included
- AC-V2-003-005: [CONFIRMED] Repo with no releases returns an empty list, no error
- AC-V2-003-006: [CONFIRMED] `RawItem.item_id = tag_name` for releases
- AC-V2-003-007: [CONFIRMED] `title = name`, falling back to `tag_name` when name is null/empty
- AC-V2-003-008: [CONFIRMED] `body = release body` (changelog), empty string when null
- AC-V2-003-009: [CONFIRMED] `url = html_url`, empty string when null
- AC-V2-003-010: [CONFIRMED] `created_at = published_at`, preserved as the raw ISO string
- AC-V2-003-011: [CONFIRMED] Release missing both `tag_name` and `id` is skipped, no crash
- AC-V2-003-012: [CONFIRMED] Release pagination reuses `Link` rel=next, `max_items_per_repo`, `page_size` from config
- AC-V2-003-013: [CONFIRMED] Releases returned newest-first; early-stop when `published_at` < cutoff (RISK-002 ordering-strategy deferred to architect S3)
- AC-V2-003-014: [CONFIRMED] Info-level truncation log when `max_items_per_repo` is reached for releases
- AC-V2-003-015: [CONFIRMED] Release requests reuse the authenticated GET-only client; token never logged
- AC-V2-003-016: [CONFIRMED] Release fetch reuses the same retry policy (429/5xx/secondary-rate-limit backoff)
- AC-V2-003-017: [CONFIRMED] `404`/`410` on releases → skip repo; `401`/`403` non-rate-limit → fail fast
- AC-V2-003-018: [CONFIRMED] Release fetch touches no state/LLM; `GitHubClient` Protocol unchanged (`fetch_releases` adapter-only)
- AC-V2-003-019: [CONFIRMED] `run_pipeline` collects both issues and releases per repo, concatenated into one list
- AC-V2-003-020: [CONFIRMED] Releases flow through the existing delta filter and are marked seen like any item
- AC-V2-003-021: [CONFIRMED] Releases render under the existing `### Release (N)` group; no renderer change
- AC-V2-003-022: [CONFIRMED] A per-repo release-fetch failure is isolated (WARN + skip), not aborting collected items

### Business Rules
- BR-V2-003-001: Release identity `repo + "release" + tag_name`, reuses state-store key contract
- BR-V2-003-002: Inclusion by `published_at` in window; drafts excluded; prereleases included
- BR-V2-003-003: Reuse `CollectorConfig`; `fetch_releases` adapter-only; Protocol frozen
- BR-V2-003-004: Renderer unchanged — releases use the existing Release group
- BR-V2-003-005: Existing security invariants apply unchanged on the release path
- BR-V2-003-006: Releases always-on; no per-source config toggle
- BR-V2-003-007: Per-repo release-fetch failure isolated like issues

### Integration Points
- INT-V2-003-001: Collector → `GET /repos/{owner}/{repo}/releases` (existing authed client)
- INT-V2-003-002: pipeline → `fetch_releases` alongside `fetch_items`, concatenated
- INT-V2-003-003: releases → state-store `is_seen`/`mark_seen` unchanged (delta from v2-001)
- INT-V2-003-004: releases → summarizer `summarize_items` unchanged (8000-char cap covers changelog)

### Risk Flags
- RISK-001: Token leakage on the new release path — LOW (reaffirm github-collector-2 ADR-004)
- RISK-002: `published_at`-inclusion vs `created_at`-ordering skew misses a late-published release — MEDIUM
- RISK-003: +1 GitHub call per repo — LOW (fine at 5000/hr)
- RISK-004: tag-based identity collision on tag delete+recreate — LOW (accepted)

### Metadata
ticket_id: V2-003
domain: github-collector, scheduler-cli
has_figma: false
has_cms_ui: false
actors: [operator]
ac_count: 22
ac_confirmed: 22
ac_assumed: 0
ac_missing: 0
ac_unclear: 0
edge_cases: 16
stride_gate: SKIPPED
renderer_delta: NONE (already release-ready — AC-5-006/AC-5-011)
