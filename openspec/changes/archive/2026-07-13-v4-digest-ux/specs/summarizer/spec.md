## MODIFIED Requirements

### Requirement: Retry with backoff on rate-limit before skipping
On a `RateLimitError` (HTTP 429) for a single item, the Summarizer SHALL retry the LLM call
with exponential backoff up to `SummarizerConfig.max_retries` (default **7**) attempts. The
backoff delay for attempt `n` (0-indexed) SHALL be `retry_backoff_base_seconds * 2**n`, which
with the default base of `1.0` yields the sequence **1, 2, 4, 8, 16, 32, 64** seconds across
the 7 retries (≈ 127 s total). When the error carries a `Retry-After` header (seconds), the
Summarizer SHALL wait at least that long before the next attempt; otherwise it SHALL use the
exponential backoff delay. If all retries are exhausted, the Summarizer SHALL fall back to the
existing skip-log-continue behavior — log the failure with item identity only (never the API
key or prompt), skip the item, and keep processing the batch.

> ACs: AC-V3-001-006 [CONFIRMED], AC-V3-001-007 [ASSUMED], AC-V3-001-008 [CONFIRMED], AC-V4-002-001 [CONFIRMED], AC-V4-002-002 [CONFIRMED]
> Business rules: BR-V3-001-004, BR-V4-002-001
> Risk: RF-2 (availability), RF-4 (no secret leakage)

#### Scenario: A 429 that succeeds on retry produces a summary (AC-V3-001-006) [CONFIRMED]
- **WHEN** the LLM raises `RateLimitError` on the first attempt for an item but succeeds on a subsequent attempt within `max_retries`
- **THEN** the item is retried after a backoff delay and a `SummarizedItem` is produced (the item is NOT skipped)

#### Scenario: A Retry-After header is honored (AC-V3-001-007) [ASSUMED]
- **WHEN** a `RateLimitError` carries a `Retry-After` value of N seconds
- **THEN** the Summarizer waits at least N seconds before the next retry attempt

#### Scenario: Exhausted retries fall back to skip-log-continue (AC-V3-001-008) [CONFIRMED]
- **WHEN** every attempt up to `max_retries` raises `RateLimitError` for an item
- **THEN** the item is skipped, the failure is logged with item identity only (no API key, no prompt), no exception propagates, and the remaining items are still summarized

#### Scenario: The default retry ceiling is 7 attempts (AC-V4-002-001) [CONFIRMED]
- **WHEN** a `LiteLLMSummarizer` is constructed with a `SummarizerConfig` built from defaults (no explicit `max_retries`)
- **THEN** `config.max_retries` is `7`, so an item hitting a persistent 429 is retried up to 7 times before being skipped

#### Scenario: The backoff sequence over 7 retries is 1/2/4/8/16/32/64 s (AC-V4-002-002) [CONFIRMED]
- **WHEN** an item raises `RateLimitError` on every attempt (no `Retry-After` header) with `max_retries=7` and `retry_backoff_base_seconds=1.0`
- **THEN** the injected sleep is called before each retry with the delays 1, 2, 4, 8, 16, 32, 64 seconds in that order, and after the 7th the item is skip-logged-continued
