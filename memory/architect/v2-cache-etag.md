# memory/architect — v2-cache-etag (V2-007)

## 2026-07-10 — v2-cache-etag: a best-effort sibling store must INVERT the fatal store's corruption handling, and say so in an ADR

When adding a second on-disk file next to an existing fatal-on-corrupt store (`state.json`), the
reflex is to reuse the existing `load()`. That is a trap: an *optimization* file (ETag cache) must
degrade to empty+WARN, never raise, or a corrupt optimization file can abort a run whose correctness
never depended on it. Copy the *atomic write* (`mkstemp(dir=parent)`→`fsync`→`os.replace`), but
INVERT the *read* path. Make it an explicit ADR + a top-of-module comment so a "consistency" refactor
at S4 doesn't re-introduce the raise.

## 2026-07-10 — v2-cache-etag: crash-safety of a cross-run cache is a COMMIT-PLACEMENT decision, not a data-structure one

The lost-item risk (persist a validator for items fetched-but-not-yet-`mark_seen`-recorded) is solved
purely by *where* the durable write happens: in-memory `set()` during fetch + one `commit()` in the
orchestrator AFTER the durable-record step, UNGUARDED so a fatal exception propagates before it. Don't
wrap it in try/except (hides the fatal error), don't move it per-item or per-repo. The regression
tripwire is a single pipeline test: `commit()` called once after the loop AND NOT called when a fatal
error fires mid-loop. Pattern reusable for any "persist-only-after-the-authoritative-record" cache.

## 2026-07-10 — v2-cache-etag: two OK-mapped statuses must be distinguished on RAW status, not on the classified action

Mapping `304`→`_Action.OK` (alongside `200`) keeps it out of the retry/fail-fast machinery, but the
caller must then branch on `response.status_code == 304` vs `200` — branching on the `_Action` alone
would try to paginate a bodiless `304`. General rule: when you fold a new status into an existing
coarse action enum, the divergent behavior moves to the call site's raw-status check.
