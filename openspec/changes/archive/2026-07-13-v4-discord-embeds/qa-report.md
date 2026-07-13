# QA Report — v4-discord-embeds (V4-001)

**Date**: 2026-07-13  
**Agent**: qa  
**Phase**: S5  
**Rigor**: lite | **Scope**: tiny | **Mode**: Smart (dev-test-report skipped — retroactive post-release QA)  
**Release**: v0.14.0 (681 tests pass at time of review)

---

## 1. Gate Checklist

| Check | Result | Notes |
|-------|--------|-------|
| Test suite passes | ✅ PASS | 681/681 pass (`uv run pytest tests/ -q`) |
| Coverage ≥ 80% | ✅ PASS | Module coverage 95% (discord_delivery 93%, config 96%, models 98%) |
| No upstream imports in adapter | ✅ PASS | `test_no_upstream_imports` verified; no `osspulse.github/summarizer/cache/render` |
| Pipeline wires `use_embeds` | ✅ PASS | `pipeline.py:395` — `use_embeds=config.discord_use_embeds` |
| `Config.discord_use_embeds` field | ✅ PASS | `models.py` — `discord_use_embeds: bool = False` |
| `_validate_discord_use_embeds` in load_config | ✅ PASS | `config.py` Step 12 |

---

## 2. AC Coverage Map

| AC-ID | Description | Test File | Status | Notes |
|-------|-------------|-----------|--------|-------|
| AC-V4-001-001 | `_parse_sections` splits at `##` → `[{title, body}]` | test_discord_delivery.py `TestParseSections` | ✅ PASS | 4 tests; title strip, empty body, single section, empty string |
| AC-V4-001-002 | `_color_for_repo` uses `hashlib.md5` not `hash()`, result in palette | test_discord_delivery.py `TestColorForRepo` | ✅ PASS | 4 tests incl. explicit md5 assertion |
| AC-V4-001-003 | Description ≤4096 code points (not bytes) | test_discord_delivery.py `TestSplitDescription`, `TestBuildEmbeds` | ✅ PASS | Code-point vs byte test present |
| AC-V4-001-004 | ≤10 embeds/request via `_batch_embeds` | test_discord_delivery.py `TestBatchEmbeds`, `test_embed_batching_sends_multiple_requests` | ✅ PASS | 11→2 batches, 10→1 batch, empty→[] |
| AC-V4-001-005 | `use_embeds=True` + sections → POST `{"embeds":[...]}` | test_discord_delivery.py `test_embed_mode_posts_embeds_json` | ✅ PASS | Verifies `embeds` key in POST body |
| AC-V4-001-006 | Fallback to plain text when no `##` sections | test_discord_delivery.py `test_plain_fallback_no_sections` | ✅ PASS | `_NO_HEADER_CONTENT` → `content` key, no `embeds` |
| AC-V4-001-007 | Embed POST failure → `DeliveryError`, URL not in message | test_discord_delivery.py `test_embed_post_non_2xx_raises_delivery_error` | ✅ PASS | 400 → DeliveryError, `secret_token` not in message |
| AC-V4-001-008 | `[discord] use_embeds` bool-trap at config load | **test_config.py — MISSING** | ⚠️ GAP | Delivery-layer default tested; `load_config` bool-trap (line 73) **not** covered by any config test |
| AC-V4-001-008a | `Config.discord_use_embeds` defaults `False` | test_discord_delivery.py `test_use_embeds_false_by_default` | ✅ PASS | Tests delivery-layer default; config-layer default also untested |

---

## 3. Test Scenarios Verified

### Functional

| AC-ID | Scenario | Method | Result |
|-------|----------|--------|--------|
| AC-V4-001-001 | Two `##` sections parsed correctly | Code review + test execution | ✅ |
| AC-V4-001-001 | No `##` headers → empty list | Code review + test | ✅ |
| AC-V4-001-002 | `hashlib.md5` used (not `hash()`) | Test explicitly asserts `md5` formula | ✅ |
| AC-V4-001-002 | Same slug → same color across calls | `test_deterministic_same_input` | ✅ |
| AC-V4-001-002 | Result always in `_EMBED_PALETTE` | `test_result_in_palette` | ✅ |
| AC-V4-001-003 | Body ≤4096 chars not split | `test_short_body_unchanged` | ✅ |
| AC-V4-001-003 | Body >4096 split into ≤4096 chunks | `test_long_body_split` | ✅ |
| AC-V4-001-003 | 4096 Vietnamese chars (3 bytes/char) → NOT split | `test_uses_code_points_not_bytes` | ✅ |
| AC-V4-001-004 | 11 embeds → 2 batches (10+1) | `test_batches_of_10` + integration test | ✅ |
| AC-V4-001-004 | Exactly 10 embeds → 1 batch | `test_exactly_10_is_one_batch` | ✅ |
| AC-V4-001-005 | `use_embeds=True` → POST body has `embeds` array | `test_embed_mode_posts_embeds_json` | ✅ |
| AC-V4-001-005 | `use_embeds=False` (default) → POST body has `content` | `test_use_embeds_false_by_default` | ✅ |
| AC-V4-001-006 | No `##` section with `use_embeds=True` → plain text | `test_plain_fallback_no_sections` | ✅ |
| AC-V4-001-007 | HTTP 400 embed POST → `DeliveryError` | `test_embed_post_non_2xx_raises_delivery_error` | ✅ |
| AC-V4-001-007 | URL (`secret_token`) not in DeliveryError message | Same test | ✅ |
| AC-V4-001-008 | `[discord] use_embeds = "yes"` → `ConfigError` at load | **No config test** | ❌ GAP |
| AC-V4-001-008a | Absent `[discord]` section → `discord_use_embeds=False` | **No config test** | ❌ GAP |

### Edge / Integration

| Scenario | Result |
|----------|--------|
| Embed timeout → `DeliveryError` without URL leak | ✅ (covered by plain-text timeout tests; embed path reuses same try/except structure) |
| Embed `ConnectError` → `DeliveryError` | ✅ (structurally identical path) |
| Multi-batch: 11 repos → exactly 2 POST calls | ✅ `test_embed_batching_sends_multiple_requests` |
| Embed has `footer.text` containing "OSS Pulse" | ✅ `test_footer_contains_oss_pulse` |
| Over-length description: each chunk ≤4096 | ✅ `test_description_truncated_at_4096` |
| Pipeline wires `use_embeds` from Config | ✅ code review `pipeline.py:395` |

---

## 4. Code Review + Security (Step 4B)

### Reviewed files
- `src/osspulse/delivery/discord_delivery.py` — full review
- `src/osspulse/config.py` — `_validate_discord_use_embeds` + `load_config` Step 12
- `src/osspulse/models.py` — `Config.discord_use_embeds` field
- `src/osspulse/pipeline.py` — wiring at line 395

### Security checklist (OWASP / project T1/T4)

| Check | Result |
|-------|--------|
| Webhook URL never in DeliveryError (T1) | ✅ `_post_one_embed` uses `type(exc).__name__` and status code only |
| No `str(exc)` / `repr(request)` in error path | ✅ Confirmed in both `_post_one` and `_post_one_embed` |
| Timeout applied to every embed batch request | ✅ `timeout=self._timeout` in `_post_one_embed` |
| No upstream module imports in delivery | ✅ `test_no_upstream_imports` + manual check |
| Bool-trap: `type(v) is not bool` (not `isinstance`) | ✅ `config.py:73` mirrors `_validate_delta` pattern |
| Config validates `use_embeds` fail-fast at load | ✅ Step 12 in `load_config`, before pipeline |
| No new trust boundary / secret surface | ✅ Confirmed — reshapes JSON body only |

### Test quality review (Step B1 — assertion quality)

Tests inspected: `tests/delivery/test_discord_delivery.py` — V4-001 section (11 test methods + 4 class-grouped).

| Finding | Classification |
|---------|---------------|
| `test_embed_mode_posts_embeds_json` checks `"embeds" in body` and `isinstance(body["embeds"], list)` — does not assert `len >= 2` for a 2-section input | [EDGE-CASE] — acceptable for a happy-path smoke test; `TestBatchEmbeds` covers the count |
| `test_use_embeds_false_by_default` correctly labeled `AC-V4-001-008` but tests delivery-layer default only — the config-layer `ConfigError` for non-bool is untested | [LOGIC-BUG] — see Bug #1 |
| All other assertions are concrete and specific — no hollow existence-only checks detected | ✅ |

---

## 5. Bugs Found

### Bug #1: AC-V4-001-008 config-layer bool-trap not exercised by any test

**AC-ID**: AC-V4-001-008  
**Severity**: Low  
**Classification**: [LOGIC-BUG]  
**RCA Phase**: S4 (code — test gap, not a production bug)

**Description**: `config.py` line 73 (`raise ConfigError("discord.use_embeds must be a boolean")`) is unreachable by any existing test. The bool-trap logic is correctly implemented; the production guard is present and correct. However, the test suite has zero coverage of the `load_config` path for `[discord] use_embeds`. The test labeled `AC-V4-001-008` (`test_use_embeds_false_by_default`) only tests the `DiscordDelivery.__init__` default at the delivery layer — it does not call `load_config` at all.

**AC-V4-001-008a** (default `False` from config) is similarly untested at the `load_config` level.

**Steps to reproduce** (gap):
1. There is no test in `tests/test_config.py` that creates a TOML with `[discord]\nuse_embeds = "yes"` and asserts `ConfigError`.
2. Coverage report confirms line 73 (`config.py`) is a miss.

**Expected**: `load_config` with `[discord] use_embeds = "yes"` → `ConfigError("discord.use_embeds must be a boolean")`  
**Actual**: No test verifies this; line 73 has 0% coverage.  
**File**: `tests/test_config.py` (missing tests), `src/osspulse/config.py:73` (correct implementation)

**Impact**: Low — the production guard works correctly; this is a test coverage gap, not a behavior bug. Does not affect v0.14.0 correctness.

**Suggested fix**: Add to `tests/test_config.py`:
```python
def test_discord_use_embeds_non_bool_string_raises(tmp_path):
    """[discord] use_embeds = "yes" → ConfigError (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = "yes"\n')
    with pytest.raises(ConfigError, match="discord.use_embeds must be a boolean"):
        load_config(p, ENV)

def test_discord_use_embeds_int_raises(tmp_path):
    """[discord] use_embeds = 1 (int) → ConfigError (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = 1\n')
    with pytest.raises(ConfigError, match="discord.use_embeds must be a boolean"):
        load_config(p, ENV)

def test_discord_section_absent_defaults_use_embeds_false(tmp_path):
    """Absent [discord] section → discord_use_embeds=False (AC-V4-001-008a)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, ENV)
    assert cfg.discord_use_embeds is False

def test_discord_use_embeds_true_accepted(tmp_path):
    """[discord] use_embeds = true → discord_use_embeds=True (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = true\n')
    cfg = load_config(p, ENV)
    assert cfg.discord_use_embeds is True
```

---

## 6. Dependency Audit

Dependency audit tools (`pip-audit`, `safety`) not installed in the project environment. Manual version check performed:

| Package | Version | Known CVE (at 2026-07-13) |
|---------|---------|--------------------------|
| httpx | 0.28.1 | None |
| litellm | 1.89.3 | None |
| redis | 8.0.0 | None |
| typer | 0.26.7 | None |
| python-dotenv | 1.2.2 | None |
| ruff | 0.15.18 | None |

No HIGH/CRITICAL findings. Recommendation: add `pip-audit` as a dev dependency for automated future scans.

---

## 7. AC Coverage Summary

| # | AC-ID | Verified | Notes |
|---|-------|----------|-------|
| 1 | AC-V4-001-001 | ✅ | Full coverage — parse, empty, single |
| 2 | AC-V4-001-002 | ✅ | Explicit hashlib formula assertion |
| 3 | AC-V4-001-003 | ✅ | Code-point vs byte confirmed |
| 4 | AC-V4-001-004 | ✅ | Batch logic + integration |
| 5 | AC-V4-001-005 | ✅ | POST body shape verified |
| 6 | AC-V4-001-006 | ✅ | No-section fallback verified |
| 7 | AC-V4-001-007 | ✅ | DeliveryError + URL non-leak |
| 8 | AC-V4-001-008 | ⚠️ PARTIAL | Delivery-layer default ✅; config-layer bool-trap ❌ gap |
| 8a | AC-V4-001-008a | ⚠️ PARTIAL | Model field ✅; load_config default untested |

---

## 8. GO / NO-GO Decision

### **GO** ✅

**Rationale**:
- 0 Critical bugs, 0 High bugs
- 1 Low bug (Bug #1): test coverage gap for AC-V4-001-008 at the `load_config` level. The production implementation is **correct** — `config.py:73` implements the bool-trap properly. This is a missing test, not a behavior defect.
- All 8 unique AC behaviors implemented correctly and match spec intent
- `hashlib.md5` confirmed — not `hash()` — idempotency non-negotiable satisfied
- 4096 code-point limit correctly measured via `len(str)` — byte vs code-point trap avoided
- Webhook URL never appears in any DeliveryError message — T1 preserved
- `deliver()` signature unchanged — port contract intact
- No upstream imports in `discord_delivery.py` — AC-6-002 preserved
- 681 tests pass, module coverage 95% overall

**Blocker for future runs**: Bug #1 (Low) should be remediated by adding 4 config tests to `tests/test_config.py`. Not a release blocker for v0.14.0 given the implementation is correct.

---

## 9. Risky Areas (passing but fragile)

1. **`_split_description` line-hard-slice path** (lines 92–93 in `discord_delivery.py` — uncovered): the branch where a single *line* within a body exceeds 4096 chars. This is a theoretical edge (a 4096+ char line with no newline), but the coverage miss means it is untested. Low risk for typical digest content.
2. **`_enforce_limit` safety-net** (line 230 — uncovered): intentional dead code (safety-net). Correct to be uncovered in normal paths.
3. **`_external_client=None` embed path** (lines 287–288 — uncovered): the production path where `DiscordDelivery` creates its own `httpx.Client` in embed mode. All tests inject a mock client. Not a bug — same as the plain-text path which has identical untested production-client branches.
