## 2026-07-10 — v2-cache-etag: crash-safety tripwire pattern for commit-after-loop

**Context**: V2-007 introduced a single unguarded `commit()` call in `run_pipeline` positioned
after `_collect_all()` returns. This is crash-safety-critical: an AuthError propagating out of
the loop must bypass the commit line so etags.json stays unchanged.

**Lesson**: When a pipeline change has a "must execute AFTER the loop AND must NOT execute on
fatal exception" placement constraint, the correct test structure is TWO complementary tripwire tests:
1. **Success invariant**: call-order tracking via `side_effect` lists to prove commit fires AFTER
   all `mark_seen` calls (not per-repo, not before the loop ends).
2. **Crash-safety invariant**: inject a fatal exception mid-loop and assert `commit.assert_not_called()`.

A single test that only checks "commit called once" misses the crash-safety path.
Pattern: `mark_seen_call_order = []` + `commit_call_order = []` side_effects, then assert ordering.

## 2026-07-10 — v2-cache-etag: _classify enum dual-mapping is a future maintainer trap

**Context**: `_classify(304)→_Action.OK` means BOTH 200 and 304 map to the same action enum
value. The fetch methods branch on `response.status_code == 304` directly, not on the action.

**Lesson**: This "dual mapping + raw status branch" pattern is correct but fragile for future
refactors. QA should explicitly verify that the fetch method branches on `status_code`, not on
the action, and add a code comment in the QA report highlighting it. If a future change adds a
`NOT_MODIFIED` action, the fetch branch MUST be updated too — the existing tests will catch a
silent body-iteration bug only if the mock returns `content=b""` (empty body for 304), not if
it returns a JSON list.

## 2026-07-10 — v2-cache-etag: best-effort store INVERT pattern — use static import scan

**Context**: `etag_store.py` is the deliberate opposite of `state/json_store.py`: corrupt → WARN +
empty (never raise). The risk is that a future developer "improves" it by copying the raise-on-corrupt
pattern from json_store.

**Lesson**: For best-effort components that deliberately invert a fatal peer's behavior, add a static
import-scan test (`test_store_does_not_import_json_store`) that reads the module source and asserts
no `from osspulse.state` / `StateError` import lines. This is cheap, fast, and catches the most
likely accidental regression (copy-paste from json_store.py). Also verify the module docstring
explicitly says "DELIBERATE OPPOSITE of json_store" so the intent survives code review.
