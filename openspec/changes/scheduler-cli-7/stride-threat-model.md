# STRIDE Threat Model — scheduler-cli-7 (S7 Scheduler/CLI)

> Run reason: `security.stride_analysis = auto` → applies (S7 handles `GITHUB_TOKEN` +
> `llm_api_key` end-to-end through the pipeline). Domain: **Tokens/Secrets + External Integration**.
> No auth surface, no payment, no PII, no upload, no admin/multi-tenant (single-operator CLI).

## Executive Summary
S7 introduces no new inbound attack surface — it is a CLI run by the operator on their own
machine. The real risks are (a) leaking the GitHub/LLM secrets through logs, error messages, or the
delivered digest, and (b) integrity/availability of the external calls (rate-limit exhaustion,
partial writes). All identified threats have established mitigations inherited from changes 2–6.
**Gate: PASS** (no Critical; the one High has a mitigation + test plan).

## S — Spoofing
- **Not applicable.** No inbound authentication surface; single operator runs the CLI locally.
  Outbound auth (the GitHub token) is the operator's own credential.

## T — Tampering
- **RF-3 (MEDIUM)** — A crash mid-write could corrupt the digest file or the state file.
  - Mitigation: delivery-6 (atomic temp+`os.replace` digest write) and state-store-3 (atomic state
    write) both guarantee no partial file. S7 MUST NOT add a non-atomic write path; it only calls
    the existing atomic adapters. Test: simulate failure between write and replace → previous file
    intact.

## R — Repudiation
- **RF-4 (LOW)** — Without per-repo logging, a silent partial failure (some repos skipped) is
  invisible to the operator, who can't tell a "no new issues" run from a "half the repos 404'd"
  run.
  - Mitigation: log exactly one outcome line per repo (collected N / skipped: reason) at INFO/WARN.
    Drives AC-7-015 + BR-7-005. Test: multi-repo run with mixed outcomes → one log line each.

## I — Information disclosure
- **RF-1 (HIGH)** — `GITHUB_TOKEN` and `llm_api_key` flow through the pipeline construction. A
  leak into a log line, an error message, or (worst) the delivered digest would expose the
  operator's credentials.
  - Mitigation: reuse the no-secret-logging discipline already enforced upstream — collector-2
    ADR-004 (token only on httpx headers, never on `self`/logs/errors) and summarizer-llm-4 ADR-008
    (api_key private, never logged/repr'd; only title+body sent to LLM). S7 logs repo names, item
    ids, counts, and error *types* only. Drives AC-7-014 (security AC) + a log-capture test that
    asserts neither secret substring appears in captured logs/stderr/digest.

## D — Denial of service
- **RF-2 (MEDIUM)** — A large watchlist × large `lookback_days` could exhaust GitHub's 5000/hr
  quota or run up LLM cost (self-inflicted DoS / cost).
  - Mitigation: the collector already backs off on rate limit; S7 stops cleanly on a terminal
    `RateLimitError` (EC-013) and delivers whatever was already collected. `lookback_days > 365`
    already warns at config load. No new guard for V1; note for V2 monitoring. Test: collector
    raises `RateLimitError` → no crash, partial digest delivered, clear message.

## E — Elevation of privilege
- **RF-6 (LOW)** — Token scope is read-only public-repo (project principle). S7 issues only the
  GETs the collector already makes; it adds no write/privileged GitHub call and no local privilege
  escalation.
  - Mitigation: none needed beyond keeping scope minimal (documented in README). No new surface.

## Security Test Strategy
- Log-capture test: run the pipeline with a fake token+key, assert neither secret substring appears
  in captured logs, stderr, or the delivered digest (RF-1, AC-7-014).
- Atomicity test: inject a failure mid-delivery/mid-state-write, assert no partial file (RF-3) —
  largely covered by delivery-6/state-store-3 suites; S7 adds an integration assertion.
- Rate-limit test: collector mock raises `RateLimitError`, assert clean message + exit + partial
  digest (RF-2, EC-013).
- Auth-fatal test: collector mock raises `AuthError`, assert exit 1 + no token in message (EC-011).

## Dev Recommendations
- Construct adapters once per run; pass the token to the collector and the key to the summarizer
  only — never store either on the pipeline object or in any logged structure.
- Log error *types/messages from our own exception classes*, never the raw upstream exception that
  might embed a URL with a token query param.

## Gate
**PASS** — Threats: 5 (Critical 0 / High 1 / Medium 2 / Low 2). RF-1 (High) mitigated + tested.
Feeds: analyst Early Risk Flags (proposal.md) · architect design security (S3) · qa-test-design (S5).
