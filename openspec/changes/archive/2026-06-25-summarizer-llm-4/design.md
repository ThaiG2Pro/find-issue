## Sketch — Gap Analysis

**No critical gaps found.** All 22 ACs are CONFIRMED at SPEC LOCK (0 ASSUMED remaining);
the 5 SPEC-LOCK answers (SHA-256 of `title\nbody`; skip-not-placeholder; 8000-char cap;
no TTL; no bespoke retry) remove every open requirement decision. The analyst's 5 WATCH
items are architect-level design calls (resolved below as ADRs), not spec gaps. Entity
model (`RawItem` → `SummarizedItem`) is frozen and fixed; no contradictory BRs.

**Minor (documented, not a gap):** `LLMClient.summarize(item) -> str` returns a string,
but graceful-skip (AC-4-011/AC-4-018) means "no `SummarizedItem` emitted". A single
`-> str` method cannot represent "skip". This is a *batch-loop* concern that lives ABOVE
the single-item Protocol method, not a Protocol change. Resolved by ADR-005 (a separate
`summarize_items()` batch helper on the adapter; the Protocol stays unchanged per AC-4-003).

**openapi.yaml: N/A** — OSS Pulse is a CLI tool with no HTTP API (confirmed with user;
consistent with changes 2 + 3). Per R5/R9, the API artifact is intentionally omitted; the
"API Design" section documents the internal stage contract instead.

---

## Context

OSS Pulse is a linear pipeline (Config → Collector → State Store → **Summarizer** →
Render → Deliver). This change builds **S4 Summarizer**: turn a `RawItem` (GitHub issue
title+body) into a **1–2 sentence** plain-text summary via **LiteLLM**, behind the
existing `osspulse.ports.LLMClient` Protocol, with **cache-aside over Redis**
(`SummaryCache` port) and **graceful degradation** on any LLM/cache failure.

**Current state:** `src/osspulse/summarizer/` and `src/osspulse/cache/` exist as empty
packages (`__init__.py` only). `ports.py` declares `LLMClient.summarize(item) -> str` and
`SummaryCache.get/set`. `models.py` declares frozen `RawItem`, `SummarizedItem`, `Config`
(with `llm_provider`/`llm_api_key`). LiteLLM 1.89.3 and redis 8.0.0 are already pinned in
`pyproject.toml`.

**Constraints:**
- V1 must NOT change the `LLMClient` / `SummaryCache` Protocol signatures (AC-4-003).
- S4 must NOT import/call S2 (GitHub) or S3 (State Store) — only LiteLLM + cache + stdlib
  + `osspulse.models`/`osspulse.ports` (AC-4-021, BR-4-010).
- Privacy non-negotiable: send ONLY `title`+`body` to the single configured provider (RF-1).
- Tests mock LiteLLM + cache; NO real network (stack.md).

**Precedent followed (changes 2 + 3):** injectable adapter (`__init__` takes the client +
a frozen tunables config); token-safe error hierarchy with static messages; `logging`
module logger; dirty-data guards (`or ""`); bool-trap guard pattern (`type(x) is int`).

## Goals / Non-Goals

**Goals:**
- Implement `LLMClient.summarize(item: RawItem) -> str` via LiteLLM (AC-4-001/002/003).
- Cache-aside over `SummaryCache` with the conventions key format (AC-4-004/005/006).
- Content-hash keying that invalidates on edit (AC-4-007/008).
- Graceful degradation: per-item LLM failure → catch, log (no secrets), skip, continue
  (AC-4-009/010/011/012).
- Best-effort cache: get/set failure → miss/no-op, never crash (AC-4-013/014).
- Defensive 1–2 sentence normalization (AC-4-015/016).
- Input boundary handling: empty-body→title-only, fully-empty→skip-no-call,
  over-long→truncate-to-8000-then-hash (AC-4-017/018/019).
- Idempotent re-run → zero new LLM calls (AC-4-020).
- Pure LLM/cache boundary; key from config, never hardcoded (AC-4-021/022).

**Non-Goals:**
- Changing any Protocol signature (cache-aside/normalization stay adapter-private).
- Bespoke LLM retry/backoff (A-A7 — rely on LiteLLM defaults; error → skip).
- Cache TTL (A-A6 — content-hash is the only invalidation).
- Discussions/releases, the meta-summary, rendering (S5), delivery (S6) — out of V1/scope.
- Cache-value validation beyond "non-empty string" (EC-014 — best-effort, documented limit).
- Concurrency locking (single-operator tool; EC-010/011 documented harmless).

## Architecture Overview

Two new adapter modules under the existing hexagonal-lite layout. Core depends on ports;
adapters depend on `osspulse.models` only — never on each other.

```
src/osspulse/
  ports.py                    # UNCHANGED — LLMClient, SummaryCache Protocols
  models.py                   # UNCHANGED — RawItem, SummarizedItem, Config
  summarizer/
    __init__.py               # re-export LiteLLMSummarizer, SummarizerConfig
    config.py                 # SummarizerConfig (frozen tunables: timeout, cap, model…)
    errors.py                 # SummarizerError base + SummarizationFailed (token-safe)
    keys.py                   # content_hash() + cache_key() — pure functions
    normalize.py              # prepare_input(), normalize_summary() — pure functions
    client.py                 # LiteLLMSummarizer — the LLMClient adapter + batch helper
  cache/
    __init__.py               # re-export RedisSummaryCache
    redis_cache.py            # RedisSummaryCache — SummaryCache adapter (thin)
```

**Cross-spec dependencies (from `openspec list` + living specs):**
- Reuses `LLMClient` + `SummaryCache` ports unchanged (change 1 / scaffolding).
- Mirrors the **adapter+frozen-config+injected-client** pattern from `github-collector-2`
  (`github/client.py`, `github/config.py`) and the **token-safe error hierarchy** from
  `github/errors.py`.
- Consumes `RawItem`, emits `SummarizedItem` — both frozen (state-store-3 / scaffolding).
- No conflict with existing exports; adds new modules only.

**Layering / boundary (AC-4-021):** `summarizer/` and `cache/` import only `osspulse.models`,
`osspulse.ports`, `litellm`, `redis`, and stdlib. A QA-checkable invariant: no `import`
of `osspulse.github` or `osspulse.state` anywhere under `summarizer/` or `cache/`.

## Decisions (ADRs)

### ADR-001 — Cache-aside lives inside the concrete summarizer adapter, not on the Protocol

**Context:** AC-4-003 forbids changing `LLMClient` (`summarize(item) -> str`). Cache-aside
(AC-4-004/005/006) needs `SummaryCache` access around the LLM call. Where does the
orchestration live?

| Option | Pros | Cons |
|---|---|---|
| A. Cache-aside inside the adapter; adapter holds a `SummaryCache` ref injected at `__init__` | Protocol unchanged (AC-4-003); single class implements `summarize`; mirrors `GitHubCollector` injection | Adapter has two collaborators (LLM + cache) |
| B. Add `get/set` cache methods to the `LLMClient` Protocol | All in one interface | **Violates AC-4-003**; couples two concerns; rejected by analyst D1/D2 |
| C. Separate `CachedSummarizer` wrapper that decorates a raw `LLMClient` | Clean separation | Two classes to wire; the wrapper still needs to BE an `LLMClient`; over-engineered for V1 single adapter |

**Decision:** **A.** `LiteLLMSummarizer.__init__(self, *, api_key, provider, cache, config, completion=litellm.completion)`. `summarize()` runs the cache-aside flow internally. Matches `GitHubCollector`'s injected-client precedent and keeps the Protocol frozen.

**Consequences:** The adapter depends on both the `SummaryCache` port and LiteLLM. Cache is injected (best-effort wrapper applied inside the adapter). Easy to test (inject a fake cache + a fake `completion`).

### ADR-002 — Single LLM error boundary: catch `litellm.exceptions.APIError`

**Context:** AC-4-009/010 require catching timeout, connection error, 429, 4xx, 5xx as one
graceful-skip class. LiteLLM raises many exception types.

| Option | Pros | Cons |
|---|---|---|
| A. Catch `litellm.exceptions.APIError` (verified common base of Timeout/RateLimit/APIConnection/Authentication/BadRequest/InternalServer…) | One catch covers all documented LLM failures; precise (won't swallow `ValueError`/bugs) | Tied to litellm's hierarchy (acceptable — it is our only LLM lib) |
| B. Catch bare `Exception` | Catches everything | Swallows programming bugs (KeyError/TypeError) → hides defects; violates "don't mask bugs" |
| C. Enumerate each subclass in the `except` tuple | Explicit | Verbose, drift-prone as litellm adds error types |

**Decision:** **A.** `except litellm.exceptions.APIError as exc:` is the LLM-failure boundary. Verified via MRO that `Timeout`, `RateLimitError`, `APIConnectionError`, `AuthenticationError`, `BadRequestError`, `InternalServerError`, `ServiceUnavailableError` all derive from `APIError`. Re-raise nothing; log + skip.

**Consequences:** Programming errors still propagate (good). If a future litellm version moves an error outside `APIError`, a test using a real litellm exception class will catch the regression. Empty-output (EC-012) is handled separately (ADR-006), not via this except.

### ADR-003 — `content_hash` = SHA-256 hex of `title + "\n" + body` (post-truncation)

**Context:** AC-4-006/007/008 + SPEC-LOCK Q1. Need a stable, edit-sensitive key segment.

| Option | Pros | Cons |
|---|---|---|
| A. `sha256((title + "\n" + body).encode("utf-8")).hexdigest()` over the **truncated** text | Newline separator prevents `("ab","c")` vs `("a","bc")` collisions; UTF-8 safe (EC-004); stable; edit-sensitive (AC-4-008); hashing truncated text keeps key stable across runs (AC-4-019) | none material |
| B. `sha256(title+body)` no separator | Simpler | Concatenation-collision risk (rejected at SPEC LOCK) |
| C. Hash a `json.dumps({...})` | Structured | Ordering/whitespace fragility; heavier; unneeded |

**Decision:** **A** — exactly the SPEC-LOCK Q1 answer. Lives in `keys.py` as a pure
`content_hash(title: str, body: str) -> str`. **Hash input = the SAME truncated text sent to
the LLM** (AC-4-019), so truncation happens before both the call and the hash.

**Consequences:** Editing title or body changes the key → re-summarize (AC-4-008). Same
content → same key → cache hit + idempotent re-run (AC-4-007/020). `cache_key()` composes
`f"summary:{repo}:{item_type}:{item_id}:{content_hash}"` (AC-4-006).

### ADR-004 — Best-effort cache via a try/except wrapper in the adapter (not in the Redis class)

**Context:** AC-4-013/014/BR-4-004: a Redis `get`/`set` failure must degrade (miss / no-op),
never crash. Where does the swallow-and-log live?

| Option | Pros | Cons |
|---|---|---|
| A. `RedisSummaryCache` stays a thin literal `SummaryCache` (may raise); the adapter wraps `get`/`set` in try/except `Exception` → miss/no-op | Keeps the port honest (`get/set` can raise per the real Redis client); best-effort policy is one place; a fake cache that raises is trivial to test | Adapter owns the policy (acceptable — it owns degradation) |
| B. `RedisSummaryCache.get/set` swallow internally | Callers never see failures | Hides failures from any other future caller; conflates transport with policy; harder to test "raises" |

**Decision:** **A.** Adapter helpers `_cache_get(key)` / `_cache_set(key, val)` wrap the port
call in `try/except Exception` (Redis/transport errors are broad and lib-specific, so a broad
catch is correct HERE — this is I/O degradation, not logic). `get` failure → return `None`
(treated as miss → call LLM). `set` failure → log + return (summary still used). Logged at
`warning`, key/identity only.

**Consequences:** A downed Redis never aborts a run (RF-2). The Redis adapter itself stays a
faithful, testable `SummaryCache`. Note: this is the one intentional broad-`except Exception`
(scoped to cache I/O), distinct from ADR-002's precise LLM boundary.

### ADR-005 — Batch helper `summarize_items()` for skip semantics; `summarize()` stays `-> str`

**Context:** AC-4-011/018 require "no `SummarizedItem` emitted" on failure/empty — but
`summarize(item) -> str` cannot express "skip". The pipeline needs a list of survivors.

| Option | Pros | Cons |
|---|---|---|
| A. Add `summarize_items(items) -> list[SummarizedItem]` adapter helper (NOT on Protocol) that calls `summarize()` per item, catches `APIError` + skip-sentinel, drops failures/empties | Protocol unchanged (AC-4-003); skip semantics live where the batch is (AC-4-011); mirrors state-store's adapter-only `is_seen/mark_seen` | One extra public method |
| B. Make `summarize()` return `str \| None` | Single method | Changes the Protocol's effective contract (AC-4-003); forces every caller to handle `None` |
| C. Raise from `summarize()` and let the pipeline catch | Minimal adapter | Pushes graceful-degradation into core/pipeline; spreads the policy; harder to unit-test skip |

**Decision:** **A.** `summarize(item) -> str` is the pure single-item Protocol method (cache-
aside + LLM + normalize), and raises `SummarizationFailed`/`APIError` or a skip signal for
fully-empty input. `summarize_items(items) -> list[SummarizedItem]` is the batch entry point
that owns the catch-log-skip-continue loop and empty-skip, returning only survivors.

**Consequences:** Two clear entry points. The pipeline (future S7 wiring) calls
`summarize_items`. Single-item `summarize` is still spec-faithful to the Protocol and
independently testable. Fully-empty items are filtered in the batch loop before any LLM call
(AC-4-018). Adapter-only helpers mirror ADR-001 of state-store-3.

### ADR-006 — Sentence normalization: regex split on `.!?`, keep ≤2; empty output → fail

**Context:** AC-4-015/016 + WATCH (A-A3). Defensively cap to ≤2 sentences; strip fences/
whitespace/newlines; EC-012 (empty/whitespace output) must be treated as a failed summary.

| Option | Pros | Cons |
|---|---|---|
| A. Strip → collapse internal whitespace/newlines to single spaces → strip surrounding markdown fences → split into sentences on a regex boundary `(?<=[.!?])\s+` → keep first 2 → re-join | Simple, deterministic, UTF-8 safe; no NLP dep (search-first: stdlib `re` suffices, no nltk/spacy) | Naive on abbreviations ("e.g.", "U.S.") — may over-split |
| B. Add an NLP sentence tokenizer (nltk/spacy) | Accurate splitting | Heavy dep for a soft contract; over-engineering ban (architecture.md); offline-model friction |
| C. No splitting, just truncate to N chars | Trivial | Cuts mid-sentence; violates "≤2 sentences" intent |

**Decision:** **A** (search-first: rejected adding an NLP lib — stdlib `re` is sufficient for a
soft contract). `normalize_summary(text) -> str`: trim → strip leading/trailing ```` ``` ````
fences/backticks → collapse all whitespace runs (incl. newlines) to single spaces → split on
`(?<=[.!?])\s+` → take first 2 non-empty sentences → join with a space. **Abbreviation guard:**
before splitting, protect a small set of common abbreviations (`e.g.`, `i.e.`, `etc.`, `vs.`,
`U.S.`, `Mr.`, `Dr.`) by temporarily masking their dots, then unmask after the split — keeps
the rule simple while avoiding the worst over-split cases (active_concern A-A3). If the
normalized result is empty/whitespace → raise `SummarizationFailed` (EC-012) so the item is
skipped, never cached as empty.

**Consequences:** No new dependency. Over-long output is normalized, not rejected (AC-4-015).
Markdown/newlines stripped to a single clean bullet line (AC-4-016). Empty LLM output is a
skip (EC-012), and is NOT written to cache (no poison-empty entries). The abbreviation list is
a documented best-effort heuristic, not exhaustive.

### ADR-007 — Frozen `SummarizerConfig` for all tunables; explicit 30s LiteLLM timeout

**Context:** RF-2 (bound a hung LLM), RF-3 (cap cost), and the lessons-learned action item
"config-driven tunables". Mirror `CollectorConfig`.

| Option | Pros | Cons |
|---|---|---|
| A. Frozen `SummarizerConfig(model, request_timeout_seconds=30.0, input_char_cap=8000, max_sentences=2, max_summary_chars=600)` injected at `__init__` | One place for all literals (matches `CollectorConfig`/lessons-learned); `timeout=` passed to `litellm.completion` bounds "hung" (RF-2); cap enforced (RF-3) | Slightly more wiring |
| B. Inline literals in `client.py` | Less code | Magic numbers; the exact anti-pattern lessons-learned flags; hard to tune |

**Decision:** **A.** All tunables in `summarizer/config.py` as a frozen dataclass.
`litellm.completion(..., timeout=config.request_timeout_seconds)` (30.0s) bounds a hung call;
a LiteLLM `Timeout` then flows through ADR-002's `APIError` boundary → skip. `input_char_cap=
8000` enforces AC-4-019.

**Consequences:** "Config-driven tunables" lesson satisfied. 30s is a V1 default (tunable, not
config-file-exposed in V1 — consistent with the 8000-cap being hardcoded-default per Q3). The
timeout is the concrete RF-2 mitigation (watch item closed).

### ADR-008 — Prompt construction: system+user messages, title+body only, no secrets in logs

**Context:** AC-4-001/002/022 + RF-1/RF-4. Build a prompt that yields ≤2 sentences from ONLY
title+body, send to the single configured provider, never log the key/prompt secrets.

| Option | Pros | Cons |
|---|---|---|
| A. `messages=[{system: "Summarize in at most 2 sentences, plain text, no markdown."},{user: f"Title: {title}\n\nBody: {body}"}]`; model from config; key passed to `litellm.completion(api_key=...)` | Clear instruction supports the soft ≤2 contract (ADR-006); only title+body egress (RF-1); key never logged | Provider-prompt tuning is provider-specific (acceptable for V1) |
| B. Single concatenated user string | Simpler | Weaker steering of length/format |

**Decision:** **A.** `normalize.prepare_input(item)` returns the truncated `(title, body)`;
`client._build_messages()` composes the 2-message list. `litellm.completion(model=…,
messages=…, api_key=config.api_key, timeout=…)`. Logs NEVER include `api_key` or message
content — only `repo/item_type/item_id` + error class (AC-4-012, RF-4).

**Consequences:** Only title+body leave the machine (RF-1 mitigation, QA-testable: assert the
`completion` mock received only title+body, no other fields). Empty body → user message is
`Title: {title}\n\nBody: ` (title-only summary, AC-4-017). Key is read from `Config.llm_api_key`
at construction (AC-4-022).

## API Design

**N/A — no HTTP API** (CLI tool; confirmed). The "contract" is the internal stage interface:

| Entry point | Signature | Purpose | ACs |
|---|---|---|---|
| `LiteLLMSummarizer.summarize` | `(item: RawItem) -> str` | Single-item cache-aside + LLM + normalize (Protocol method); exactly one LiteLLM call via configured provider on miss (AC-4-002) | AC-4-001, AC-4-002, AC-4-003, AC-4-004, AC-4-005, AC-4-006, AC-4-007, AC-4-008, AC-4-013, AC-4-014, AC-4-015, AC-4-016, AC-4-017, AC-4-019 |
| `LiteLLMSummarizer.summarize_items` | `(items: list[RawItem]) -> list[SummarizedItem]` | Batch skip-log-continue; emits survivors | AC-4-009..011, 018, 020, 021 |
| `RedisSummaryCache.get` | `(key: str) -> str \| None` | `SummaryCache` get | AC-4-004, 013 |
| `RedisSummaryCache.set` | `(key: str, value: str) -> None` | `SummaryCache` set | AC-4-005, 014 |
| `content_hash` | `(title: str, body: str) -> str` | SHA-256 hex key segment | AC-4-007, 008, 019 |
| `cache_key` | `(item: RawItem, content_hash: str) -> str` | `summary:{repo}:{type}:{id}:{hash}` | AC-4-006 |
| `prepare_input` | `(item: RawItem) -> tuple[str, str]` | trim + truncate(8000) title/body | AC-4-017, 019 |
| `normalize_summary` | `(text: str) -> str` | ≤2 sentences, plain text; raise on empty | AC-4-015, 016 |

## DB Schema

**N/A — no database** (V1 uses JSON state file + Redis cache; this change touches neither a
DB nor the state file). The only persisted structure is the Redis cache entry:

- **Key:** `summary:{repo}:{item_type}:{item_id}:{content_hash}` (string).
- **Value:** the normalized 1–2 sentence summary (UTF-8 string).
- **No TTL** (A-A6 / SPEC-LOCK Q4 — content-hash is the sole invalidation mechanism).

## Error Mapping

| Trigger | Caught as | Handling | Outcome | AC |
|---|---|---|---|---|
| LLM timeout (hung call > 30s) | `litellm.exceptions.Timeout` (⊂ `APIError`) | catch in `summarize_items` loop, `logger.warning(identity, err_class)` | skip item, continue | AC-4-009 |
| LLM 4xx / 5xx / 429 | `APIError` subclasses (`BadRequestError`, `InternalServerError`, `RateLimitError`, `AuthenticationError`) | same | skip item, continue | AC-4-010 |
| One item fails, others ok | (per-item except) | A,C succeed; B skipped | survivors returned | AC-4-011 |
| Cache `get` raises (Redis down) | `Exception` in `_cache_get` | log warning, return `None` | treated as miss → call LLM | AC-4-013 |
| Cache `set` raises (Redis down) | `Exception` in `_cache_set` | log warning, return | summary still returned/used | AC-4-014 |
| LLM returns empty/whitespace | normalized → empty → `SummarizationFailed` | caught in batch loop | skip item; NOT cached | EC-012 |
| Fully-empty item (no title+body) | guard before LLM (no exception) | filtered in batch loop | skip, zero LLM calls | AC-4-018 |

**Token/secret safety (AC-4-012, RF-4):** `SummarizerError` messages and all log records
contain only `repo`/`item_type`/`item_id` + the exception class name/message — NEVER
`api_key`, the prompt, or the body. Mirrors `github/errors.py` token-safe construction.

```python
class SummarizerError(Exception):
    """Base for summarizer failures. Messages carry item identity + static reason only."""

class SummarizationFailed(SummarizerError):
    """LLM produced no usable summary (empty output) for one item; triggers skip (EC-012)."""
```

## Sequence Flows

**Flow 1 — `summarize(item)` single-item cache-aside (happy + miss):**
```
prepare_input(item) -> (title, body)  # trim + truncate to 8000  (AC-4-019)
  if title and body both empty -> raise _SkipItem  (AC-4-018; caught by batch)
h   = content_hash(title, body)                     # SHA-256(title\nbody)  (AC-4-007)
key = cache_key(item, h)                             # summary:...:h  (AC-4-006)
cached = _cache_get(key)        # best-effort; Redis error -> None  (AC-4-013)
  if cached is not None: return cached               # HIT, no LLM call  (AC-4-004)
msgs = _build_messages(title, body)                  # title+body only  (RF-1)
raw  = completion(model, msgs, api_key, timeout=30)  # exactly one call  (AC-4-005)
summary = normalize_summary(raw)                     # <=2 sentences; raise if empty (AC-4-015/16, EC-012)
_cache_set(key, summary)        # best-effort; Redis error -> no-op  (AC-4-014)
return summary
```

**Flow 2 — `summarize_items(items)` batch degradation (AC-4-009/010/011/018/020):**
```
out = []
for item in items:
    try:
        out.append(SummarizedItem(raw=item, summary=self.summarize(item)))
    except _SkipItem:                 # fully-empty (AC-4-018)
        continue                       # no log noise needed / debug-level
    except SummarizationFailed as e:   # empty LLM output (EC-012)
        logger.warning("skip %s: %s", _identity(item), e); continue
    except litellm.exceptions.APIError as e:   # timeout/4xx/5xx/429 (AC-4-009/010)
        logger.warning("skip %s: %s", _identity(item), type(e).__name__); continue
return out                             # survivors only (AC-4-011)
```

**Flow 3 — idempotent re-run (AC-4-020):** second run over unchanged items → every
`_cache_get` is a HIT → `completion` invoked **zero** times. (QA asserts the mock's call count == 0.)

## Edge Cases

Covered (mapped to spec EC list):
- EC-001 empty body → `prepare_input` yields `("title","")`; user msg `Body: ` → title-only summary (AC-4-017).
- EC-002 fully empty → `_SkipItem` before any LLM call (AC-4-018).
- EC-003 huge body (200k) → truncate to 8000 before call + hash (AC-4-019).
- EC-004 non-ASCII/emoji/CJK → UTF-8 encode in `content_hash`; slicing on `str` is codepoint-safe.
- EC-005 markdown/code-fence body → sent as text; output normalized to one clean line (AC-4-016).
- EC-006 missing/None field (dirty) → `getattr(item, f) or ""` guard (conventions.md; mirrors `_map_item`).
- EC-007/008 first-seen miss → call+set; same item → hit (AC-4-005/004).
- EC-009 edited body → different `content_hash` → miss → re-summarize (AC-4-008).
- EC-010/011 concurrent writers → last-write-wins, harmless (documented out-of-scope; single-operator).
- EC-012 empty LLM output → `SummarizationFailed` → skip, not cached.
- EC-013 >2 sentences → normalized to ≤2 (AC-4-015).
- EC-014 corrupt cached value → returned as-is (best-effort; documented V1 limit).
- EC-015..019 LLM timeout / 4xx / 5xx-429 / Redis-get-down / Redis-set-down → see Error Mapping.
- EC-020 re-run → zero LLM calls. EC-021 oversized body → bounded by 8000 cap.

## Performance

- **LLM call** is the dominant latency; bounded by a 30s timeout (ADR-007). Cache-aside makes
  re-runs O(1) Redis lookups with zero LLM cost (AC-4-020) — the primary cost lever (RF-3).
- **Truncation to 8000 chars** caps token spend per call (RF-3).
- **No concurrency in V1** (single-operator, sequential batch). Parallelism is a V2 concern;
  not designed in to avoid over-engineering.
- `content_hash`/`normalize` are pure CPU, negligible vs network.

## Security

(STRIDE: `security.stride_analysis=auto`; this feature is the project's defining data-egress
surface — analyst captured RF-1..5. No new auth/privilege boundary, so a full new STRIDE
report adds nothing beyond the analyst's flags; addressed here per flag.)

- **RF-1 / data egress (HIGH, ACK'd at SPEC LOCK):** ONLY `title`+`body` of operator-watched
  public-repo issues are sent, to the single `Config.llm_provider` only (ADR-008). No other
  network call from `summarizer/`/`cache/` (AC-4-021, QA-testable). README discloses what is
  sent (PROJECT_SPEC §8) — flagged as a release task.
- **RF-2 / availability (MED):** 30s LiteLLM timeout (ADR-007) + graceful skip (ADR-002) +
  best-effort cache (ADR-004) → a hung LLM or downed Redis never stalls/crashes the run.
- **RF-3 / cost (MED):** 8000-char truncation + cache-aside (ADR-003/007).
- **RF-4 / logging (LOW→MED):** token-safe errors + identity-only logs; never `api_key`/prompt
  (ADR-008, AC-4-012). `SummarizerConfig` `repr` must not expose the key → key is NOT a config
  field; it is passed straight to `completion(api_key=...)` and held only as a private attr.
- **RF-5 / tampering (LOW):** corrupt cache entry served as-is (EC-014) — accepted V1 limit;
  content-hash keying limits cross-item contamination.
- **AC-4-022:** key sourced from `Config.llm_api_key`; no secret literal in source (grep-clean).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| litellm moves an error type outside `APIError` (ADR-002) | Low | Med (skip stops working) | QA test raises real `litellm.exceptions.*` instances, not custom stubs; pinned `litellm>=1.40` (1.89.3) |
| Abbreviation over-split in `normalize_summary` (ADR-006) | Med | Low (cosmetic ≤2 boundary) | masked-abbrev list; soft contract; documented heuristic |
| Broad `except Exception` in cache wrapper masks a bug (ADR-004) | Low | Low | scoped to the two cache I/O calls ONLY; LLM/logic errors use precise excepts |
| `api_key` accidentally logged | Low | High | key never a config field / never in messages-log; AC-4-012 test asserts absence |
| Empty-output cached as a valid summary | Low | Med | EC-012 raises before `_cache_set`; never caches empty |

## Implementation Guide

**Recommended order (foundational → adapter → batch; dependency-correct):**
1. `summarizer/errors.py` — `SummarizerError`, `SummarizationFailed` (no deps). Pattern: copy
   the token-safe docstring style of `github/errors.py`.
2. `summarizer/config.py` — frozen `SummarizerConfig`. Pattern: mirror `github/config.py`
   (`CollectorConfig`) — frozen dataclass, locked defaults, NO secret fields.
3. `summarizer/keys.py` — pure `content_hash()` + `cache_key()`. Use `hashlib.sha256`,
   `("title" + "\n" + "body").encode("utf-8")`.
4. `summarizer/normalize.py` — pure `prepare_input()` (trim+truncate 8000) + `normalize_summary()`
   (regex `(?<=[.!?])\s+`, abbrev mask, ≤2, raise on empty). Use stdlib `re` only.
5. `cache/redis_cache.py` — `RedisSummaryCache(redis.Redis)` thin `get/set` (may raise).
   Inject the `redis.Redis` client (testable). `get` returns `str | None` (decode bytes).
6. `summarizer/client.py` — `LiteLLMSummarizer`: `__init__(*, provider, api_key, cache, config,
   completion=litellm.completion)`; `_cache_get/_cache_set` (best-effort), `_build_messages`,
   `summarize` (Flow 1), `summarize_items` (Flow 2). This is the only module importing `litellm`.
7. `summarizer/__init__.py` + `cache/__init__.py` — re-export public classes.
8. Tests (after each module): mock `completion` (a callable) + a fake/raising cache; NEVER hit
   real LiteLLM/Redis (stack.md, A-C8).

**Patterns to follow (with file paths):**
- Injected client + frozen config: `src/osspulse/github/client.py` (`__init__(..., client=None)`)
  and `src/osspulse/github/config.py`.
- Token-safe error messages: `src/osspulse/github/errors.py`.
- Dirty-data guard (`x or ""`): `src/osspulse/github/client.py:_map_item`.
- Adapter-only helpers off the Protocol: `src/osspulse/state/json_store.py` (`is_seen/mark_seen`).
- `logging.getLogger(__name__)` at module top (all existing adapters).

**Gotchas:**
- Truncate BEFORE hashing AND before the call — the hashed text must equal the sent text
  (AC-4-019), or the cache key drifts between runs.
- `summarize()` must call `completion` **exactly once** on miss (AC-4-005) and **zero** times on
  hit (AC-4-004) — tests assert call counts; don't add a retry (A-A7).
- The cache best-effort wrapper is the ONLY place a broad `except Exception` is allowed; the LLM
  boundary must stay `except litellm.exceptions.APIError` so real bugs surface (ADR-002 vs 004).
- `normalize_summary` must raise (not return "") on empty output so the empty value is never
  cached (EC-012).
- Do NOT import `osspulse.github` or `osspulse.state` anywhere under `summarizer/`/`cache/`
  (AC-4-021) — QA will grep for this.
- `litellm` has no `__version__`; import exceptions from `litellm.exceptions`.
