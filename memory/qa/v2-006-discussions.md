## 2026-07-09 — v2-006-discussions: shape-first null-check tripwire for GraphQL 200-with-errors

**Lesson**: When a GraphQL 200 response can carry BOTH a null connection AND an errors array
(disabled-feature payload), the null-shape check MUST precede the errors-raise check. The
dedicated `test_disabled_null_shape_detected_BEFORE_errors_raise` test (payload with BOTH
null connection AND non-RATE_LIMITED errors → returns [] not raises) is the canonical tripwire
pattern for ADR-003-style "check order is load-bearing" scenarios. Always request this tripwire
for any GraphQL 200-with-errors classification path.

## 2026-07-09 — v2-006-discussions: two-arm CollectorError catch with fatal re-raise

**Lesson** (reinforces v2-003 lesson): Inner guards wrapping per-source collectors must use the
two-arm pattern: `except (InvalidRepoError, NetworkError)` first, then `except CollectorError`
with `isinstance(exc, (AuthError, RateLimitError)): raise`. Do NOT simplify to a single
`except CollectorError` — AuthError ⊂ CollectorError and MUST NOT be swallowed. QA should
always verify BOTH fatal subclasses (AuthError + RateLimitError) are tested individually in
pipeline tests when a new inner guard is added.

## 2026-07-09 — v2-006-discussions: _classify_graphql return-type deviation is safe

**Lesson**: When a classifier returns a connection dict (nodes+pageInfo) instead of just nodes,
the outer loop calling `conn.get("nodes") or []` is safe. The semantic contract is preserved.
This deviation pattern (returning a richer dict for cursor pagination) is a valid trade-off when
the connection object is needed downstream. Not a bug; document as minor deviation in
dev-test-report.md Design Deviations section.

## 2026-07-09 — v2-006-discussions: token-not-in-POST-body test pattern

**Lesson**: For GraphQL paths, assert token absence at three layers: (1) raw POST body bytes —
`requests_captured[0].content.decode()`; (2) log lines — `caplog.records`; (3) error message
strings — `str(exc_info.value)`. All three are present in this change. The body-bytes test is
the most important because logs/errors might be suppressed in production but the POST body is
always sent. Reuse this 3-layer pattern for any future GraphQL or POST-with-auth path.
