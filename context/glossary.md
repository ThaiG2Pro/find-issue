# Domain Glossary

| Term | Definition | Notes / aliases |
|------|------------|-----------------|
| Watchlist | The user-defined list of GitHub repos (`org/repo`) the tool monitors | Core scope boundary — tool never goes beyond it |
| Digest | The readable summarized output for a run, grouped per repo and source | Output of S5; delivered by S6 |
| Lookback window | The time range (`lookback_days`, e.g. 7) a run considers for new items | Per-repo or global |
| Delta | The subset of items that are new since the last run | Full delta is V2; V1 only records seen state |
| Collector | The component that fetches raw items from GitHub | S2; REST (V1), GraphQL for Discussions (V2) |
| Summarizer | The component that turns raw item text into a 1–2 sentence summary via LLM | S4; uses LiteLLM + Redis cache |
| State store | Persisted record of "what has been seen" to enable idempotency/delta | S3; JSON file (V1) → SQLite (V2) |
| Summary cache | Redis store of already-computed summaries to avoid re-calling the LLM | Cache-aside, best-effort |
| Rate limit | GitHub API request cap (60/hr unauthenticated, 5000/hr with token) | Token raises the cap; pipeline backs off near the limit |
| Item | A single unit of content: an issue (V1), discussion, or release (V2) | The thing that gets summarized |
| Repo-welcomeness | Experimental metric: how welcoming a repo is to new contributors | V3 only (PR response time, newcomer merge rate) |
