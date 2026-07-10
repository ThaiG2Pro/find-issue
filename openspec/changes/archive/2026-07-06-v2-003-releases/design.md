## Sketch — Gap Analysis

**No critical gaps found.** The change is fully satisfiable against the existing codebase; the
work concentrates in one adapter method + one pipeline wiring line, mirroring `fetch_items`.

Codebase grounding (read at sketch):
- `src/osspulse/github/client.py` — `GitHubCollector.fetch_items` + `_map_item` are the exact
  mirrors for the new `fetch_releases` + `_map_release`. Reusable as-is: `_validate_repo`,
  `_request_with_retry`, `_classify`, `_next_link`, `_backoff_seconds`, `_parse_created`.
- `src/osspulse/pipeline.py` — `_collect_all` per-repo `try/except` is the wiring site; the
  v2-001 **R1 partition-before-mark_seen** invariant lives here and MUST be preserved.
- `src/osspulse/render/renderer.py` — `GROUP_ORDER = ["issue","discussion","release"]` already
  emits `### Release (N)` (confirmed); **no renderer delta** (BR-V2-003-004).
- `src/osspulse/github/config.py` — `CollectorConfig` (`max_items_per_repo`, `page_size`,
  `base_url`, `retry`) is reused with **no new field** (BR-V2-003-003).
- `src/osspulse/ports.py` — `GitHubClient` Protocol has only `fetch_items`; stays **frozen**
  (`fetch_releases` is adapter-only, AC-V2-003-018).
- `src/osspulse/models.py` — `RawItem.item_type` doc already lists `"release"`; no model change.

Non-gaps explicitly classified (per governance conflict handling):
- **RISK-002** is a *design decision* (ADR-001 below), not a spec ambiguity. AC-V2-003-013 is
  CONFIRMED and mandates early-stop; the accept-risk-vs-full-scan tradeoff is resolved here.
- **No `openapi.yaml`** — OSS Pulse is a CLI tool with **no HTTP API** (internal stage contracts
  are Python dataclasses). Every prior change (github-collector-2 … v2-002-cron-scheduler) ships
  no `openapi.yaml`. The design-rule "keep a SEPARATE openapi.yaml" is conditional ("*if the
  change has an API*") — recorded as a documented non-deviation in §Architecture Overview, not a
  gap. See ADR-004.

---

## Context

The V1 pipeline (`osspulse run`) collects, summarizes, renders, and delivers new **issues** per
watched repo. This change adds **releases** as a first-class source (PROJECT_SPEC §5 / V2) so the
digest shows "what shipped" alongside "what's being discussed".

The pipeline downstream of the collector was deliberately built **item-type-agnostic**:
- State store keys on `repo + item_type + item_id` — accepts `"release"` unchanged.
- The v2-001 delta filter (`_partition_new` in `pipeline.py`) filters any `item_type`.
- The summarizer caps input at 8000 chars (`input_char_cap`) — long changelogs handled.
- The renderer already ships `"release"` in `GROUP_ORDER`.

So the delta is: teach the **Collector** to fetch + map GitHub releases, and wire **one extra
call** into `pipeline._collect_all`. All artifacts reused unchanged downstream.

Constraints (from `context/architecture.md`, prior ADRs, and architect memory):
- `GitHubClient` Protocol is **frozen** — new fetch method goes on the adapter only
  (summarizer-llm-4 ADR-005 discipline).
- **No new `Config`/`CollectorConfig` field** — reuse existing tunables (github-collector-2
  ADR-001 / v2-002 derive-don't-add discipline).
- `pipeline.py` is the **only** cross-stage importer (AC-7-002); no stage imports another.
- The v2-001 **R1 invariant**: partition new items BEFORE `mark_seen`; `mark_seen` always records
  the FULL fetched list, never just `new`.
- Per-module one-error-class convention: the collector's `CollectorError` hierarchy is reused;
  **no new error class** is introduced (releases raise the same errors as issues).

## Goals / Non-Goals

**Goals:**
- Add `GitHubCollector.fetch_releases(repo, lookback_days) -> list[RawItem]` (adapter-only).
- Map release JSON → `RawItem` with `item_type="release"`, null-safe on every field.
- Reuse the collector's pagination / cutoff / retry / security / error-isolation machinery
  unchanged on the release path.
- Wire releases into `pipeline._collect_all` under the SAME per-repo isolation boundary as issues,
  preserving the R1 partition-before-mark_seen invariant.

**Non-Goals:**
- No digest-renderer delta (BR-V2-003-004 — already release-ready).
- No `openapi.yaml` (no HTTP API — CLI tool).
- No new `Config`/`CollectorConfig` field, no per-source enable/disable toggle (BR-V2-003-006).
- No `GitHubClient` Protocol change (AC-V2-003-018).
- No Discussions source, no release-asset download, no release-specific summarization.
- No new error class — releases reuse the `CollectorError` hierarchy.

## Architecture Overview

**Layer touched:** the GitHub Collector adapter (`src/osspulse/github/`) + the pipeline
orchestrator (`src/osspulse/pipeline.py`). No new module, no new port, no new stage.

```
run_pipeline
  └─ _collect_all(config, collector, state)          # pipeline.py — wiring site
       for repo in watched_repos:
         try:
           issues   = collector.fetch_items(repo, lookback_days)     # existing
           releases = collector.fetch_releases(repo, lookback_days)  # NEW (same try/except)
           items    = issues + releases                              # concatenate (AC-019)
           new, seen = _partition_new(items, state)   # R1: BEFORE mark_seen (AC-022 safe)
           state.mark_seen(items)                      # full list, never `new`
           all_items.extend(new if delta_enabled else items)
         except AuthError:        raise               # fatal (AC-7-005)
         except RateLimitError:   break               # partial deliver (AC-7-017)
         except (InvalidRepoError, NetworkError, CollectorError): skip repo (AC-7-004 / AC-022)
```

**Reused (no change):**
- State store `is_seen`/`mark_seen` (`repo + "release" + tag_name`) — INT-V2-003-003.
- v2-001 delta filter `_partition_new` — item_type-agnostic.
- Summarizer `summarize_items` (8000-char cap covers changelog) — INT-V2-003-004.
- Renderer `### Release (N)` group — AC-V2-003-021.

**Dependencies (from prior changes):** `RawItem` (models), `CollectorConfig` (github-collector-2),
`_partition_new` (v2-001-delta-filter), `GROUP_ORDER` (digest-renderer-5).

**Cross-cutting reuse note:** `fetch_releases` and `fetch_items` share **one** `httpx.Client`
instance (already held on `self._client`) and therefore **one** retry budget per collector — the
pipeline constructs a single `GitHubCollector` per run. No second client is created (resolves the
handoff §3 wiring question).

**API surface:** none. OSS Pulse is a CLI tool; internal contracts are Python dataclasses. No
`openapi.yaml` is produced (see ADR-004). The only external HTTP is the outbound GitHub REST call,
which is not an API this project *exposes*.

## ADRs

### ADR-001 — RISK-002: reconcile `published_at`-inclusion with `created_at`-ordering early-stop

**Context.** AC-V2-003-002 decides inclusion by `published_at` within the lookback window;
AC-V2-003-013 (CONFIRMED) mandates early-stop when a release before the cutoff is encountered,
because the `/releases` endpoint returns releases **newest-first by `created_at`** (GitHub does not
support `sort=published` on this endpoint). A release **created** long ago but **published**
recently sorts late in the created-desc stream, so a naive early-stop keyed on `published_at`
could stop before reaching it and silently drop it. The two candidate stop keys (created vs
published) each have a distinct failure mode.

**Options.**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Early-stop on `created_at`, filter each fetched item by `published_at`** (chosen) | Paginate created-desc; per item, include when `published_at >= cutoff`; **stop** when the item's **`created_at` < cutoff** (mirrors `fetch_items` exactly). Draft (`published_at==null`) skipped without stopping. | Matches the CONFIRMED early-stop AC; identical control-flow to `fetch_items` (max reuse, one mental model); a recently-published release whose `created_at` is still ≥ cutoff is caught; bounded pages | A release created *before* the cutoff but published *within* it is still missed — the residual RISK-002 window |
| **B. Early-stop on `published_at`** | Stop when `published_at < cutoff` | Simplest read | WRONG under created-desc ordering: the first low-`published_at` item can appear before a later high-`published_at` one → drops valid releases unpredictably |
| **C. Disable early-stop; scan all pages, filter by `published_at`, bound only by `max_items_per_repo`** | No cutoff-based stop; page until `Link` ends or cap | Catches every in-window release regardless of create/publish skew | Contradicts the CONFIRMED AC-V2-003-013 (would require an S2 return); unbounded pages on active repos → rate-budget cost (RISK-003); marginal benefit for a single-operator watchlist |

**Decision.** **Option A.** Early-stop keys on **`created_at`** (the actual sort order, so the
"everything after is older" guarantee holds), while **inclusion** keys on **`published_at`** (the
requirement). This mirrors `fetch_items` control-flow one-to-one, maximizing reuse and keeping a
single pagination mental model. The residual RISK-002 window — a release *created* before the
cutoff but *published* within it — is accepted as rare for a single-operator watchlist and bounded
in practice: releases are almost always published at or near creation. Option C is rejected because
it contradicts the CONFIRMED AC-013 (an early-stop AC); flipping it would be an S2-level scope
change, not an S3 decision.

**Consequences.** A regression test (`fetch_releases` with an old-`created_at`/recent-`published_at`
release beyond the first page) documents the accepted miss explicitly, so the behavior is a
recorded decision, not a latent bug. If operators later report missed releases, the mitigation is
Option C behind a config flag — a future change, out of scope here. The stop comparison uses the
existing `_parse_created` helper on `created_at`; the include comparison uses the same helper on
`published_at`.

### ADR-002 — `fetch_releases` placement: adapter method, Protocol frozen

**Context.** The release fetch needs to live somewhere. The `GitHubClient` Protocol
(`ports.py`) currently declares only `fetch_items`.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| **A. Add `fetch_releases` to the adapter only; leave the Protocol frozen** (chosen) | Matches summarizer-llm-4 ADR-005 (batch helper on adapter, not Protocol); the pipeline holds a concrete `GitHubCollector`, so it can call the method directly; keeps the Protocol a minimal seam | The Protocol no longer fully describes the adapter's surface (acceptable — Protocol documents what the pipeline *abstracts over*, not every method) |
| **B. Add `fetch_releases` to the `GitHubClient` Protocol** | Protocol fully mirrors the adapter | Widens a frozen seam for a single concrete impl; violates BR-V2-003-003 + AC-V2-003-018; forces every future fake to implement it |

**Decision.** **Option A** — adapter-only method; `GitHubClient` Protocol stays frozen. Mandated by
AC-V2-003-018 / BR-V2-003-003 and consistent with summarizer-llm-4 ADR-005.

**Consequences.** The pipeline calls `collector.fetch_releases(...)` on the concrete
`GitHubCollector` it constructs — no Protocol widening. Tests inject a fake collector that adds the
method ad-hoc; no Protocol churn.

### ADR-003 — Per-repo isolation across TWO fetches (AC-V2-003-022)

**Context.** Each repo now has two fetches (`fetch_items` + `fetch_releases`). A release-fetch
failure must NOT discard issues already collected for that repo, and must be isolated exactly like
an issue-fetch failure. The v2-001 R1 invariant requires partitioning BEFORE `mark_seen`.

**Options.**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Both fetches inside ONE per-repo `try/except`; concatenate, then partition once, then mark_seen once** (chosen) | `items = fetch_items(...) + fetch_releases(...)` inside the existing try; `_partition_new(items)` then `mark_seen(items)` | Single isolation boundary (both fetches covered by AC-7-004/017/005 arms); R1 preserved (one partition, one mark_seen); minimal diff | If `fetch_items` succeeds but `fetch_releases` raises, the *issues* for that repo are also skipped (both lost together for that repo) — see decision |
| **B. Separate `try/except` per fetch; merge survivors** | Issues survive even if releases fail | Finer-grained isolation | Two mark_seen sites or a deferred-partition dance → easy to violate R1 (partition-after-mark_seen bug); more complex; AC-022 only requires the *other repos* + *already-collected* items survive, not intra-repo split |

**Decision.** **Option A** — one `try/except` per repo covering both fetches; concatenate → partition
once → `mark_seen(items)` once. Reading AC-V2-003-022 precisely: it requires that a release failure
"does not abort **collected items**" and "**issues already collected for that repo (and all other
repos)** are still … delivered". Under Option A, if `fetch_items` runs first and succeeds but
`fetch_releases` raises a recoverable error, the exception unwinds before `items` is assembled, so
that repo contributes nothing — which would fail AC-022's "issues already collected for that repo".

**Refinement (chosen concrete form).** Wrap **only** `fetch_releases` in a narrow inner
`try/except` that logs WARN + yields `[]` on a *recoverable* release error, while `AuthError`
propagates (fatal) and a terminal `RateLimitError` re-raises to the outer handler (partial-deliver
break). This keeps issues already collected for that repo, satisfies AC-022 literally, and still
routes fatal/rate-limit outcomes to the existing outer arms. `_partition_new` + `mark_seen` then run
once on `issues + releases` — R1 preserved.

**Consequences.** The inner guard catches `(InvalidRepoError, NetworkError, CollectorError)` and
`RateLimitError`-as-recoverable only where partial-per-repo is intended; `AuthError` and terminal
`RateLimitError` (backoff exhausted) still reach the outer arms unchanged. A count-invariant test
asserts `mark_seen` is called exactly once per repo with `len(issues)+len(releases)` items, and a
test asserts issues survive a release-fetch failure (AC-022).

### ADR-004 — No `openapi.yaml` for a CLI-only change

**Context.** The architect S3 rules and R5 say "keep a SEPARATE openapi.yaml … *if the change has
an API*". OSS Pulse exposes **no HTTP API**; internal stage contracts are Python dataclasses.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| **A. Produce no `openapi.yaml`; document the internal `fetch_releases` contract in §API Design** (chosen) | Truthful — there is no HTTP surface; consistent with all 9 prior changes (none ship openapi.yaml); avoids a misleading artifact | R5 mentions openapi.yaml (but conditionally) |
| **B. Author an openapi.yaml describing the outbound GitHub call** | Satisfies R5 literally | Misrepresents an *outbound consumed* API as an API this project *exposes*; no consumer; pure ceremony |

**Decision.** **Option A.** The conditional in R5/design-rules ("if the change has an API") is not
met. §API Design documents the internal Python method contract (signature, mapping, errors)
instead. This is a documented, rule-cited non-deviation, not an omission.

**Consequences.** The DESIGN REVIEW cross-artifact-audit runs over spec deltas + design.md +
tasks.md (no openapi.yaml row). `openspec change validate` does not require openapi.yaml.

## API Design

No HTTP API. The change adds one **internal adapter method** and one **private helper**:

```python
# src/osspulse/github/client.py  (on GitHubCollector)

def fetch_releases(self, repo: str, lookback_days: int) -> list[RawItem]:
    """Fetch releases published within the last `lookback_days` for `repo`.

    Pure I/O. Paginates created-desc via Link rel=next; early-stops per-item when
    `created_at` < cutoff (ADR-001); includes an item when `published_at` >= cutoff;
    skips drafts (`published_at is None`); caps at `max_items_per_repo` with an info
    truncation log; returns [] for a skipped repo (404/410). Reuses the same authed
    httpx client, retry policy, and error hierarchy as fetch_items.
    """

def _map_release(self, raw: dict, repo: str) -> RawItem | None:
    """Map a GitHub release dict to RawItem; guard every field.

    Returns None (skip) when BOTH `tag_name` and `id` are missing (cannot key).
    item_id=tag_name; title=name or tag_name; body=body or ""; url=html_url or "";
    created_at=published_at (raw ISO string, unchanged).
    """
```

**Outbound GitHub request (consumed, not exposed):**
`GET {base_url}/repos/{repo}/releases?per_page={page_size}` — created-desc by default (no `sort`
param supported for releases). Same `Authorization: Bearer <token>`, `Accept`,
`X-GitHub-Api-Version` headers as `fetch_items` (set on the shared client at construction).

**Release JSON → RawItem field map (AC-006..011):**

| RawItem field | Source | Null/empty rule | AC |
|---|---|---|---|
| `repo` | validated `owner/repo` arg | — | AC-001 |
| `item_type` | literal `"release"` | — | AC-001 |
| `item_id` | `tag_name` | if missing AND `id` also missing → **skip item** | AC-006 / AC-011 |
| `title` | `name` | `null`/empty → fall back to `tag_name` | AC-007 |
| `body` | `body` | `null` → `""` | AC-008 |
| `url` | `html_url` | `null`/missing → `""` | AC-009 |
| `created_at` | `published_at` | raw ISO string, never reformatted; `null` = draft → excluded upstream | AC-010 / AC-003 |

## Error Mapping

The release path reuses the collector's existing `CollectorError` hierarchy **unchanged** — no new
error class (per the per-module-one-error-class convention; architect memory delivery-6/v2-001).

| HTTP / condition | `_classify` action | Raised | Pipeline handling | AC |
|---|---|---|---|---|
| 200 | OK | — | items returned | AC-001 |
| 404 / 410 | SKIP_REPO | — (returns `[]`) | WARN + empty release list for repo; run continues | AC-017 |
| 429 / 5xx / 403+`X-RateLimit-Remaining:0` | RETRY | `RateLimitError` after budget | terminal → partial deliver (outer arm); mid-budget → backoff+retry | AC-016 / AC-017 |
| 401 / non-rate-limit 403 | FAIL_FAST | `AuthError` | fatal — abort run, no token in message | AC-017 / AC-7-005 |
| transport error | RETRY | `NetworkError` after budget | recoverable → skip repo's releases | AC-017 |
| release-fetch recoverable error (in `_collect_all`) | — | `InvalidRepoError`/`NetworkError`/`CollectorError` | inner guard: WARN + skip **releases only**, issues survive | AC-022 |

Security invariant on every arm: messages carry **status + repo + static reason only** — never the
token, request, or headers (reused from `errors.py` construction; AC-V2-003-015).

## Sequence Flows

**Flow 1 — `fetch_releases` happy path + early-stop (ADR-001):**
```
fetch_releases(repo, lookback_days)
  cutoff = now(UTC) - lookback_days
  _validate_repo(repo)                       # reuse; path-traversal guard
  url = "{base_url}/repos/{repo}/releases?per_page={page_size}"
  items = []
  while url and len(items) < max_items_per_repo:
    resp = _request_with_retry(url, repo)     # reuse: retry/backoff/auth
    if _classify(resp) is SKIP_REPO: WARN; return []      # 404/410 (AC-017)
    for raw in resp.json():
      published = raw.get("published_at")
      if published is None: continue          # draft → skip, do NOT stop (AC-003)
      created = raw.get("created_at")
      if isinstance(created, str) and _parse_created(created) < cutoff:
        return items                          # created-desc early-stop (AC-013, ADR-001)
      if _parse_created(published) < cutoff: continue   # published-old but created-recent → skip item
      item = _map_release(raw, repo)          # may return None (AC-011)
      if item is not None: items.append(item)
      if len(items) >= max_items_per_repo:
        logger.info("truncated at %d for %s", ...); return items   # (AC-014)
    url = _next_link(resp.headers.get("Link"))    # reuse (AC-012)
  return items
```

**Flow 2 — pipeline per-repo isolation across two fetches (ADR-003, AC-022):**
```
for repo in watched_repos:
  try:
    issues = collector.fetch_items(repo_name, lookback_days)   # existing
    try:
      releases = collector.fetch_releases(repo_name, lookback_days)
    except (InvalidRepoError, NetworkError, CollectorError) as exc:
      logger.warning("skipped releases for %s: %s", repo_name, type(exc).__name__)
      releases = []                                            # issues survive (AC-022)
    items = issues + releases                                  # (AC-019)
    new, seen = _partition_new(items, state)                  # R1: BEFORE mark_seen
    state.mark_seen(items)                                     # full list (BR-V2-001-002)
    all_items.extend(new if delta_enabled else items)         # (AC-020)
    ...stats...
  except AuthError: raise                                     # fatal (AC-7-005)
  except RateLimitError: break                                # partial (AC-7-017)
  except (InvalidRepoError, NetworkError, CollectorError) as exc:
    stats["skipped"] += 1; logger.warning("skipped %s: %s", repo_name, type(exc).__name__)
```
Note: `AuthError` from either fetch and a terminal `RateLimitError` from `fetch_releases` propagate
past the inner guard (not in its catch tuple / re-raised) to the outer arms, preserving fatal +
partial-deliver semantics.

## Edge Cases

Mapped from the 16 proposal edge cases:
1. Draft (`published_at==null`) → skipped, does NOT trigger early-stop (Flow 1) — AC-003.
2. Prerelease → included (no filter on `prerelease` flag) — AC-004.
3. `name==null` → `title = tag_name` — AC-007.
4. `body==null` → `body = ""` — AC-008.
5. `html_url==null` → `url = ""` — AC-009.
6. Both `tag_name` and `id` missing → `_map_release` returns None, item skipped — AC-011.
7. Very long changelog → no collector truncation; summarizer 8000-char cap applies — INT-004.
8. Repo with zero releases → `[]`, no error — AC-005.
9. 404/410 on `/releases` → WARN + `[]` for repo, run continues — AC-017.
10. Rate limit on `/releases` → same backoff; terminal → partial deliver — AC-016/017.
11. Old-created/recent-published release beyond early-stop → accepted miss (ADR-001, RISK-002).
12. Release seen on prior run → suppressed by delta filter (`repo+"release"+tag_name`) — AC-020.
13. Tag deleted+recreated same name → treated as seen (identity collision) — accepted (RISK-004).
14. Two repos, one's releases fail while issues succeed → issues survive (Flow 2) — AC-022.
15. +1 GitHub call per repo → shared client + retry budget; fine at 5000/hr — RISK-003.
16. `delta_enabled=false` → all releases render every run (inherited v2-001) — AC-020.

## Performance

- +1 GitHub REST call per repo per run (`/releases`). Negligible at 5000 req/hr authenticated for a
  single-operator watchlist (RISK-003). Both fetches share one `httpx.Client` and one retry budget.
- Pagination bounded by `max_items_per_repo` (cap) AND created-desc early-stop (cutoff) — same
  bound as `fetch_items`. No unbounded page walks.
- No new state/LLM/render work per release beyond what any `RawItem` already incurs.

## Security

STRIDE gate: **SKIPPED** at S2 (`security.stride_analysis=auto`, no new attack surface) — reaffirmed
here. The release path adds no new token handling, no PII, no upload, no admin, no new endpoint.
Reaffirmed invariants (all reused from github-collector-2, no new code path for them):
- **RISK-001 (Info disclosure, LOW):** token never written to logs/errors/returned data. Reused via
  the shared httpx client + `errors.py` static-message construction. A test asserts the token value
  never appears in any release-path log/error (BR-V2-003-005) — AC-V2-003-015.
- Only `GET` issued; TLS never disabled; `base_url` only from config, never from `repo` or response
  data; `repo` validated by `_validate_repo` (path-traversal guard) before any request.
- No new secret, no new config surface.

## Risk Assessment

| Risk | Severity | Mitigation | AC/ADR |
|---|---|---|---|
| RISK-001 token leak on release path | LOW | reuse authed client + static error messages; token-absence test | BR-005 / §Security |
| RISK-002 published-vs-created skew misses a release | MEDIUM | ADR-001 Option A (created_at early-stop, published_at include); documented regression test; bounded, rare | ADR-001 / AC-013 |
| RISK-003 +1 call per repo | LOW | shared client + retry budget; negligible at 5000/hr | §Performance |
| RISK-004 tag delete+recreate identity collision | LOW | accepted (rare, single-operator) | proposal EC-13 |
| R1 violation (partition after mark_seen) | HIGH-if-regressed | one partition + one mark_seen per repo; count-invariant test | ADR-003 |

## Implementation Guide

**Recommended order** (data/helper → adapter method → pipeline wiring → tests):
1. `_map_release(raw, repo)` helper in `client.py` — mirror `_map_item`; null-guards + skip rule.
2. `fetch_releases(repo, lookback_days)` in `client.py` — mirror `fetch_items`; ADR-001 dual-key
   stop/include logic; reuse `_validate_repo`/`_request_with_retry`/`_classify`/`_next_link`.
3. Wire into `pipeline._collect_all` — inner `try/except` around `fetch_releases`; concatenate
   before `_partition_new`; keep `mark_seen(items)` single-call (ADR-003, R1).
4. Unit tests for `_map_release` (each null/skip case) + `fetch_releases` (window, draft, prerelease,
   early-stop, truncation, 404, rate-limit, token-absence, RISK-002 miss).
5. Pipeline tests: both-sources concatenation (AC-019), delta suppression (AC-020), release-fetch
   isolation preserves issues (AC-022), mark_seen count-invariant.

**Patterns to follow (with file paths):**
- Mirror `GitHubCollector.fetch_items` / `_map_item` in `src/osspulse/github/client.py` — same
  control flow, same helpers, same error semantics.
- Reuse `_parse_created` (`client.py`) for BOTH the `created_at` stop comparison and the
  `published_at` include comparison.
- Preserve the v2-001 R1 pattern in `src/osspulse/pipeline.py`: `_partition_new` BEFORE `mark_seen`;
  `mark_seen` gets the FULL concatenated list.
- Mock the httpx layer with `MockTransport` + injected `sleep` (github-collector-2 ADR-005) so
  retries never wait in tests.

**Gotchas:**
- Do NOT stop pagination on a draft (`published_at is None`) — `continue`, do not `return`.
- Early-stop compares **`created_at`**, not `published_at` (ADR-001) — reversing this reopens the
  Option-B bug. Add the RISK-002 regression test as a tripwire.
- `mark_seen` must be called exactly once per repo with issues+releases — a second call or passing
  `new` violates the R1 invariant (v2-001 count-invariant test).
- `AuthError` and terminal `RateLimitError` from `fetch_releases` must NOT be swallowed by the inner
  guard — keep them out of its catch tuple / re-raise.
- Do NOT open a digest-renderer delta — the renderer is already release-ready (BR-V2-003-004).
- Do NOT add a `sort=published` query param — the `/releases` endpoint does not support it; that is
  the entire premise of ADR-001.
