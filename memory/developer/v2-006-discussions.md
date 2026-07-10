## 2026-07-09 — v2-006-discussions: MagicMock compatibility when adding a new method to _collect_all

When a new method (`fetch_discussions`) is wired into `_collect_all` and the return value is
concatenated with other lists (`issues + releases + discussions`), all existing tests that use a
`MagicMock` collector MUST have `mock_collector.fetch_discussions.return_value = []` added.
Without this, `MagicMock()` (the auto-created attribute) is returned and `list + MagicMock` raises
a `TypeError` caught by the pipeline's `except CollectorError` arm → silently collected=0.
The symptom is test failures like "assert 'Issue 1' in '# OSS Pulse Digest\n\nNo new items…'" —
items disappear rather than an explicit error. Use sed to bulk-add the stub after each existing
`fetch_releases.return_value = []` line. Watch for indented contexts (for/def blocks) where sed
produces incorrect indentation — inspect and fix those manually.

## 2026-07-09 — v2-006-discussions: ADR-003 null-shape-BEFORE-errors-raise is a test-pinned invariant

The `_classify_graphql` check order (null shape → skip; then errors → raise; then map) is
load-bearing. A disabled-Discussions repo carries BOTH a null `discussions` connection AND an
`errors` entry. If the order is reversed, the run crashes instead of gracefully skipping. Pin this
with a dedicated test (`test_disabled_null_shape_detected_BEFORE_errors_raise`) that sends a
payload with both conditions and asserts the result is `[]` (not a raised exception).

## 2026-07-09 — v2-006-discussions: GraphQL classify should return connection dict, not just nodes

When a GraphQL 200-payload classifier needs to feed both `nodes` AND `pageInfo` to the cursor loop,
return the full `discussions` connection dict (not just the nodes list). If only nodes are returned,
the caller has no `pageInfo` for cursor advance. The design pseudocode sometimes simplifies to
`list[dict]` but the correct return is the connection object; the outer loop calls
`conn.get("nodes") or []` and `conn.get("pageInfo") or {}` safely.
