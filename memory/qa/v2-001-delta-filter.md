## 2026-07-03 — v2-001-delta-filter: idempotency test ≠ cross-mode equivalence test

When a spec says "result is byte-identical to V1," two distinct TC designs exist:
- **Idempotency test** (what dev wrote): run `delta_enabled=False` twice → assert both digests
  equal. Proves the path is deterministic. Does NOT prove that False == V1-equivalent behavior
  (a bug that renders differently from V1 could still pass if it does so consistently).
- **Equivalence test** (what the spec asks): run `delta_enabled=False` AND `delta_enabled=True`
  with empty prior state (no items seen yet) → assert both render the same digest.

Pattern to check at review time: if the test body only calls the same function twice with the
same params and asserts equality, it's an idempotency test. The spec likely wants an equivalence
test (two different modes/code paths, same expected output).

**Catch**: the AC may still be adequately covered by the combination of the idempotency test +
a separate count-invariant test + code review that confirms a single conditional. Document as
SHALLOW_TC [AI-DETECTABLE] (Low), not blocking if code review fills the gap. Always check
whether the spec has a "byte-identical / same as V1 / same as without the feature" claim and
ensure the test exercises both paths over the same input, not just the same path twice.
