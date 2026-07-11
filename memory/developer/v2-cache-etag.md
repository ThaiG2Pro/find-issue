# Memory — v2-cache-etag (developer, 2026-07-10)

## 2026-07-10 — v2-cache-etag: Port-layer placement of null objects

**Lesson**: When a null/no-op object is designed to be the default ctor arg for a module that
has strict import isolation tests (e.g. `test_collector_is_pure_io_no_state_or_llm`), the null
object must live in the PORT layer (`ports.py`), not in a concrete adapter module. Even if the
design says "put it in adapter X", the isolation test will fail because the import chain now
brings in the entire adapter module. Placing the null object in `ports.py` is architecturally
correct (it IS a port-layer concern) and avoids the isolation violation. The adapter can re-
export it for convenience without triggering the isolation check.

**Pattern**: `_NullXxx` lives in `ports.py` → concrete module uses it via `from osspulse.ports
import _NullXxx` → adapter module re-exports `_NullXxx` for existing callers.

## 2026-07-10 — v2-cache-etag: _classify(304)→OK + branch-on-raw-status pattern

**Lesson**: When an HTTP status (304) is "semantically identical" to another (200) for the
retry/backoff layer but "semantically different" for the caller, the correct pattern is:
1. Map both to the same `_Action.OK` in `_classify` (so retry machinery ignores it)
2. Have the caller branch on `response.status_code == 304` explicitly
This is DIFFERENT from introducing a new `_Action` variant (over-engineered) and different
from branching on `_Action` (would silently pass a bodiless 304 to JSON-parse).

## 2026-07-10 — v2-cache-etag: Crash-safety commit placement with existing test tests

**Lesson**: When implementing a "commit exactly once after a loop, UNGUARDED" pattern, write
TWO tripwire tests immediately:
1. `assert commit() called_once after loop completes normally`
2. `assert commit() NOT called when a fatal error fires mid-loop`
Both are needed because only testing one gives false confidence. The call-order tracking
pattern (side_effect appending to a list) is useful for verifying "after" semantics.
