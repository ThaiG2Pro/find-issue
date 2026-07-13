# Dev Test Report — V3-003 `v3-upstash-state`

> Generated: 2026-07-11 · Phase: S4 · Agent: developer · Rigor: lite · Scope: tiny

---

## 1. Summary

| Metric | Value |
|--------|-------|
| Tasks completed | 7/7 (all required) |
| Tests added | 39 new (27 upstash_store + 12 pipeline_upstash) |
| Total tests | 658 passing, 0 failing |
| Coverage | 96.17% (≥ 80% required) |
| `upstash_store.py` coverage | 94% |
| `pipeline.py` coverage | 94% |
| Lint | ✅ 0 ruff errors |
| Format | ✅ ruff format clean |
| Design deviations | 0 major / 0 minor |

---

## 2. Implementation Overview

### Files changed / created

| File | Change |
|------|--------|
| `pyproject.toml` | Added `upstash-redis>=1.7,<2` dependency |
| `uv.lock` | Updated (upstash-redis 1.7.0 resolved) |
| `src/osspulse/state/upstash_store.py` | NEW — `UpstashStateStore` adapter |
| `src/osspulse/ports.py` | Added `SeenTracker(Protocol)` (ADR-003) |
| `src/osspulse/pipeline.py` | Added `_build_store(config)`, widened type hints, wired into `run_pipeline` |
| `.env.example` | Documented `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` |
| `README.md` | Added Upstash rows to env var reference table |
| `tests/state/__init__.py` | New package |
| `tests/state/test_upstash_store.py` | 27 tests — all AC-V3-003-001..008 |
| `tests/test_pipeline_upstash.py` | 12 tests — backend selection (AC-004/005), Protocol compliance (AC-008) |

### Key implementation decisions

**ADR-001 — `_build_store(config)`**: Mirrors `_build_etag_cache`/`_build_cache` helper shape but INVERTS the failure behavior — state fails loud (StateError), caches degrade to null. Lazy import of `UpstashStateStore` inside the `if url and token` branch so the package is not required unless Upstash is configured.

**ADR-002 — `is_seen`/`mark_seen`**: Copied `_identity_key` and `_now_utc_z` helpers verbatim from `json_store.py` for byte-for-byte field/value format parity. `mark_seen` uses `HSETNX` per item (set-if-absent) — atomic write-once with no read-modify-write race. Empty list → early return, no client call.

**ADR-003 — `SeenTracker(Protocol)`**: Added to `ports.py`; widened `_partition_new`/`_collect_all` hints from `JsonFileStateStore` to `SeenTracker`. `StateStore` Protocol unchanged (load/save only).

**ADR-004 — fail loud**: Every Upstash client call wrapped in `try/except Exception`; on failure raises `StateError(f"... {type(exc).__name__}")` chained from the original. Never `str(exc)` — prevents tokened-URL leakage. `StateError` is not caught anywhere in `_collect_all` (existing comment preserved, same semantics as pre-existing StateError propagation from json_store).

---

## 3. AC Traceability

| AC | Description | Test(s) |
|----|-------------|---------|
| AC-V3-003-001 | Empty `items` list → no-op, no client call | `test_empty_list_is_noop_no_client_call` |
| AC-V3-003-002 | Key `osspulse:state:{repo}`, field `{item_type}:{item_id}` | `test_key_format_uses_repo_in_key`, `test_field_format_is_item_type_colon_item_id`, `test_key_format_uses_repo_in_key` |
| AC-V3-003-003 | Write-once `first_seen_at` via HSETNX (set-if-absent, no RMW race) | `test_write_once_semantics_via_hsetnx`, `test_mark_seen_value_is_iso_z_timestamp` |
| AC-V3-003-004 | Both env vars set → `UpstashStateStore` selected | `test_returns_upstash_store_when_both_env_vars_set`, `test_upstash_store_receives_url_and_token` |
| AC-V3-003-005 | Either/both env vars absent/empty → `JsonFileStateStore` | `test_returns_json_store_when_no_env_vars`, `test_returns_json_store_when_only_url_set`, `test_returns_json_store_when_only_token_set`, `test_returns_json_store_when_url_is_empty_string`, `test_returns_json_store_when_token_is_empty_string` |
| AC-V3-003-006 | REST URL/token never in error messages or logs | `test_state_error_message_does_not_contain_token`, `test_state_error_message_does_not_contain_url`, `test_state_error_message_no_token_in_mark_seen` |
| AC-V3-003-007 | Runtime Upstash error → `StateError` (fail loud, never silent fallback) | `test_raises_state_error_on_upstash_failure` (is_seen + mark_seen), `test_load_raises_state_error_on_failure`, `test_save_raises_state_error_on_failure` |
| AC-V3-003-008 | `StateStore` Protocol unchanged; `SeenTracker` added; `is_seen`/`mark_seen` NOT added to `StateStore` | `test_state_store_protocol_unchanged`, `test_seen_tracker_protocol_has_is_seen_and_mark_seen`, `test_both_backends_satisfy_seen_tracker_protocol` |

---

## 4. Design Deviations

None. All ADRs implemented as designed.

---

## 5. Self-Review Log

**[HIGH] — R-1 (pipeline AttributeError)**: Verified — `UpstashStateStore` exposes both `is_seen` and `mark_seen` with identical semantics to `JsonFileStateStore`. Round-trip test confirms both methods callable and behave correctly. ✅ RESOLVED

**[HIGH] — R-3 (secret leak)**: Verified — `StateError` messages compose from `type(exc).__name__` only, never `str(exc)`. Tests explicitly assert URL and token substrings are absent from error messages. ✅ RESOLVED

**[HIGH] — ADR-004 (fail loud, no runtime fallback)**: Verified — `_build_store` has no try/except around construction; `UpstashStateStore` wraps all calls with `raise StateError(...) from exc`. No `except Exception → null object` pattern copied from cache builders. ✅ RESOLVED

**[MEDIUM] — Empty-string env var = absent**: Verified — `_build_store` uses truthiness check (`if url and token`) so `""` is treated as absent, same as unset. Tests cover all 4 combinations. ✅ RESOLVED

**[MEDIUM] — `StateStore` Protocol unchanged**: Verified — `ports.py` still has only `load`/`save` on `StateStore`; `SeenTracker` is a SEPARATE Protocol. Test asserts no `is_seen`/`mark_seen` on `StateStore`. ✅ RESOLVED

**[LOW] — `_partition_new` before `mark_seen` invariant**: Unchanged by this CR. `UpstashStateStore` has no in-memory cache, so each `is_seen` is a live HGET — the existing R1 invariant (partition before mark) is still satisfied. ✅ NO CHANGE NEEDED

---

## 6. QA Focus Areas

- **Fail-loud semantics** (AC-007): any network/auth error to Upstash must propagate as `StateError` exit 1, never swallowed.
- **Secret non-disclosure** (AC-006): grep error messages in all `StateError` raise sites to confirm no `str(exc)` and no URL/token in message strings.
- **Backend selection boundary conditions** (AC-005): empty-string env var treated as absent; only BOTH non-empty selects Upstash.
- **Protocol conformance** (AC-008): `StateStore` has no `is_seen`/`mark_seen`; `SeenTracker` has both; both concrete stores satisfy `SeenTracker`.
- **Write-once invariant** (AC-003): `HSETNX` called (not `HSET`) in `mark_seen`.
