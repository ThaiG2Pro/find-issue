## ADDED Requirements

### Requirement: Token-aware per-minute throttle
The Summarizer SHALL pace its LLM calls to stay under a configurable per-minute token
budget (`SummarizerConfig.tokens_per_minute`, default **6000** to match Groq's free tier).
After each completion it SHALL read `response.usage.total_tokens` and record it against a
**60-second sliding window** (`SummarizerConfig.throttle_window_seconds`, default `60`).
Before making the next LLM call, if adding the window's currently-recorded tokens would meet
or exceed the budget, the Summarizer SHALL sleep until the oldest entries fall outside the
window (enough headroom is freed), then proceed. The throttle is run-scoped, in-memory, and
best-effort — it SHALL NOT persist across runs and SHALL NOT alter summary content.

> ACs: AC-V3-001-001 [CONFIRMED], AC-V3-001-002 [ASSUMED], AC-V3-001-003 [ASSUMED], AC-V3-001-004 [CONFIRMED]
> Business rules: BR-V3-001-001, BR-V3-001-002
> Risk: RF-1 (cost control), RF-2 (availability)

#### Scenario: Approaching the per-minute budget triggers a sleep before the next call (AC-V3-001-001) [CONFIRMED]
- **WHEN** the tokens recorded in the current 60-second window plus the next call would meet or exceed `tokens_per_minute`
- **THEN** the Summarizer sleeps until enough window headroom is freed before issuing the next LLM completion, and the batch still completes without raising

#### Scenario: Calls comfortably under budget incur no sleep (AC-V3-001-002) [ASSUMED]
- **WHEN** the recorded window tokens plus the next call stay below `tokens_per_minute`
- **THEN** no sleep is triggered and items are summarized back-to-back

#### Scenario: Missing usage data is treated as zero tokens, not a crash (AC-V3-001-003) [ASSUMED]
- **WHEN** a completion response has `usage` set to `None` or missing `total_tokens`
- **THEN** the item's recorded token cost for the window is `0`, no exception is raised, and the batch continues

#### Scenario: Cache hits and skipped items add nothing to the window (AC-V3-001-004) [CONFIRMED]
- **WHEN** an item is served from cache or skipped as fully-empty (no LLM call made)
- **THEN** no tokens are recorded in the sliding window and no throttle sleep is triggered for that item

### Requirement: Summaries are returned in Vietnamese
The Summarizer SHALL instruct the LLM to answer in Vietnamese by including the exact
instruction text `Trả lời bằng tiếng Việt.` in the prompt it sends. This SHALL NOT change
which fields are sent to the provider — only `title` and `body` are still egressed (RF-1) —
and SHALL NOT alter the 1–2 sentence normalization contract.

> ACs: AC-V3-001-005 [CONFIRMED]
> Business rules: BR-V3-001-003
> Risk: RF-5 (data egress boundary — unchanged)

#### Scenario: The Vietnamese instruction is present in the prompt (AC-V3-001-005) [CONFIRMED]
- **WHEN** `summarize(item)` builds the prompt for an LLM call
- **THEN** the messages sent to the LLM contain the exact string `Trả lời bằng tiếng Việt.`, and still contain only the item's title and body as content (no other item fields)

### Requirement: Retry with backoff on rate-limit before skipping
On a `RateLimitError` (HTTP 429) for a single item, the Summarizer SHALL retry the LLM call
with exponential backoff up to `SummarizerConfig.max_retries` (default **3**) attempts. When
the error carries a `Retry-After` header (seconds), the Summarizer SHALL wait at least that
long before the next attempt; otherwise it SHALL use exponential backoff. If all retries are
exhausted, the Summarizer SHALL fall back to the existing skip-log-continue behavior — log
the failure with item identity only (never the API key or prompt), skip the item, and keep
processing the batch.

> ACs: AC-V3-001-006 [CONFIRMED], AC-V3-001-007 [ASSUMED], AC-V3-001-008 [CONFIRMED]
> Business rules: BR-V3-001-004
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

## MODIFIED Requirements

### Requirement: Graceful degradation on LLM timeout or error
The Summarizer SHALL catch any timeout, connection error, rate-limit (429), 4xx, or 5xx
raised by the LLM call for a single item, and SHALL NOT let it propagate to abort the
pipeline run. For a **rate-limit (429)** specifically, the Summarizer SHALL first attempt
retry-with-backoff (see "Retry with backoff on rate-limit before skipping") and only skip the
item once retries are exhausted; for all other errors (timeout, connection, 4xx, 5xx) it SHALL
skip immediately. In every skip case the Summarizer SHALL log the failure via structured
logging (level `warn`/`error`, including item identity but NEVER the LLM key or full prompt
secrets), and SHALL **skip** the item (no `SummarizedItem` emitted for it) so the rest of the
digest still renders. The Summarizer SHALL continue processing subsequent items.

> ACs: AC-4-009 [CONFIRMED], AC-4-010 [CONFIRMED], AC-4-011 [CONFIRMED], AC-4-012 [CONFIRMED]
> Business rules: BR-4-006, BR-4-007
> Risk: RF-2 (DoS / availability), RF-4 (logging — no secret leakage)

#### Scenario: LLM timeout is caught and the run continues (AC-4-009) [CONFIRMED]
- **WHEN** the mocked LLM raises a timeout for one item during a batch of items
- **THEN** no exception propagates out of the summarization step, the failure is logged, that item is skipped, and the remaining items are still summarized

#### Scenario: LLM 5xx / 4xx / rate-limit error degrades gracefully (AC-4-010) [CONFIRMED]
- **WHEN** the mocked LLM raises a 5xx or 4xx for an item, or raises a 429 rate-limit error that is still failing after `max_retries` retries
- **THEN** the error is caught, logged once, the item is skipped, and the pipeline run is not aborted

#### Scenario: A single item failure does not lose other items' summaries (AC-4-011) [CONFIRMED]
- **WHEN** item B's LLM call fails but items A and C succeed
- **THEN** A and C produce `SummarizedItem`s and B is absent (skipped); the overall operation returns successfully

#### Scenario: Failure logs never contain the LLM key or secrets (AC-4-012) [CONFIRMED]
- **WHEN** an LLM failure is logged
- **THEN** the log record contains item identity (repo/item_type/item_id) and an error class/message but does NOT contain `Config.llm_api_key` or any secret value

## Business Rules

- **BR-V3-001-001**: The per-minute token budget defaults to 6000 (Groq free tier) and is a `SummarizerConfig` field; the window defaults to 60 seconds.
- **BR-V3-001-002**: The throttle is best-effort and in-memory per `summarize_items` batch; it never persists across runs and never changes summary content. Missing `usage` ⇒ 0 tokens recorded.
- **BR-V3-001-003**: The exact Vietnamese instruction string is `Trả lời bằng tiếng Việt.`; adding it must not change the set of item fields egressed (title+body only).
- **BR-V3-001-004**: Rate-limit retries are capped at `max_retries` (default 3); a `Retry-After` header, when present, sets the minimum wait; otherwise exponential backoff is used; exhaustion ⇒ skip-log-continue.
