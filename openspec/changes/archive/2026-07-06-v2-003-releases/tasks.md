# Tasks — v2-003-releases (ticket V2-003)

> No HTTP API — no openapi.yaml (ADR-004). No DB/schema layer (JSON state store, item_type-agnostic).
> Work order follows the architecture layering: data/mapping helper → adapter method → pipeline
> wiring → tests. No new module, no new port, no new error class, no renderer/state/config change.

## 1. Release → RawItem mapping (data layer)

- [x] 1.1 Add `_map_release(self, raw: dict, repo: str) -> RawItem | None` to `GitHubCollector`, mirroring `_map_item`. Map `item_type="release"`, `item_id=tag_name`, `title=name or tag_name`, `body=body or ""`, `url=html_url or ""`, `created_at=published_at` (raw ISO string, never reformatted). Return `None` when BOTH `tag_name` and `id` are missing.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-003-006, AC-V2-003-007, AC-V2-003-008, AC-V2-003-009, AC-V2-003-010, AC-V2-003-011_

## 2. Release fetch + pagination (adapter method)

- [x] 2.1 Add `fetch_releases(self, repo: str, lookback_days: int) -> list[RawItem]` to `GitHubCollector`, mirroring `fetch_items`. Compute `cutoff = now(UTC) - lookback_days`; call `_validate_repo(repo)`; build URL `{base_url}/repos/{repo}/releases?per_page={page_size}`; reuse `_request_with_retry`, `_classify` (404/410 → WARN + return `[]`), and `_next_link` for pagination.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-003-001, AC-V2-003-002, AC-V2-003-005, AC-V2-003-012, AC-V2-003-017_
- [x] 2.2 Implement the ADR-001 dual-key loop body: skip drafts (`published_at is None`) with `continue` (no stop); early-stop with `return items` when `_parse_created(created_at) < cutoff` (created-desc order); skip an item when `_parse_created(published_at) < cutoff`; include prereleases (no `prerelease` filter); call `_map_release` and append non-`None`; cap at `max_items_per_repo` with an info truncation log.
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-003-002, AC-V2-003-003, AC-V2-003-004, AC-V2-003-013, AC-V2-003-014_
- [x] 2.3 Confirm the release path reuses the existing security + retry contract with NO new code: same authed httpx client (token never logged/returned), GET-only, TLS on, `base_url` from config only, same `RetryPolicy` object (429/5xx/secondary-rate-limit backoff), same `CollectorError` hierarchy (no new error class), and the `GitHubClient` Protocol in `ports.py` stays unchanged (adapter-only method).
  File: `src/osspulse/github/client.py`
  _Requirements: AC-V2-003-015, AC-V2-003-016, AC-V2-003-018_

## 3. CHECKPOINT — collector unit tests (mid-build human gate)

- [x] 3.1 Unit tests for `_map_release`: each field-mapping + null case — `item_id=tag_name`, `title` fallback to `tag_name`, `body`/`url` null→`""`, `created_at=published_at` unchanged, and skip when both `tag_name`+`id` missing.
  File: `tests/github/test_map_release.py`
  _Requirements: AC-V2-003-006, AC-V2-003-007, AC-V2-003-008, AC-V2-003-009, AC-V2-003-010, AC-V2-003-011_
- [x] 3.2 Unit tests for `fetch_releases` using `httpx.MockTransport` + injected `sleep`: in-window returned; older-than-cutoff excluded; draft skipped (no early-stop); prerelease included; empty repo → `[]`; config tunables drive `per_page`/cap (not literals); early-stop mid-pagination; truncation info-log at cap; 404/410 → `[]`; rate-limit retried then terminal; token value never appears in any log/error line.
  File: `tests/github/test_fetch_releases.py`
  _Requirements: AC-V2-003-001, AC-V2-003-002, AC-V2-003-003, AC-V2-003-004, AC-V2-003-005, AC-V2-003-012, AC-V2-003-013, AC-V2-003-014, AC-V2-003-015, AC-V2-003-016, AC-V2-003-017_
- [x] 3.3 RISK-002 regression test (ADR-001 tripwire): a release with `created_at` before the cutoff but `published_at` within the window, positioned beyond the first page — assert the documented early-stop-on-`created_at` behavior (the accepted miss) so a future reversal to Option B is caught.
  File: `tests/github/test_fetch_releases.py`
  _Requirements: AC-V2-003-013_
- [x] 3.4 **CHECKPOINT**: run `pytest tests/github/ -q` + coverage on `client.py` (≥80% lines). STOP for human review of the collector before wiring the pipeline. Confirm ADR-001 stop/include keys and the no-new-error-class / frozen-Protocol invariants hold.
  File: `tests/github/`
  _Requirements: AC-V2-003-001, AC-V2-003-013, AC-V2-003-018_

## 4. Pipeline wiring (orchestration)

- [x] 4.1 In `_collect_all`, inside the existing per-repo `try`, after `fetch_items`, add a narrow inner `try/except` around `collector.fetch_releases(repo_name, config.lookback_days)`: on `(InvalidRepoError, NetworkError, CollectorError)` → `logger.warning("skipped releases for %s: %s", repo_name, type(exc).__name__)` + `releases = []` (issues survive). `AuthError` and terminal `RateLimitError` must NOT be in the inner catch tuple — they propagate to the outer arms (fatal / partial-deliver).
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-003-022_
- [x] 4.2 Concatenate `items = issues + releases`, then keep the existing R1 sequence unchanged: `new, seen = _partition_new(items, state)` BEFORE `state.mark_seen(items)` (full list, never `new`); `all_items.extend(new if config.delta_enabled else items)`. Update the per-repo stats/log to count both sources.
  File: `src/osspulse/pipeline.py`
  _Requirements: AC-V2-003-019, AC-V2-003-020_

## 5. CHECKPOINT — pipeline tests + final gate

- [x] 5.1 Pipeline test: a repo returning 2 issues + 1 release yields 3 `RawItem`s (2 `issue`, 1 `release`) concatenated into one list before the delta step.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-003-019_
- [x] 5.2 Pipeline test: a release rendered+recorded on run 1 (`repo+"release"+tag_name`) is suppressed on run 2 with `delta_enabled=true`; renders under the existing `### Release (N)` group with no renderer change.
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-003-020, AC-V2-003-021_
- [x] 5.3 Pipeline isolation test (AC-022): a repo whose `fetch_releases` raises a recoverable error while `fetch_items` succeeded — assert the repo's issues are still delivered, other repos unaffected, exit 0; and a count-invariant assertion that `mark_seen` is called exactly once per repo with `len(issues)+len(releases)` items (R1 tripwire).
  File: `tests/test_pipeline.py`
  _Requirements: AC-V2-003-022, AC-V2-003-019_
- [x] 5.4 **CHECKPOINT (final)**: full `pytest -q` green, coverage ≥80% lines on `client.py` + `pipeline.py`, and a secret-scan confirming no token value in any log/error across the release path. STOP for human sign-off before S4 exit.
  File: `tests/`
  _Requirements: AC-V2-003-015, AC-V2-003-019, AC-V2-003-020, AC-V2-003-021, AC-V2-003-022_
