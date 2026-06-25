# Glossary — summarizer-llm-4

Shared, append-only domain/technical glossary. Every phase adds rows. Keep **Phase** as the LAST column.

| Term | Definition | Phase |
|------|------------|-------|
| SummarizedItem | Frozen domain model `SummarizedItem(raw: RawItem, summary: str)` — the S4 output consumed by S5 renderer | S2 |
| content_hash | Stable SHA-256 hex of the normalized text submitted to the LLM (title+body, post-truncation); the last segment of the cache key so an edited issue gets a fresh summary | S2 |
| Cache-aside | Pattern: check `SummaryCache.get(key)` → on miss call LLM → `set(key, value)`. Used by S4 over the existing `SummaryCache` port | S2 |
| Graceful degradation | On LLM timeout/error for one item: catch, log (no secrets), skip that item, continue the run — never abort the whole digest | S2 |
| Best-effort cache | The Redis summary cache may fail; a get/set failure is caught and treated as miss/no-op, never crashing the pipeline | S2 |
| Skip-item | The chosen failure mode (A-A2): a failed item is absent from the digest (no SummarizedItem), as opposed to a placeholder summary | S2 |
| Input cap | Bounded character length the issue body is truncated to before the LLM call, to cap token cost (A-A5; value TBD by architect) | S2 |
| Data egress (LLM) | The act of sending issue text to the operator-configured third-party LLM provider — the project's defining privacy/security surface (RF-1) | S1 |
| LiteLLMSummarizer | The concrete `LLMClient` adapter (S4) holding cache-aside + LLM call + normalize; injected with provider/api_key/cache/config/completion (ADR-001) | S3 |
| summarize_items | Adapter-only batch helper `summarize_items(items)->list[SummarizedItem]` that owns catch-log-skip-continue; NOT on the Protocol (ADR-005) | S3 |
| SummarizationFailed | Adapter exception raised when the LLM returns empty/whitespace output → triggers skip; never cached (ADR-006, EC-012) | S3 |
| SummarizerConfig | Frozen tunables dataclass: model, request_timeout_seconds=30, input_char_cap=8000, max_sentences=2, max_summary_chars=600; NO secret field (ADR-007) | S3 |
| APIError-boundary | The single LLM-failure catch `except litellm.exceptions.APIError` (common base of Timeout/RateLimit/4xx/5xx); precise so bugs still surface (ADR-002) | S3 |
| RedisSummaryCache | Thin faithful `SummaryCache` adapter over `redis.Redis` (may raise); best-effort swallow lives in the summarizer adapter, not here (ADR-004) | S3 |
