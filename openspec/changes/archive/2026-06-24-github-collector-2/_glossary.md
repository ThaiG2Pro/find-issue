# Glossary — github-collector-2 (ticket 2)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|------------|------------|-----------|-------|
| Collector | The S2 component that fetches raw items from GitHub via REST and returns `RawItem`s; pure I/O, no state/LLM access | analyst | — | S1 |
| Newly-opened issue | A GitHub issue whose `created_at` is within the last `lookback_days` (UTC); the unit S2 V1 collects | analyst | — | S1 |
| Lookback cutoff | The UTC timestamp `now - lookback_days`; items with `created_at` before it are excluded | analyst | — | S1 |
| max_items_per_repo | Config-driven cap (default 100) on how many `RawItem`s the Collector returns for one repo; read from config, never hardcoded in the fetch loop | analyst | AC-2-005, AC-2-006, AC-2-024, BR-2-005, BR-2-013 | S1 |
| Pull request exclusion | Dropping any GitHub issues-endpoint item that carries a `pull_request` field (PRs are not collected in V1) | analyst | — | S1 |
| Link rel=next | GitHub's pagination mechanism — the `Link` response header's `rel="next"` URL drives page traversal | analyst | — | S1 |
| Per-repo error isolation | 404/410 → warn+skip+continue; 401/403 auth → fail fast (affects all repos) | analyst | — | S1 |
| Dirty data tolerance | Treating GitHub JSON as untrusted: guard null/missing fields, coerce to safe defaults | analyst | — | S1 |
| Pure I/O boundary | The Collector must not read/write the State Store (S3) nor call the LLM (S4); depends only on `osspulse.models` | analyst | AC-2-015, BR-2-012 | S1 |
| RawItem mapping | issue→RawItem: repo=owner/repo, item_type="issue", item_id=str(number), title, body (null→""), url=html_url, created_at=raw ISO string | analyst | AC-2-016, AC-2-017, BR-2-010 | S2 |
| Secondary rate limit | A `403` response carrying `X-RateLimit-Remaining: 0` — a rate-limit signal, NOT a permanent auth error; triggers backoff not fail-fast | analyst | AC-2-020, BR-2-007 | S2 |
| Retry policy | Single config object — `max_retries`=3, `backoff_base_seconds`=1.0, `backoff_multiplier`=2.0, `jitter_seconds`=0.5, `backoff_ceiling_seconds`=60.0 — for 429/5xx/secondary-limit, honoring `Retry-After` (capped by ceiling); 4xx permanent. Tunable without editing the fetch loop | analyst | AC-2-019..023, AC-2-026, BR-2-007, BR-2-014 | S2 |
| Truncation note | Info-level log emitted when `max_items_per_repo` cap is reached, so a truncated repo digest is not silent | analyst | AC-2-006, BR-2-005 | S2 |
| Repo identifier validation | Collector rejects any `repo` not matching `^[\w.-]+/[\w.-]+$` before any request (defense-in-depth vs SSRF-shaped path) | analyst | AC-2-014, BR-2-011 | S2 |
| Config-driven tunable | Any value the Collector reads from its config object rather than a literal: `max_items_per_repo`, `page_size`, `base_url`, and the retry-policy fields. Defaults apply when omitted; explicit config overrides without a code change | analyst | AC-2-024..027, BR-2-013, BR-2-014 | S2 |
| page_size | Config-driven `per_page` for each GitHub request (default 100 = GitHub max); read from config, not a scattered literal | analyst | AC-2-024, BR-2-013 | S2 |
| base_url | Config constant for the GitHub API host (default `https://api.github.com`); GET-only, overridable for GitHub Enterprise, never built from the `repo` arg or untrusted input | analyst | AC-2-025, BR-2-008, BR-2-014 | S2 |
| GitHubCollector | The httpx-based adapter (S2) implementing `ports.GitHubClient`; lives in `src/osspulse/github/client.py` | architect | INT-2-001, AC-2-015 | S3 |
| CollectorConfig | Frozen dataclass of collector tunables (`max_items_per_repo`, `page_size`, `base_url`, `retry`) injected via the constructor; defaults locked, token NOT stored here | architect | AC-2-024..027, BR-2-013 | S3 |
| RetryPolicy | Frozen dataclass nested in CollectorConfig (`max_retries`, `backoff_base_seconds`, `backoff_multiplier`, `jitter_seconds`, `backoff_ceiling_seconds`) driving `_request_with_retry` | architect | AC-2-026, BR-2-014 | S3 |
| _classify | Single status→{OK,RETRY,SKIP_REPO,FAIL_FAST} classifier; the 403 split keys on `X-RateLimit-Remaining:0` | architect | AC-2-008, AC-2-011, AC-2-020 | S3 |
| _request_with_retry | The only httpx caller; bounded backoff wrapper honoring Retry-After, capped by ceiling | architect | AC-2-019..023, AC-2-026 | S3 |
| REPO_PATTERN | Public shared `owner/name` regex constant promoted from `config._REPO_RE`; reused by the Collector for re-validation | architect | AC-2-014, BR-2-011 | S3 |
| _Action | Internal enum {OK, RETRY, SKIP_REPO, FAIL_FAST} returned by `_classify`; drives the retry loop and the fetch-loop skip branch | developer | AC-2-008, AC-2-011, AC-2-020 | S4 |
| _parse_created | Helper that converts a GitHub `created_at` `...Z` ISO string to a tz-aware UTC datetime for the cutoff compare ONLY; the stored `RawItem.created_at` keeps the raw string (BR-2-010) | developer | AC-2-005, BR-2-009, BR-2-010 | S4 |
