## 2026-07-11 — v3-llm-throttle: injection-pattern silent-invariant ordering test

When a timing/throttle mechanism uses injected callables (`sleep`, `clock`) AND has a
placement invariant (throttle must only fire on the real-completion path, after all
early-returns), the critical QA check is reading the `summarize()`/handler body to
verify the ORDERING — not just that individual helpers work. Two dedicated tests
(`test_token_window_cache_hit_not_counted_AC_V3_001_004` + skip variant) guard this
by asserting `_window._entries == []` after a non-LLM path. This pattern (assert the
*negative* — that state is NOT mutated on bypass paths) is the reliable way to catch
silent double-count regressions. Use it whenever a stateful adapter has bypass-first
early-returns.
