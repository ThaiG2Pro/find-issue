# Glossary — v2-003-releases (ticket V2-003)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| Release (item) | A GitHub release (tag + name + changelog body) collected from `GET /repos/{owner}/{repo}/releases` and represented as a `RawItem` with `item_type = "release"`. The third source after issues; discussions remain a separate V2 change. | analyst | AC-V2-003-001 | S1 |
| Release identity | The delta/idempotency key for a release: `repo + "release" + tag_name`, reusing the state-store key contract (which is `item_type`-agnostic). `tag_name` is chosen over the numeric release `id` so the digest renders `#v1.2.0` rather than an opaque number. | analyst | BR-V2-003-001 | S1 |
| published_at (inclusion) | The timestamp that decides whether a release is inside the lookback window; mapped to `RawItem.created_at` and compared against `now(UTC) - lookback_days`. A `null` `published_at` marks a draft. | analyst | BR-V2-003-002 | S1 |
| Draft release | A release with `published_at == null` (not yet published); EXCLUDED from collection because it is not a published release. | analyst | AC-V2-003-003 | S1 |
| Prerelease | A release with `prerelease = true`; INCLUDED in collection (still a release the contributor should see). | analyst | AC-V2-003-004 | S1 |
| fetch_releases | The new Collector adapter method `fetch_releases(repo, lookback_days) -> list[RawItem]` mirroring `fetch_items`; adapter-only, NOT added to the frozen `GitHubClient` Protocol (per summarizer-llm-4 ADR-005). | analyst | AC-V2-003-018 | S1 |
| Changelog body | The release `body` field (markdown release notes); mapped to `RawItem.body`, `""` when null. Long changelogs are capped by the summarizer's existing 8000-char `input_char_cap` — no collector-side truncation. | analyst | INT-V2-003-004 | S1 |
| Renderer release group | The existing `### Release (N)` group the digest renderer already emits for `item_type = "release"` (`GROUP_ORDER = ["issue","discussion","release"]`, living AC-5-006/AC-5-011). This change adds NO renderer delta. | analyst | BR-V2-003-004 | S1 |
| published-vs-created skew | The correctness risk (RISK-002) that a release created long ago but published recently could be missed by created-desc early-stop pagination; the architect resolves the ordering strategy at S3. | analyst | AC-V2-003-013 | S1 |

## S2 terms

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| SPEC-LOCK sign-off | User confirmation (2026-07-06) that flips the 7 [ASSUMED] release ACs (draft-exclusion, prerelease-inclusion, item_id=tag_name, title fallback, created_at=published_at, newest-first early-stop, per-repo isolation) to [CONFIRMED]. The RISK-002 ordering-strategy tradeoff stays open for the architect at S3. | analyst | AC-V2-003-003, AC-V2-003-013 | S2 |

## S3 terms

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| dual-key pagination | The ADR-001 strategy for `fetch_releases`: pagination **early-stop** compares `created_at` (the endpoint's actual newest-first sort key) while **inclusion** compares `published_at` (the requirement). Reversing the stop key to `published_at` reopens the Option-B bug. | architect | ADR-001, AC-V2-003-013 | S3 |
| RISK-002 residual miss | The accepted, bounded data-miss under ADR-001 Option A: a release **created before** the lookback window but **published within** it can be skipped by created-desc early-stop. Rare for a single-operator watchlist; pinned by a regression test rather than eliminated. | architect | ADR-001 | S3 |
| inner release guard | The narrow `try/except` in `_collect_all` wrapping ONLY `fetch_releases`: catches `(InvalidRepoError, NetworkError, CollectorError)` → WARN + `releases=[]` so issues already collected for the repo survive (AC-022); `AuthError` + terminal `RateLimitError` deliberately excluded so they reach the outer fatal/partial arms. | architect | ADR-003, AC-V2-003-022 | S3 |
| R1 invariant (reaffirmed) | The v2-001 rule preserved by this change: `_partition_new` runs BEFORE `mark_seen`, and `mark_seen` records the FULL concatenated issues+releases list (never just `new`) exactly once per repo. A count-invariant test is the tripwire. | architect | ADR-003, AC-V2-003-019 | S3 |
| _map_release | Private `GitHubCollector` helper mirroring `_map_item`: maps a release dict → `RawItem`, returns `None` when both `tag_name` and `id` are missing. | architect | AC-V2-003-011 | S3 |
