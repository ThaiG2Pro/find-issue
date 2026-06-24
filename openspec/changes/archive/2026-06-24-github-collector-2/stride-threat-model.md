# STRIDE Threat Model — github-collector-2 (S2 GitHub Collector, V1 issues)

> Run trigger: `security.stride_analysis = auto` → feature touches **tokens/secrets**
> (`GITHUB_TOKEN`) and an **external integration** (GitHub REST API). Applicable.
> Domain: **API integration (outbound)** — single-operator self-host CLI, no inbound surface.

## Executive Summary

The Collector is an **outbound-only** client: it authenticates to GitHub with the
operator's own token and reads public-repo data. There is no inbound HTTP surface,
no multi-tenant authz, and the only secret is the operator's own token. The real risk
surface is therefore: (1) leaking the token, (2) trusting attacker-influenced response
data, (3) request amplification (rate-limit DoS against the operator's own budget),
and (4) the `repo` string being used to build a URL (SSRF-shaped, but bounded by a
strict `owner/name` validation at config time, owned by S1).

Threats: 7 (Critical 0 / High 2 / Medium 3 / Low 2) · Gate: **PASS** (all High mitigated with a test plan).

## S — Spoofing
- **T-S1 [Medium]** A malicious/compromised endpoint impersonating `api.github.com`.
  *Mitigation*: httpx default TLS verification (never disable `verify`); base URL is a
  constant, not derived from untrusted input. → AC-2-013.

## T — Tampering
- **T-T1 [High]** GitHub response JSON is **untrusted/dirty data** — missing fields,
  null `body`, unexpected types. Blindly indexing can crash the run or inject bad
  content into LLM prompts downstream.
  *Mitigation*: guard every field access; coerce missing `body`/`title` to safe
  defaults; never assume shape. → AC-2-010, AC-2-011.
- **T-T2 [Medium]** `repo` string used to build the request path (`/repos/{repo}/issues`)
  — a crafted value (`../`, `@evil.com`) could redirect the request (SSRF-shaped).
  *Mitigation*: `WatchedRepo` is validated to strict `owner/name` at config time (S1,
  ADR-003); Collector receives only validated `full_name`. Collector additionally
  rejects any `repo` not matching `^[\w.-]+/[\w.-]+$`. → AC-2-012.

## R — Repudiation
- **T-R1 [Low]** No audit trail of which repos were fetched / skipped.
  *Mitigation*: structured log line per repo (fetched count, skipped reason) at
  info/warn. Low severity for a single-operator tool. → AC-2-008.

## I — Information Disclosure
- **T-I1 [High]** `GITHUB_TOKEN` leaking into logs, exception messages, or the digest.
  GitHub returns the token only in the request `Authorization` header, but a naive
  error handler could echo the request (headers) on failure.
  *Mitigation*: token read from env only (S1); NEVER logged; error messages reference
  the failure class, not the request headers; redact `Authorization` if a request is
  ever logged. → AC-2-009, security.md R-SEC.
- **T-I2 [Low]** Fetched issue bodies (public data) flow downstream to the LLM provider.
  *Mitigation*: out of S2 scope (S4 owns LLM I/O); data is already public; README
  privacy note (S1). No Collector action. → noted, not an AC.

## D — Denial of Service
- **T-D1 [High → mitigated]** Unbounded pagination on a hot repo burns the 5000 req/hr
  budget and can starve later repos in the watchlist; also produces an unreadable digest.
  *Mitigation*: `max_items_per_repo` cap (default 100) + early-stop on `created_at` <
  cutoff (Q3); back off and respect `Retry-After`/`X-RateLimit-Reset` near the limit
  (Q-rate). → AC-2-005, AC-2-006, AC-2-007.

## E — Elevation of Privilege
- **T-E1 [Medium]** Token scoped wider than needed (e.g. write/admin) increases blast
  radius if leaked.
  *Mitigation*: documented minimum scope = read-only public repo (S1 constraint); the
  Collector only issues GET requests — never mutating verbs. → AC-2-013.

## Security Test Strategy
- Mock a 401/403 response → assert fail-fast with a clear message, token value absent from output (T-I1).
- Mock a response with null `body` / missing `user` → assert no crash, safe defaults (T-T1).
- Feed an invalid `repo` (`../x`, `a/b/c`, empty) → assert rejected before any request (T-T2).
- Mock a near-limit `X-RateLimit-Remaining: 0` + `Retry-After` → assert backoff, no hammering (T-D1).
- Assert the Collector only ever issues `GET` (T-E1) and never disables TLS verify (T-S1).

## Gate: PASS
No Critical. Both High threats (T-T1 untrusted data, T-I1 token leak, T-D1 DoS) have a
mitigation + a test in the strategy above. Feeds: analyst Early Risk Flags · architect
design security · qa-test-design.
