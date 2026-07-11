## 1. Config tunables

- [x] 1.1 Add `tokens_per_minute: int = 6000`, `throttle_window_seconds: float = 60.0`, `max_retries: int = 3`, and `retry_backoff_base_seconds: float = 1.0` to `SummarizerConfig` (ADR-001/005). File: `src/osspulse/summarizer/config.py` _Requirements: AC-V3-001-001, AC-V3-001-006_
- [x] 1.2 Inject `sleep: Callable[[float], None] = time.sleep` and `clock: Callable[[], float] = time.monotonic` into `LiteLLMSummarizer.__init__` (testability — ADR-003), mirroring the existing `completion=` param. File: `src/osspulse/summarizer/client.py` _Requirements: AC-V3-001-001, AC-V3-001-002_

## 2. Vietnamese prompt

- [x] 2.1 Add the exact instruction `Trả lời bằng tiếng Việt.` to `_build_messages` (system content), still sending only title+body. File: `src/osspulse/summarizer/client.py` _Requirements: AC-V3-001-005_

## 3. Token-aware throttle

- [x] 3.1 Add a `TokenWindow` class (in-memory `list[(timestamp, tokens)]`, using the injected `clock`) with `record(tokens)` + `_prune()` that drops entries older than `throttle_window_seconds` (ADR-001). File: `src/osspulse/summarizer/client.py` _Requirements: AC-V3-001-001, AC-V3-001-002_
- [x] 3.2 Add `TokenWindow.sleep_if_needed()` (ADR-002): prune, then while recorded window tokens ≥ `tokens_per_minute` sleep until the oldest entry expires. Call it in `summarize` ONLY on the real-completion path (after cache-hit `return` and `_SkipItem`), and after the call record `getattr(response.usage, "total_tokens", 0) or 0` (None/missing usage ⇒ 0). File: `src/osspulse/summarizer/client.py` _Requirements: AC-V3-001-001, AC-V3-001-003, AC-V3-001-004_

## 4. Retry-then-skip on 429

- [x] 4.1 Add `_call_with_retry` wrapping `self._completion(...)` (ADR-005): catch only `RateLimitError`, retry up to `max_retries` with wait = `max(Retry-After, retry_backoff_base_seconds * 2**attempt)` (extract `Retry-After` defensively via `getattr(exc, "response", None)` → headers, fall back to backoff on any absence/parse error), then re-raise so the batch loop's existing `except openai.APIError` skip-log-continue handles it. Call it from `summarize`; leave `summarize_items` untouched. File: `src/osspulse/summarizer/client.py` _Requirements: AC-V3-001-006, AC-V3-001-007, AC-V3-001-008, AC-4-010_
- [x] 4.2 Verify throttle/retry log lines carry item identity only — no api_key, no prompt. File: `src/osspulse/summarizer/client.py` _Requirements: AC-4-012_

## 5. Tests + checkpoint

- [x] 5.1 Add unit tests (inject a recording no-op `sleep` + manual `clock` — ADR-003): sleep-when-near-budget, no-sleep-under-budget, missing-usage⇒0, cache-hit/skip adds nothing, Vietnamese instruction present, 429-then-success, Retry-After honored, retries-exhausted⇒skip. File: `tests/test_summarizer_client.py` _Requirements: AC-V3-001-001, AC-V3-001-002, AC-V3-001-003, AC-V3-001-004, AC-V3-001-005, AC-V3-001-006, AC-V3-001-007, AC-V3-001-008_
- [x] 5.2 Update the existing `test_llm_rate_limit_item_skipped_AC_4_010` to inject a no-op `sleep` and expect `max_retries` attempts BEFORE the skip (429 now retries-then-skips — ADR-005, MODIFIED AC-4-010). File: `tests/test_summarizer_client.py` _Requirements: AC-4-010, AC-V3-001-008_
- [x] 5.3 CHECKPOINT — run module test scope (`tests/test_summarizer_client.py` + `tests/test_summarizer_normalize.py` + ruff lint on `src/osspulse/summarizer/`), confirm all 8 new ACs green and AC-4-009..012/021/022 still pass, then human review. File: `src/osspulse/summarizer/` _Requirements: AC-V3-001-001, AC-V3-001-005, AC-V3-001-008, AC-4-010, AC-4-012_
