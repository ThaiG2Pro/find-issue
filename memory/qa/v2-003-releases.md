# QA Memory — v2-003-releases

## 2026-07-06 — v2-003-releases: RISK-002 tripwire test semantics

**Lesson**: A regression test that documents an ACCEPTED MISS must PASS (not fail) for the guard to be valid.

`test_risk002_regression_old_created_recent_published_is_missed` asserts that a release IS NOT returned. The test PASSING = the accepted miss is in place (stop key is correctly on `created_at`). If the test FAILS, someone reversed the stop key to `published_at` — that is the bug.

Pattern to watch: when a test name says "...is_missed", it may be documenting accepted behavior, not a failure to fix. Read the docstring before "fixing" it.

**Applicable to**: any collector with dual-key pagination (early-stop key ≠ inclusion key).

---

## 2026-07-06 — v2-003-releases: two-arm catch pattern for fatal subclass isolation

**Lesson**: When `FatalError ⊂ BaseError`, catching `BaseError` in an inner guard silently swallows the fatal error. Use a two-arm pattern instead.

```python
# Design said: except (TypeA, TypeB, BaseError)  ← WRONG: swallows AuthError
# Correct:
except (TypeA, TypeB) as exc:
    handle_recoverable(exc)
except BaseError as exc:
    if isinstance(exc, (FatalError, TerminalError)):
        raise  # let it escape to the outer handler
    handle_recoverable(exc)
```

This pattern is load-bearing. If a future refactor "simplifies" it to a single catch tuple, it will swallow fatal errors silently.

**Applicable to**: any inner guard wrapping a call whose error hierarchy has a fatal subclass nested under a recoverable base.

---

## 2026-07-06 — v2-003-releases: proposal "What Changes" documentation notes are not formal ACs

**Lesson**: The proposal's prose description (§"What Changes") often mentions documentation side-effects (e.g. "README gains a note"). These are **not** automatically ACs. If they're not in tasks.md or the spec's AC list, they're not testable requirements and don't block GO.

Flag them as non-blocking observations in the QA report. Recommend them as S6 follow-ups.

**Applicable to**: all features with documentation side-effects described in the proposal but not formalized as ACs.
