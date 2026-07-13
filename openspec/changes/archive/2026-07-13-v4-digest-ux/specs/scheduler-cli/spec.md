## ADDED Requirements

### Requirement: The run truncates each item-type group per repo to a configurable cap before summarizing
Between collection and summarization, the pipeline SHALL truncate each `(repo, item_type)`
group of collected items to at most `Config.max_items_per_type` items (default **10**),
keeping the **newest** items by `created_at` (descending) and dropping the oldest. Truncation
SHALL happen **before** the LLM summarize call so that dropped items are never sent to the
LLM (token-cost correctness). A group with `≤ max_items_per_type` items SHALL be left
unchanged. The pipeline SHALL record, per repo, the total number of items dropped by
truncation and SHALL make that count available to the renderer so a per-repo truncation
notice can be emitted (see digest-renderer). Truncation SHALL NOT change which items are
recorded as seen — `mark_seen` still records the full fetched set (idempotency unchanged).

> ACs: AC-V4-002-003 [CONFIRMED], AC-V4-002-004 [CONFIRMED], AC-V4-002-006 [CONFIRMED]
> Business rules: BR-V4-002-002, BR-V4-002-003
> Risk: RF-1 (cost control), RF-2 (readability)

#### Scenario: A group over the cap keeps the newest N and drops the rest before the LLM call (AC-V4-002-003) [CONFIRMED]
- **WHEN** a repo has 15 `issue` items collected and `max_items_per_type = 10`
- **THEN** only the 10 newest issues (by `created_at` descending) are passed to the summarizer, the 5 oldest are dropped and never sent to the LLM, and the recorded dropped-count for that repo is at least 5

#### Scenario: A group exactly at the cap is not truncated and drops nothing (AC-V4-002-004) [CONFIRMED]
- **WHEN** a repo has exactly `max_items_per_type` items of a type
- **THEN** none are dropped, all are summarized, and the recorded dropped-count for that group is 0 (off-by-one guard)

#### Scenario: Dropped items are excluded from summarization but still marked seen (AC-V4-002-006) [CONFIRMED]
- **WHEN** truncation drops the oldest items of a group
- **THEN** the summarizer is invoked only with the surviving newest items, and `state.mark_seen` is still called with the full collected set (dropped items are recorded as seen so they are not re-fetched next run)

### Requirement: Per-type item cap is config-driven and validated fail-fast
The item cap SHALL be read from the `[watchlist]` config section as `max_items_per_type`
(positive integer, default **10** when the key is absent). At load time `config.py` SHALL
validate it is a strict `int` (rejecting `bool`, `float`, and string values) that is `≥ 1`;
any violation SHALL raise `ConfigError` before the pipeline runs (fail fast, mirroring the
`lookback_days` guard). The resolved value SHALL be carried on `Config` as
`max_items_per_type`.

> ACs: AC-V4-002-005 [CONFIRMED]
> Business rules: BR-V4-002-004

#### Scenario: max_items_per_type defaults to 10 when absent (AC-V4-002-005) [CONFIRMED]
- **WHEN** a config file has a `[watchlist]` section with no `max_items_per_type` key
- **THEN** `load_config` returns a `Config` with `max_items_per_type = 10`

#### Scenario: A non-positive or non-int max_items_per_type fails validation (AC-V4-002-005b) [CONFIRMED]
- **WHEN** `[watchlist] max_items_per_type` is `0`, `-1`, `"10"`, `true`, or `2.5`
- **THEN** `load_config` raises `ConfigError` with a clear message, before the pipeline runs (strict positive-int check, mirroring `lookback_days`)
