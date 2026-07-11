# summarizer Specification

## Purpose
TBD - created by archiving change summarizer-llm-4. Update Purpose after archive.
## Requirements
### Requirement: Summarize a RawItem into a 1–2 sentence summary via LiteLLM
The Summarizer SHALL implement the existing `osspulse.ports.LLMClient` Protocol
(`summarize(item: RawItem) -> str`) using **LiteLLM** with the operator-configured
provider (`Config.llm_provider` / `Config.llm_api_key`). Given a `RawItem`, it SHALL
build a prompt from `RawItem.title` and `RawItem.body` and return a plain-text summary
constrained to **1–2 sentences**. The V1 change SHALL NOT alter the `LLMClient`
Protocol signature.

> ACs: AC-4-001 [CONFIRMED], AC-4-002 [CONFIRMED], AC-4-003 [CONFIRMED]
> Business rules: BR-4-001, BR-4-002
> Integration: INT-4-001

#### Scenario: A RawItem is summarized into a 1–2 sentence string (AC-4-001) [CONFIRMED]
- **WHEN** `summarize(item)` is called with a `RawItem` having non-empty `title`/`body` and the mocked LLM returns a short paragraph
- **THEN** the return value is a non-empty plain-text `str` of at most 2 sentences derived from the item's title and body

#### Scenario: The LLM is called through LiteLLM with the configured provider (AC-4-002) [CONFIRMED]
- **WHEN** `summarize(item)` is invoked and no cached summary exists
- **THEN** exactly one LLM completion call is made via LiteLLM using `Config.llm_provider`/`llm_api_key`, and the prompt input contains the item's title and body

#### Scenario: The LLMClient Protocol signature is unchanged (AC-4-003) [CONFIRMED]
- **WHEN** the V1 summarizer is added
- **THEN** `osspulse.ports.LLMClient` still declares exactly `summarize(item: RawItem) -> str`; any cache-aside/normalization helpers live on the concrete adapter, not the Protocol

### Requirement: Cache-aside over Redis to avoid re-summarizing
The Summarizer SHALL apply a **cache-aside** strategy using the existing
`osspulse.ports.SummaryCache` Protocol (`get(key) -> str | None`,
`set(key, value) -> None`). Before calling the LLM it SHALL compute the cache key and
call `get`; on a **hit** (non-`None`) it SHALL return the cached summary WITHOUT
calling the LLM; on a **miss** (`None`) it SHALL call the LLM and then `set` the result
under that key.

> ACs: AC-4-004 [CONFIRMED], AC-4-005 [CONFIRMED], AC-4-006 [CONFIRMED]
> Business rules: BR-4-003, BR-4-004
> Integration: INT-4-002

#### Scenario: Cache hit returns cached summary without an LLM call (AC-4-004) [CONFIRMED]
- **WHEN** `SummaryCache.get(key)` returns a non-`None` cached summary for the item
- **THEN** that cached value is returned and the LLM (LiteLLM) is NOT called (mock LLM records zero calls)

#### Scenario: Cache miss calls the LLM then stores the result (AC-4-005) [CONFIRMED]
- **WHEN** `SummaryCache.get(key)` returns `None`
- **THEN** the LLM is called exactly once and the resulting summary is written back via `SummaryCache.set(key, summary)`

#### Scenario: Cache key follows the conventions format (AC-4-006) [CONFIRMED]
- **WHEN** the cache key is computed for an item
- **THEN** it equals `summary:{repo}:{item_type}:{item_id}:{content_hash}` where `content_hash` is a stable hash of the exact text sent to the LLM (title+body)

### Requirement: Content-hash keying invalidates on edited content
The `content_hash` segment of the cache key SHALL be a deterministic, stable hash
(SHA-256 hex of `title + "\n" + body` actually submitted to the LLM, after
any truncation). Identical input SHALL produce an identical key (cache reuse); a
changed `body`/`title` SHALL produce a different key so an edited issue is
re-summarized rather than served a stale cached summary.

> ACs: AC-4-007 [CONFIRMED], AC-4-008 [CONFIRMED]
> Business rules: BR-4-005

#### Scenario: Same content yields the same cache key (AC-4-007) [CONFIRMED]
- **WHEN** two `RawItem`s share the same `repo`, `item_type`, `item_id`, `title`, and `body`
- **THEN** they produce an identical `content_hash` and therefore the same cache key (so the second is a cache hit)

#### Scenario: Changed body yields a different cache key (AC-4-008) [CONFIRMED]
- **WHEN** an item's `body` changes between runs (same `repo`/`item_type`/`item_id`)
- **THEN** the `content_hash` differs, the key differs, the prior cache entry is NOT reused, and the item is re-summarized

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

### Requirement: Best-effort cache — Redis failure must not crash the run
The cache layer SHALL be **best-effort**: the Summarizer SHALL catch a failure of
`SummaryCache.get` or `SummaryCache.set` (e.g. Redis unavailable / connection error)
and SHALL treat it as a cache miss for `get` (proceed to call the LLM) or a no-op for
`set` (log and continue). A cache failure SHALL NEVER raise into the pipeline or
prevent a summary from being produced.

> ACs: AC-4-013 [CONFIRMED], AC-4-014 [CONFIRMED]
> Business rules: BR-4-004, BR-4-008
> Risk: RF-2 (availability)

#### Scenario: Cache get failure is treated as a miss (AC-4-013) [CONFIRMED]
- **WHEN** `SummaryCache.get(key)` raises (Redis down)
- **THEN** the error is caught and the Summarizer proceeds to call the LLM (treats it as a miss), producing a summary without raising

#### Scenario: Cache set failure does not abort or lose the summary (AC-4-014) [CONFIRMED]
- **WHEN** the LLM produced a summary and `SummaryCache.set(key, value)` raises (Redis down)
- **THEN** the failure is logged and the produced summary is still returned/used; no exception propagates

### Requirement: Length and output normalization (1–2 sentence contract)
The Summarizer SHALL enforce the 1–2 sentence contract defensively: it SHALL instruct
the LLM to answer in at most 2 sentences AND SHALL normalize the returned text
(trim whitespace, collapse to plain text). If the LLM returns more than 2 sentences or
multi-paragraph text, the Summarizer SHALL normalize/truncate it to at most 2 sentences
rather than rejecting it. The returned summary SHALL NOT echo the prompt template or
contain raw newlines that break the digest's per-line rendering.

> ACs: AC-4-015 [CONFIRMED], AC-4-016 [CONFIRMED]
> Business rules: BR-4-001, BR-4-002

#### Scenario: Over-long LLM output is normalized to ≤2 sentences (AC-4-015) [CONFIRMED]
- **WHEN** the mocked LLM returns 4 sentences / multiple paragraphs
- **THEN** the returned summary is normalized to at most 2 sentences (the rest dropped), not raised as an error

#### Scenario: Whitespace and prompt leakage are stripped (AC-4-016) [CONFIRMED]
- **WHEN** the LLM returns text with leading/trailing whitespace or surrounding markdown fences
- **THEN** the returned summary is trimmed plain text suitable for a single Markdown bullet line

### Requirement: Input boundary handling for empty, huge, and dirty RawItems
The Summarizer SHALL treat `RawItem` text as untrusted/dirty data. A `RawItem` with an
empty/whitespace-only `body` SHALL be summarized from `title` alone. A `RawItem` with
both `title` AND `body` empty/whitespace-only SHALL be skipped WITHOUT calling the LLM
(nothing to summarize). An over-long `body` SHALL be truncated to **8 000 characters**
before the LLM call to cap token cost, and the truncated text SHALL be the text
that is both summarized and hashed into the cache key.

> ACs: AC-4-017 [CONFIRMED], AC-4-018 [CONFIRMED], AC-4-019 [CONFIRMED]
> Business rules: BR-4-002, BR-4-009
> Risk: RF-3 (cost / DoS via oversized input)

#### Scenario: Empty body summarizes from title alone (AC-4-017) [CONFIRMED]
- **WHEN** `summarize(item)` is called with non-empty `title` and empty `body`
- **THEN** the LLM is called with the title as input and a 1–2 sentence summary is returned (no crash on the empty body)

#### Scenario: Fully empty item is skipped without an LLM call (AC-4-018) [CONFIRMED]
- **WHEN** both `title` and `body` are empty/whitespace-only
- **THEN** no LLM call is made and the item is skipped (no `SummarizedItem`), with no exception raised

#### Scenario: Over-long body is truncated before the LLM call and hashed post-truncation (AC-4-019) [CONFIRMED]
- **WHEN** an item's `body` exceeds **8 000 characters**
- **THEN** the input is truncated to 8 000 chars before the LLM call, and the `content_hash` is computed over the truncated input so the cache key is stable across runs

### Requirement: Idempotent re-run produces no duplicate LLM cost
Re-running summarization over the same set of unchanged items SHALL be idempotent with
respect to LLM cost: the second run SHALL serve every unchanged item from the cache and
SHALL make zero new LLM calls. This preserves the project's idempotency principle and
caps LLM token spend.

> ACs: AC-4-020 [CONFIRMED]
> Business rules: BR-4-003, BR-4-004
> Risk: RF-1 (cost control)

#### Scenario: Second run over identical items makes zero LLM calls (AC-4-020) [CONFIRMED]
- **WHEN** the same unchanged items are summarized a second time with a populated cache
- **THEN** every item is a cache hit and the mocked LLM records zero calls on the second run

### Requirement: Pure LLM boundary — no GitHub / cross-stage calls
The Summarizer SHALL be pure LLM-and-cache I/O: it SHALL NOT call the GitHub Collector
(S2), the State Store (S3), or any network other than the configured LLM provider and
the Redis summary cache. It SHALL depend only on `osspulse.models` (`RawItem`,
`SummarizedItem`), the `LLMClient`/`SummaryCache` ports, LiteLLM, and the standard
library. The LLM API key SHALL be read from configuration/env, never hardcoded.

> ACs: AC-4-021 [CONFIRMED], AC-4-022 [CONFIRMED]
> Business rules: BR-4-010
> Integration: INT-4-001, INT-4-002
> Risk: RF-5 (data egress boundary)

#### Scenario: No GitHub or state-store calls during summarization (AC-4-021) [CONFIRMED]
- **WHEN** the Summarizer summarizes items
- **THEN** it performs only LLM (LiteLLM) and `SummaryCache` calls — no GitHub I/O, no State Store I/O, no other network

#### Scenario: LLM key comes from config/env, never hardcoded (AC-4-022) [CONFIRMED]
- **WHEN** the LiteLLM client is constructed
- **THEN** the API key is sourced from `Config.llm_api_key` (env/`.env`), and no secret literal appears in the summarizer source

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

