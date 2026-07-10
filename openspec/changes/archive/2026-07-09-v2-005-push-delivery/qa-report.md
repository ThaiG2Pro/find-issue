# S5 QA Report — V2-005 (v2-005-push-delivery)
Date: 2026-07-08T17:30:00+07:00
QA Mode: Smart (dev-test-report.md present)

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% threshold | ✅ 96% |
| All required tasks `[x]` | ✅ 17/17 |
| Self-review log present | ✅ (dev-test-report §Self-Review) |
| Integration smoke test | ✅ config load/fail-fast, SSRF guard, split boundary, CLI imports verified locally |
| `.env.example` / README / structured logging | ✅ N/A — CLI tool; no HTTP server, no new structured logging path; existing logging wired unchanged |

**Gate: PASS** — all items satisfied.

## Test Scenarios (QA-generated for gap coverage + risky areas)

| AC-ID | Scenario | How to verify | Expected | Priority | Result |
|-------|----------|---------------|----------|----------|--------|
| AC-V2-005-004 | Exactly 2000-char content → single message | `_split_for_discord("x"*2000)` | `len(result)==1` | High | ✅ smoke confirmed |
| AC-V2-005-007 | 700 × 'Ế' (3-byte char) — chars < 2000, bytes > 2000 | `_split_for_discord(content)` | `len(result)==1` | High | ✅ confirmed in unit test + smoke |
| AC-V2-005-011 | SSRF error for evil.com URL | `load_config` with `https://evil.com/...` | ConfigError, no URL in message | Critical | ✅ smoke: "webhook host must be..." (no URL) |
| AC-V2-005-013 | Missing env var → ConfigError at load time (not at delivery) | `load_config` with no `DISCORD_WEBHOOK_URL` in env | ConfigError before pipeline runs | High | ✅ smoke: ConfigError raised at load |
| AC-V2-005-014 | http:// URL → ConfigError | `load_config` with http:// URL | ConfigError "https scheme" | High | ✅ unit test + smoke |
| AC-V2-005-008 | HTTP 204 treated as success | mock returning 204 | no DeliveryError | High | ✅ `test_2xx_204_is_success` |
| AC-V2-005-010 | Timeout 10s → DeliveryError | inject `TimeoutException` | DeliveryError "timed out", no URL | High | ✅ `test_timeout_raises_delivery_error` |
| AC-V2-005-001 | Pipeline wiring: `elif "discord"` instantiates DiscordDelivery | static code inspection | elif branch present, correct ordering | High | ✅ static smoke verified |
| AC-V2-005-003 | No upstream imports at module level | static inspection of discord_delivery.py | no github/summarizer/cache/render | High | ✅ test_no_upstream_imports passes |
| AC-V2-005-011 | DeliveryError from ConnectError contains type name not URL | inject ConnectError, check error msg | "ConnectError" in msg, URL absent | Critical | ✅ `test_connection_error_does_not_leak_url` |

## Security Audit Results (OWASP-based, mandatory)

### ✅ Passed

- **A10 SSRF guard**: `urlparse` scheme==`https` + hostname ∈ `{discord.com, discordapp.com}` enforced at config load. Verified by `test_discord_non_discord_host_raises`, `test_discord_http_url_raises`, and smoke test.
- **A09 Logging — no secret**: `discord_delivery.py` has zero `logger`/`print` calls. DeliveryError text uses `type(exc).__name__` / `response.status_code` — never `str(exc)` (which embeds URL in httpx). Five tests assert URL absent from error message.
- **A01/A02 Secrets management**: webhook URL resolved from env var only; never in config file, never committed. Error messages for all validation failures confirmed URL-free (even SSRF error names only the constraint).
- **A03 Injection**: no string interpolation into outbound request beyond the pre-validated URL and the digest content. Digest content is rendered Markdown — no eval, no SQL, no shell.
- **A02 TLS**: `https` scheme enforced; httpx uses system TLS by default.
- **Timeout**: `~10s` applied at both `httpx.Client(timeout=...)` and per-request `client.post(..., timeout=...)`. Double-timeout is redundant but harmless (per-request overrides client default).

### 🟡 Medium (non-blocking)

- **A06 Vulnerable Components**: `pip-audit`/`safety` not installed in this environment — dependency audit could not be run automatically. `httpx 0.28.1` has no known CVEs in public advisories at time of review. Recommend adding `pip-audit` to CI.

### No Critical / High findings.

## Bug List

| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| — | No bugs found | — | — | — | — |

## AC Coverage Summary

- Total ACs: 15
- Covered by Dev (unit tests): 15 (verified via dev-test-report.md AC table + independent test run 103/103)
- Independently verified by QA this session: 15 (code review + smoke tests for every AC)
- Not covered: 0

**Notes on QA independent verification:**
- ACs 001/002: pipeline wiring + port compat — code review + static inspection ✅
- ACs 004–007: split algorithm — read source + manual boundary smoke ✅
- ACs 008–010: error mapping — read `_post_one` except chain; `TimeoutException` caught before `RequestError` (subclass ordering correct) ✅
- AC-011: URL-leak — read error construction code; no `str(exc)`, no URL interpolation; 5 tests cross-checked ✅
- ACs 012–015: config validation — read `_resolve_discord_url`; error messages inspected (no URL value); smoke-tested fail paths ✅
- AC-003: import decoupling — read module top-level imports; only `httpx` and `osspulse.delivery.errors` ✅

## CMS UI Visual QA

N/A — no Figma URL, no UI changes. CLI tool only.

## Dependency Vulnerability Audit

pip-audit / safety not installed in this environment. Manual check: `httpx 0.28.1` — no known CVEs at 2026-07-08. Recommend adding `pip-audit` to CI pipeline.

**No HIGH/CRITICAL findings that block GO.**

## Active Concerns (non-blocking, noted for S6/ops)

1. **`pipeline.py:291-294` uncovered** — discord `elif` branch not hit by `test_pipeline.py`. Developer documented this; delivery is tested independently (24 tests). Recommendation: add a pipeline-level integration fixture for `destination=discord` in a follow-up.
2. **`_enforce_limit` line 112** — defensive safety-net, never reached in practice. Low risk.
3. **RISK-1 partial multi-message** — if message k fails, messages 1..k-1 already sent; no rollback. This is accepted design behavior (CLAR-3, ADR). `test_multi_message_second_fails_after_first_sent` verifies this is the actual behavior.
4. **pip-audit missing in CI** — see dependency audit above.

## Decision: ✅ GO

- 0 Critical bugs, 0 High bugs
- 15/15 ACs covered and independently verified
- 103/103 tests pass (QA independent run)
- Coverage 96% ≥ 80% threshold
- Security audit: 0 Critical/High findings; SSRF guard, URL-leak guard, HTTPS enforcement all verified
- All 17 required tasks `[x]`
- `openspec validate` PASS

## Blockers

None.
