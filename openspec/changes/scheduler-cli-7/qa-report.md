# S5 QA Report — 7 (scheduler-cli-7)
Date: 2026-06-30
QA Mode: Smart (dev-test-report.md present; focus on gaps, code review, security)

## Gate Checklist

| Item | Result |
|------|--------|
| dev-test-report.md present | ✅ |
| Coverage ≥ 80% threshold | ✅ 98.51% |
| All required tasks `[x]` | ✅ 25/25 |
| Self-review log present (deviations documented) | ✅ 2 deviations in report |
| Integration smoke test | ⚠️ Deferred — no live GitHub token in this environment (see smoke section) |
| `.env.example` ≥ 10 lines | ✅ 33 lines |
| README ≥ 10 lines | ✅ 199 lines |
| Structured logging wired | ✅ `logging.getLogger("osspulse.pipeline")` in pipeline.py |
| Figma URL | N/A — CLI tool, no UI |

## Test Scenarios

All ACs verified by code review. Shallow TCs from Dev's suite resolved via code review below.

| AC-ID | Scenario | How to verify | Expected | Priority | Result |
|-------|----------|---------------|----------|----------|--------|
| AC-7-002 | Import isolation | Read stage source files for cross-imports | No stage imports another | High | ✅ PASS |
| AC-7-005 | Auth-fatal catch order | Read `_collect_all` except ladder | `AuthError` FIRST clause, before `RateLimitError` | Critical | ✅ PASS |
| AC-7-009 | Redis fail → _NullCache end-to-end | Code review `_build_cache` → `_summarize` path | Digest delivered; one WARN log | Medium | ✅ PASS |
| AC-7-013 | BrokenPipe → exit 0 | Code review `cli.py except BrokenPipeError` | Handler present and correct; `Exit(code=0)` | Medium | ✅ PASS (code review) |
| AC-7-014 | AuthError message token-safe | Read `github/client.py:154-156` | Message = repo + status code, no token | Critical | ✅ PASS |
| AC-7-018 | Survivors only rendered | Code review `_summarize` → `render(summarized, ...)` | No re-merge of `all_items`; only survivors passed | Medium | ✅ PASS |
| AC-7-021 | Run-summary log line content | Read `run_pipeline` final `logger.info` | `"run complete — repos: %d, collected: %d, summarized: %d, skipped: %d"` | Medium | ✅ PASS |
| AC-7-022 | No-LLM placeholder non-empty | `NO_LLM_PLACEHOLDER == "(no summary — LLM disabled)"` | Non-empty; renderer emits it | High | ✅ PASS |
| BR-7-006 | Token never on pipeline object | Code review `run_pipeline` — local vars only | `config.github_token` passed only to `GitHubCollector(...)` ctor | Critical | ✅ PASS |

## Step B1 — Test Quality Review (Hollow TC Findings)

| ID | Test | Issue | Classification | Decision |
|----|------|-------|----------------|----------|
| H1-a | `test_broken_pipe_exits_0` | Static source inspection only; does not exercise the handler | `[EDGE-CASE]` | Accepted — CliRunner limitation documented in `_decisions.jsonl`; code review confirms correctness |
| H1-b | `test_run_summary_log_emitted_on_success` | Asserts `exit_code == 0` only; caplog not asserted | `[AI-DETECTABLE]` | Low severity — AC-7-021 verified by code review; log line confirmed present in source |
| H1-c | `test_summarizer_returns_fewer_items` | Asserts `deliver` called but never checks digest contains only survivors | `[AI-DETECTABLE]` | Low severity — AC-7-018 verified by code review; no re-merge path exists |

All three hollow TCs are Low severity (H1-b and H1-c are coverage-depth issues, not correctness bugs — the code review independently confirms the behavior). No blocking bugs.

## Security Audit Results

Applied OWASP checklist against `pipeline.py` + `cli.py`:

| Category | Result | Notes |
|----------|--------|-------|
| Secrets management | ✅ PASS | Token/key passed to ctor only; never stored on `self` or logged |
| Logging security (RF-1) | ✅ PASS | All log calls use `type(exc).__name__`, repo name, counts only — never raw exception or secret value |
| AuthError message | ✅ PASS | `"GitHub auth failed for '{repo}' (status {code})"` — token-free (github/client.py:154) |
| Input validation | ✅ N/A | No new input surface; config validated by `load_config` |
| Injection / SSRF | ✅ N/A | No DB, no shell, no user URL construction |
| File path safety | ✅ PASS | `FileDelivery` path from `load_config` (already validated); no traversal |

**Security verdict: 0 Critical, 0 High, 0 Medium. RF-1 (HIGH) mitigated and verified.**

## Integration Smoke Test

The environment does not have a valid `GITHUB_TOKEN` or live network access. Per QA rules, this is documented as an [EDGE-CASE] limitation:

- **What was done**: `uv run pytest --cov=osspulse -q` run independently by QA → 271 pass, 98.51% coverage. App imports without error. Config validation tested end-to-end via `test_config_error_exits_1_no_traceback`.
- **What was NOT done**: Live `osspulse run` against real GitHub repos.
- **Risk**: Low — all GitHub/LLM calls are mocked in tests. The pipeline wiring (`run_pipeline`) is fully unit-tested with all adapter interactions covered.
- **Operator verification**: Run `uv run osspulse run --config config.toml` with a real `GITHUB_TOKEN` to confirm end-to-end.

## Bug List

No Critical or High bugs found. Hollow TC findings (H1-a/b/c) are Low severity and do not block GO.

| # | Title | AC-ID | Severity | Classification | RCA Phase |
|---|-------|-------|----------|----------------|-----------|
| — | No bugs found | — | — | — | — |

## AC Coverage Summary

- Total ACs: 22
- Covered by Dev unit tests: 22/22 (all in `dev-test-report.md` AC table)
- Independently verified by QA this session: **22/22** (17 via test quality review confirming assertions are correct; 4 shallow TCs resolved via code review; 1 additional via security audit)
- Not covered: 0
- Deviation: AC-7-013 (BrokenPipeError) tested statically by Dev due to CliRunner limitation; QA code review confirms handler is correct.

## CMS UI Visual QA

N/A — CLI tool, no UI. No Figma URL present (consistent with collector-2 ADR-007, confirmed in proposal.md).

## Dependency Vulnerability Audit

```
Tool: pip-audit (uv tool run pip-audit)
Result: No known vulnerabilities found
HIGH/CRITICAL: 0 — CLEAN
```

✅ No blocking dependency findings.

## Decision: **GO**

0 Critical bugs, 0 High bugs. All 22 ACs verified. Coverage 98.51% ≥ 80%. Security audit clean. Dependency audit clean. 3 hollow TCs (Low severity) documented but do not block release — all verified by code review.

**Operator note for S6**: Before archiving, verify `uv run osspulse run` end-to-end with a real `GITHUB_TOKEN` to confirm the live integration smoke test passes.

## Blockers

None.
