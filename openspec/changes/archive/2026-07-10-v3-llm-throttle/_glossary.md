# Glossary — v3-llm-throttle

| Term | Definition | Phase |
|------|------------|-------|
| sliding window | in-memory 60s record of per-call `total_tokens` used to decide when to sleep | S2 |
| tokens_per_minute | configurable per-minute token budget (default 6000, Groq free tier) | S2 |
| retry-then-skip | 429 triggers exp-backoff retry (max 3, honoring Retry-After) before the existing skip-log-continue fallback | S2 |
| TokenWindow | S3 class in `client.py` holding `list[(timestamp, tokens)]`; `record()`, `_prune()`, `sleep_if_needed()`; run/batch-scoped adapter state, never persisted (ADR-001/002) | S3 |
| sleep/clock injection | injected `sleep=time.sleep`, `clock=time.monotonic` ctor params (mirror existing `completion=`) so throttle/retry delays are deterministic in tests (ADR-003) | S3 |
| Retry-After extraction | defensive `getattr(exc, "response", None)` → headers → `Retry-After`; used as the *minimum* wait, falls back to exp-backoff on any absence/parse failure (ADR-005) | S3 |
