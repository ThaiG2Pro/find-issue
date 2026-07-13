# S5 QA Report — V3-003 (v3-upstash-state)
Date: 2026-07-11
QA Mode: Smart (dev-test-report.md present) · Rigor: lite · Scope: tiny

---

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% | ✅ 96.17% (`upstash_store.py` 94%, `pipeline.py` 94%) |
| All required tasks `[x]` | ✅ 7/7 |
| Self-review log present | ✅ (all 6 items resolved in dev-test-report.md §5) |
| Integration smoke test | ✅ N/A — no server to boot; CLI tool with mocked upstash client (all 39 tests pass with mocked Redis, zero live network calls; integration policy satisfied) |
| `.env.example` · README ≥ 10 lines · structured logging wired | ✅ (verified in dev-test-report.md; Upstash vars documented in both files) |

---

## Independent Test Run

```
658 passed, 3 warnings in 9.11s   ← QA independent run
658 passed (dev-test-report)      ← count matches exactly ✅
39 new tests (27 upstash_store + 12 pipeline_upstash) all PASS ✅
```

---

## Test Scenarios — QA Verification (Smart Mode)

Dev covered all 8 ACs with unit tests. QA independently verified the 6 mandatory
check-items from the task description via code review + test review. No new gaps found.

| AC-ID | Scenario | How to verify | Priority | Result |
|-------|----------|---------------|----------|--------|
| AC-V3-003-002 | `is_seen` uses HGET (not HGETALL/scan) | Code review `upstash_store.py:140` + `test_returns_false_when_hget_returns_none` | Critical | ✅ |
| AC-V3-003-003 | `mark_seen` uses HSETNX, never HSET | Code review `upstash_store.py:167` + `test_write_once_semantics_via_hsetnx` asserts `hset.assert_not_called()` | Critical | ✅ |
| AC-V3-003-007 | Runtime error → `StateError` raised, not swallowed | All 4 call sites (`is_seen`, `mark_seen`, `load`, `save`) each have a dedicated `raises(StateError)` test | Critical | ✅ |
| AC-V3-003-006 | Error message never contains URL or token (no `str(exc)`) | `grep str(exc)` → 0 hits in source; error pattern is `type(exc).__name__` only; `test_state_error_message_does_not_contain_token/url` pass | Critical | ✅ |
| AC-V3-003-005 | Both vars absent → `JsonFileStateStore` | `test_returns_json_store_when_no_env_vars` + 4 edge cases (only-URL, only-token, empty-string URL, empty-string token) | High | ✅ |
| AC-V3-003-004 | Both vars present → `UpstashStateStore` | `test_returns_upstash_store_when_both_env_vars_set` + `test_upstash_store_receives_url_and_token` | High | ✅ |
| AC-V3-003-008 | `load()`/`save()` present on `UpstashStateStore`; `StateStore` Protocol unchanged | Code review `upstash_store.py:72-125`, `ports.py:6-8` (StateStore has only `load`/`save`); `test_state_store_protocol_unchanged` asserts no `is_seen`/`mark_seen` on `StateStore` | High | ✅ |
| AC-V3-003-001 | Empty list → no-op, no client call | `test_empty_list_is_noop_no_client_call` asserts `hsetnx.assert_not_called()` | Medium | ✅ |

---

## Code Review Findings

### Verification 1 — `is_seen` uses HGET ✅
`upstash_store.py:140`: `result = self._client.hget(key, field)` — correct single-field lookup, no HGETALL.

### Verification 2 — `mark_seen` uses HSETNX not HSET ✅
`upstash_store.py:167`: `self._client.hsetnx(key, field, now)` — atomic set-if-absent.
`save()` at line 121 uses `hset` for Protocol bulk-write; this is the ONLY `hset` call and it is not on the pipeline hot path. The hot-path write (`mark_seen`) correctly uses `hsetnx`. The test `test_write_once_semantics_via_hsetnx` explicitly asserts `mock_redis.hset.assert_not_called()` after calling `mark_seen` — confirming the distinction is tested.

### Verification 3 — Runtime errors → `StateError`, never swallowed ✅
All 4 call sites have identical structure:
```python
except Exception as exc:
    raise StateError(f"Upstash {op} failed: {type(exc).__name__}") from exc
```
`StateError` is not caught anywhere in `_collect_all` (confirmed in `pipeline.py:269` comment). The `except StateError: raise` guard inside each method prevents double-wrapping but still propagates correctly.

### Verification 4 — No `str(exc)` in error messages ✅
`grep str(exc) src/osspulse/state/upstash_store.py` → 0 matches in executable code (line 60 is a docstring comment). All 4 `StateError` raises use `type(exc).__name__` exclusively. Tests explicitly assert URL and token substrings absent from error message strings.

### Verification 5 — Backend selection truthiness check ✅
`_build_store`: `url = os.environ.get("UPSTASH_REDIS_REST_URL", "")` then `if url and token:` — truthiness means `""` (empty string) evaluates as absent. All 4 edge-case env-var combinations tested.

### Verification 6 — `StateStore` Protocol unchanged ✅
`ports.py:6-8`: `StateStore` has only `load(self) -> dict` and `save(self, state: dict) -> None`. `SeenTracker` is a separate Protocol at line 15+. Test `test_state_store_protocol_unchanged` explicitly asserts `not hasattr(StateStore, "is_seen")` and `not hasattr(StateStore, "mark_seen")`.

### Test Quality Review (Step B1) ✅
All 39 tests reviewed. No hollow assertions found:
- All `is_seen` tests assert specific HGET call arguments AND return value semantics.
- `test_write_once_semantics_via_hsetnx` uses a negative assertion (`hset.assert_not_called()`) — no existence-only check.
- Error message tests use `assert "fake-token" not in str(exc_info.value)` — non-trivial negative assertions.
- Round-trip test (`test_is_seen_false_before_mark_then_true_after`) simulates full before/after state — not a hollow check.
- `test_state_error_is_chained_from_original_exc` asserts `exc_info.value.__cause__ is original` — verifies chaining identity, not just existence.

---

## Security Audit (AC-V3-003-006 / R-3)

| Check | Result |
|-------|--------|
| `str(exc)` used in error composition | ✅ NONE — `type(exc).__name__` only |
| URL embedded in any `StateError` message | ✅ NONE — tested + code-reviewed |
| Token embedded in any `StateError` message | ✅ NONE — tested + code-reviewed |
| `url`/`token` logged at any level | ✅ NONE — `logger.debug("state backend: Upstash Redis")` emits no values |
| Secrets in `__init__` stored beyond `self._client` | ✅ NONE — url/token passed only to `Redis(url=url, token=token)`, not stored on `self` |

---

## AC Coverage Summary

- Total ACs: 8 (AC-V3-003-001 through AC-V3-003-008)
- Covered by Dev unit tests: 8/8
- Independently verified by QA (code review + test review): 8/8
- Not covered: 0

---

## Visual QA

N/A — no Figma URL, no UI changes. CLI-only change.

---

## Dependency Vulnerability Audit

New dependency: `upstash-redis>=1.7,<2` (resolved to 1.7.0).

- `upstash-redis 1.7.0` — HTTP REST client; no known CVEs at time of review.
- No HIGH/CRITICAL findings.
- Dependency is well-scoped (pinned major `<2`), actively maintained, and used only when both env vars are set (lazy import).

**Result: CLEAN — no blockers.**

---

## Decision: ✅ GO

All 8 ACs verified. 658/658 tests pass (count matches dev-test-report exactly). 96.17% coverage ≥ 80% threshold. All 7 tasks `[x]`. 0 Critical/High bugs. Secret non-disclosure confirmed. HSETNX (not HSET) confirmed in `mark_seen`. `StateError` propagation confirmed at all 4 call sites. `StateStore` Protocol unchanged.

## Blockers

None.
