# Tasks — summarizer-llm-4 (S4 Summarizer)

> Order: foundational/pure (errors → config → keys → normalize) → cache adapter → LLM
> adapter + batch → wiring → tests. Tests follow the code they test (R10). All tests mock
> LiteLLM (`completion` callable) + cache; NO real network (stack.md, A-C8). `summarizer/`
> and `cache/` import ONLY `osspulse.models`/`osspulse.ports`/`litellm`/`redis`/stdlib
> (AC-4-021). See design.md §Implementation Guide.

## 1. Errors + Config (foundational, no deps)

- [x] 1.1 Define `SummarizerError` base + `SummarizationFailed` (token-safe messages: item identity + static reason only, no key/prompt/body). Mirror `github/errors.py` docstring style.
  File: `src/osspulse/summarizer/errors.py`
  _Requirements: AC-4-012_
- [x] 1.2 Define frozen `SummarizerConfig` (`model: str`, `request_timeout_seconds: float = 30.0`, `input_char_cap: int = 8000`, `max_sentences: int = 2`, `max_summary_chars: int = 600`). NO secret/api_key field (RF-4). Mirror `github/config.py` (`CollectorConfig`).
  File: `src/osspulse/summarizer/config.py`
  _Requirements: AC-4-019, AC-4-022_

## 2. Pure helpers — keys + normalization

- [x] 2.1 Implement `content_hash(title, body) -> str` = `sha256((title + "\n" + body).encode("utf-8")).hexdigest()`, and `cache_key(item, content_hash) -> str` = `f"summary:{item.repo}:{item.item_type}:{item.item_id}:{content_hash}"`.
  File: `src/osspulse/summarizer/keys.py`
  _Requirements: AC-4-006, AC-4-007, AC-4-008_
- [x] 2.2 Implement `prepare_input(item) -> tuple[str, str]`: dirty-data guard (`(item.title or "")`, `(item.body or "")`), strip, truncate body+title to `input_char_cap` (8000) — truncation is the text that is both hashed and sent (AC-4-019).
  File: `src/osspulse/summarizer/normalize.py`
  _Requirements: AC-4-017, AC-4-019_
- [x] 2.3 Implement `normalize_summary(text) -> str`: strip surrounding ``` fences/backticks + whitespace, collapse whitespace/newlines to single spaces, mask common abbreviations (`e.g. i.e. etc. vs. U.S. Mr. Dr.`), split on `(?<=[.!?])\s+`, keep first `max_sentences` (2), unmask, re-join; raise `SummarizationFailed` if result is empty/whitespace (EC-012).
  File: `src/osspulse/summarizer/normalize.py`
  _Requirements: AC-4-015, AC-4-016_
- [x] 2.4 Unit tests for keys + normalize: same content→same hash (AC-4-007); changed body→different hash (AC-4-008); key format (AC-4-006); empty body→title-only input (AC-4-017); huge body→truncated to 8000 then hashed (AC-4-019); >2 sentences→≤2 (AC-4-015); fences/whitespace/markdown stripped (AC-4-016); empty output→`SummarizationFailed` (EC-012); non-ASCII/emoji/CJK safe (EC-004).
  File: `tests/test_summarizer_normalize.py`
  _Requirements: AC-4-006, AC-4-007, AC-4-008, AC-4-015, AC-4-016, AC-4-017, AC-4-019_

## 3. Redis cache adapter

- [x] 3.1 Implement `RedisSummaryCache` (`SummaryCache` port): `__init__(self, client: redis.Redis)` injected; `get(key) -> str | None` (decode bytes→str, missing→`None`, may raise on transport error — faithful port); `set(key, value) -> None`. NO best-effort swallow here (lives in adapter per ADR-004).
  File: `src/osspulse/cache/redis_cache.py`
  _Requirements: AC-4-004, AC-4-005, AC-4-013, AC-4-014_
- [x] 3.2 Unit tests for `RedisSummaryCache` with a fake/in-memory redis client: get hit returns decoded str; get miss returns `None`; set stores value; raising client propagates (best-effort handled upstream). NO real Redis.
  File: `tests/test_redis_cache.py`
  _Requirements: AC-4-004, AC-4-005_

## 4. CHECKPOINT — foundation review (mid-build)

- [x] 4.1 CHECKPOINT (human review): run `uv run ruff check src tests` + `uv run pytest tests/test_summarizer_normalize.py tests/test_redis_cache.py -q`. Confirm: keys/normalize/cache green; no `import osspulse.github`/`osspulse.state` under `summarizer/`/`cache/` (AC-4-021); `SummarizerConfig` has no key field (RF-4). STOP and wait for user sign-off before the LLM adapter.
  File: `tests/test_summarizer_normalize.py`
  _Requirements: AC-4-021, AC-4-022_

## 5. LiteLLM summarizer adapter (single-item cache-aside)

- [x] 5.1 Implement `LiteLLMSummarizer.__init__(self, *, provider, api_key, cache, config, completion=litellm.completion)` — hold `api_key` as a private attr (never logged/repr); `logging.getLogger(__name__)`. Implement `_identity(item)`, `_build_messages(title, body)` (system: "≤2 sentences, plain text, no markdown"; user: `Title: {title}\n\nBody: {body}`) — title+body only (RF-1).
  File: `src/osspulse/summarizer/client.py`
  _Requirements: AC-4-001, AC-4-002, AC-4-022_
- [x] 5.2 Implement `_cache_get(key)` / `_cache_set(key, value)` best-effort wrappers: `try: ... except Exception: log warning (key/identity only) + return None / no-op` (ADR-004). This is the ONLY broad-except in the change.
  File: `src/osspulse/summarizer/client.py`
  _Requirements: AC-4-013, AC-4-014_
- [x] 5.3 Implement `summarize(item) -> str` (Flow 1): `prepare_input` → if title+body both empty raise internal `_SkipItem` (AC-4-018) → `content_hash`/`cache_key` → `_cache_get` hit returns (no LLM call, AC-4-004) → miss: `completion(model, messages, api_key, timeout=request_timeout_seconds)` exactly once (AC-4-005) → `normalize_summary` → `_cache_set` → return. LLM key from config, no hardcode (AC-4-022).
  File: `src/osspulse/summarizer/client.py`
  _Requirements: AC-4-001, AC-4-002, AC-4-003, AC-4-004, AC-4-005, AC-4-013, AC-4-014, AC-4-017, AC-4-019, AC-4-022_
- [x] 5.4 Export public symbols: `LiteLLMSummarizer`, `SummarizerConfig` from summarizer; `RedisSummaryCache` from cache.
  File: `src/osspulse/summarizer/__init__.py`
  _Requirements: AC-4-001, AC-4-003_
- [x] 5.5 Unit tests for `summarize()` single-item: cache hit → zero `completion` calls, cached value returned (AC-4-004); miss → exactly one call then `set` (AC-4-005); key format end-to-end (AC-4-006); cache-get raises → treated as miss, LLM called, no raise (AC-4-013); cache-set raises → summary still returned (AC-4-014); empty body → title-only call (AC-4-017); huge body → truncated-then-hashed (AC-4-019); Protocol unchanged: `LLMClient.summarize` signature still `(item)->str` (AC-4-003); no secret literal in source / key sourced from config (AC-4-022).
  File: `tests/test_summarizer_client.py`
  _Requirements: AC-4-003, AC-4-004, AC-4-005, AC-4-006, AC-4-013, AC-4-014, AC-4-017, AC-4-019, AC-4-022_

## 6. Batch degradation + boundary (skip-log-continue)

- [x] 6.1 Implement `summarize_items(items) -> list[SummarizedItem]` (Flow 2): per-item try → `SummarizedItem(raw=item, summary=summarize(item))`; `except _SkipItem: continue` (fully-empty, AC-4-018); `except SummarizationFailed: log warning + continue` (EC-012); `except litellm.exceptions.APIError: log warning (identity + error class, NEVER key/prompt) + continue` (AC-4-009/010). Return survivors (AC-4-011).
  File: `src/osspulse/summarizer/client.py`
  _Requirements: AC-4-009, AC-4-010, AC-4-011, AC-4-012, AC-4-018, AC-4-020, AC-4-021_
- [x] 6.2 Unit tests for `summarize_items()`: LLM timeout (`litellm.exceptions.Timeout`) → item skipped, others summarized, no raise (AC-4-009); 4xx/5xx/429 (`BadRequestError`/`InternalServerError`/`RateLimitError`) → skip+continue (AC-4-010); item B fails, A+C succeed → A,C returned, B absent (AC-4-011); failure log contains identity but NOT `api_key`/prompt (AC-4-012); fully-empty item → skipped, zero LLM calls (AC-4-018); second run over unchanged items with populated cache → zero `completion` calls (AC-4-020); assert no GitHub/state import or call — only `completion` + cache used (AC-4-021). Use REAL `litellm.exceptions.*` instances (ADR-002 risk mitigation).
  File: `tests/test_summarizer_client.py`
  _Requirements: AC-4-009, AC-4-010, AC-4-011, AC-4-012, AC-4-018, AC-4-020, AC-4-021_

## 7. CHECKPOINT — final (coverage + security scan)

- [x] 7.1 CHECKPOINT (human review + gates): `uv run ruff check src tests` clean; `uv run pytest --cov=osspulse --cov-report=term-missing` ≥ 80% lines (stack.md); all 22 ACs traced to ≥1 asserting test; security scan — grep source for any secret literal / `api_key` in logs (AC-4-012/022), confirm `summarizer/`+`cache/` import only allowed modules (AC-4-021), confirm 30s timeout passed to `completion` (RF-2), confirm only title+body egress (RF-1). STOP and wait for user sign-off → DESIGN REVIEW / S4 complete.
  File: `tests/test_summarizer_client.py`
  _Requirements: AC-4-009, AC-4-010, AC-4-011, AC-4-012, AC-4-020, AC-4-021, AC-4-022_
