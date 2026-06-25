# Proposal: Summarizer (S4 — LLM) — ticket 4

## Why
The pipeline (Config → Collector → State Store → **Summarizer** → Render → Deliver)
needs to turn raw GitHub issue text into a short, readable summary so a user
understands a repo's recent issues in **< 2 minutes** without opening each thread
(PROJECT_SPEC §1, §3 "[P0] mỗi issue có một tóm tắt ngắn (1–2 câu)"). This change
builds the **S4 Summarizer** behind the existing `osspulse.ports.LLMClient` Protocol:
take a `RawItem` (issue) and return a **1–2 sentence** summary via **LiteLLM**.

Two cross-cutting V1 constraints make this more than a thin LLM wrapper:
1. **Cost/idempotency** — re-running `osspulse run` must not re-call the LLM for an
   item already summarized. A **cache-aside** layer over **Redis** (`SummaryCache`
   port) returns a cached summary on hit and stores on miss.
2. **Resilience** — the LLM is a remote, rate-limited, fallible dependency. A timeout
   or error for one item must **degrade gracefully** (skip that item, log, continue)
   and NEVER abort the whole digest run (conventions.md → "LLM timeout/error =
   degrade gracefully").

## What Changes
- **NEW** capability `summarizer`: a LiteLLM-backed implementation of the existing
  `LLMClient` Protocol (`summarize(item: RawItem) -> str`), producing a 1–2 sentence
  plain-text summary from `RawItem.title` + `RawItem.body`.
- **NEW** cache-aside orchestration around the LLM call using the existing
  `SummaryCache` Protocol (`get(key) -> str | None`, `set(key, value)`): check cache
  → on miss call the LLM → store the result. Cache is **best-effort**: a cache
  get/set failure (Redis down) is caught and the run continues (re-summarize on miss).
- **NEW** cache-key derivation: `summary:{repo}:{item_type}:{item_id}:{content_hash}`
  per conventions.md, where `content_hash` is a stable hash of the summarized input
  (title+body) so an edited issue gets a fresh summary rather than a stale cached one.
- **NEW** graceful-degradation policy: a per-item LLM timeout/error is caught, logged
  (structured, no secrets), and yields a **skip** (no `SummarizedItem` emitted for
  that item, or a clearly-marked fallback) without raising into the pipeline.
- **NEW** prompt/length contract: the summary is constrained to 1–2 sentences;
  output is sanitized to plain text (no leaked prompt, no raw multi-paragraph dump).
- Produces the existing `SummarizedItem(raw, summary)` domain model (models.py).

## Capabilities
- **New Capabilities**: `summarizer` → `openspec/changes/summarizer-llm-4/specs/summarizer/spec.md`
- **Modified Capabilities**: none. The `LLMClient` and `SummaryCache` Protocols in
  `ports.py` are reused unchanged. `github-collector` (S2) and `state-store` (S3) are
  NOT touched — S4 receives `RawItem` only through pipeline data (hard S2≠S4 boundary).

## Impact
- **Code**: new `src/osspulse/summarizer/` adapter (LiteLLM client + cache-aside
  logic) and `src/osspulse/cache/` Redis `SummaryCache` adapter. `models.py`/`ports.py`
  unchanged in V1; `Config` already carries `llm_provider`/`llm_api_key`.
- **Consumers**: `RawItem` (frozen) is the input; `SummarizedItem` (frozen) is the
  output consumed downstream by S5 Renderer (separate change).
- **External**: LiteLLM (LLM provider chosen by operator) + Redis (summary cache).
  Both are mocked/faked in tests — NO real network calls in tests (stack.md).
- **Security/Privacy**: issue text (title+body) is sent to the operator-configured
  LLM provider — this is the project's only data-egress surface (see Early Risk Flags).
- **No** DB, no queue/broker, no HTTP API, no discussions/releases (those are V2).

Figma: N/A (CLI tool, no UI).

## Assumptions

### [CONFIRMED]
- A-C1 [CONFIRMED]: Summarizer implements the existing `LLMClient.summarize(item: RawItem) -> str`; V1 does NOT change the Protocol signature — Source: `src/osspulse/ports.py`.
- A-C2 [CONFIRMED]: Summary length target is 1–2 sentences — Source: PROJECT_SPEC §3 [P0], §5, glossary "Summarizer".
- A-C3 [CONFIRMED]: LiteLLM is the LLM client library; provider is operator-configured (`Config.llm_provider`/`llm_api_key`) — Source: stack.md, project.md, models.py.
- A-C4 [CONFIRMED]: Cache-aside over Redis via the existing `SummaryCache` Protocol; cache is best-effort and a failure must degrade gracefully (re-summarize), never crash — Source: architecture.md "cache-aside", "Redis cache is best-effort".
- A-C5 [CONFIRMED]: Cache key = `summary:{repo}:{item_type}:{item_id}:{content_hash}` — Source: conventions.md "Cache keys".
- A-C6 [CONFIRMED]: LLM timeout/error degrades gracefully (skip-item, log, continue) and NEVER aborts the run — Source: conventions.md "LLM timeout/error = degrade gracefully".
- A-C7 [CONFIRMED]: S4 must NOT call S2 (GitHub I/O) or any network other than the LLM provider — Source: architecture.md S2≠S4 boundary, PROJECT_SPEC §6.
- A-C8 [CONFIRMED]: Tests mock LLM + cache; no real API/Redis calls in tests — Source: stack.md integration-test policy.
- A-C9 [CONFIRMED]: Only V1 issues are summarized; discussions/releases are V2 — Source: PROJECT_SPEC §5, §6 (S4 = V1 with issues only).
- A-C10 [CONFIRMED]: Secrets (LLM key) read from env/`.env`, never hardcoded/logged — Source: steering/security.md (R-SEC-001/002), PROJECT_SPEC §8.

### [ASSUMED]
- A-A1 [ASSUMED]: `content_hash` is a stable hash (e.g. SHA-256 hex) of the exact text sent to the LLM (`title` + `body`), so an item whose body changed gets a fresh summary instead of a stale cache hit — design choice; conventions.md names the key but not the hash algorithm. **Confirm: SHA-256 of `title\nbody`?**
- A-A2 [ASSUMED]: On LLM failure the item is **skipped** (no `SummarizedItem` emitted) rather than emitting a `SummarizedItem` with a placeholder summary. PROJECT_SPEC §4 shows an issue line always rendered; "skip" means that issue is absent from the digest. **Confirm: skip entirely vs. include with a "(summary unavailable)" placeholder?**
- A-A3 [ASSUMED]: "1–2 sentences" is enforced as a **soft** contract (prompt instruction + a defensive truncation/normalization), not a hard parser that rejects 3-sentence output — an over-long LLM response is normalized down, not treated as an error — design choice (over-strict rejection would lose summaries unnecessarily). **Confirm acceptable.**
- A-A4 [ASSUMED]: Empty/whitespace-only issue `body` → summarize from `title` alone (still produce a 1–2 sentence summary); a fully empty `title`+`body` → skip-with-no-LLM-call (nothing to summarize) — design choice; PROJECT_SPEC silent on empty issues.
- A-A5 [ASSUMED]: Over-long issue bodies are truncated to a bounded input length before the LLM call to cap token cost; truncation is part of the hashed input so the cache key stays stable — design choice (cost guard); PROJECT_SPEC §8 cares about cost, no explicit limit given. **Confirm a default input cap (e.g. ~8k chars)?**
- A-A6 [ASSUMED]: Cache TTL — summaries are cached **without expiry** in V1 (content-hash key already invalidates on edit), matching idempotency; an explicit TTL is a V2 tuning concern — design choice. **Confirm no TTL in V1.**
- A-A7 [ASSUMED]: The summarizer does NOT implement its own LLM rate-limit backoff/retry loop in V1 beyond LiteLLM's defaults; a rate-limit/error simply triggers graceful skip for that item. GitHub-style proactive rate-limit backoff (conventions.md) is the **Collector's** concern, not S4's — design choice; PROJECT_SPEC §5 lists rate-limit handling under the issue collector. **Confirm: no bespoke LLM retry in V1.**

## Edge Cases
(Full enumerated list with expected behavior lives in `specs/summarizer/spec.md` →
"Edge Cases". Summary: ≥16 cases across input boundary, state transition, concurrency,
data integrity, integration failure, and business-rule/cost categories — covering LLM
timeout, LLM 4xx/5xx, empty/huge body, missing/dirty `RawItem` fields, Redis down on
get vs set, cache hit vs miss, non-ASCII/markdown body, over-long summary, cost guard,
and idempotent re-run.)

## Early Risk Flags
(STRIDE trigger decision + threat-derived flags live at the end of
`specs/summarizer/spec.md` → "Early Risk Flags". STRIDE **triggers** here: the feature
egresses repo issue text to a third-party LLM provider — an information-disclosure /
data-egress surface that the project's privacy principle explicitly governs.)

## Non-Goals
- ❌ NOT summarizing discussions or releases — V2 (PROJECT_SPEC §5/§6; S4 V1 = issues).
- ❌ NOT the meta-summary "tình hình repo tuần qua" — V3 (PROJECT_SPEC §5 V3).
- ❌ NOT the digest rendering (S5) or delivery (S6) — separate changes; S4 only
  produces `SummarizedItem`.
- ❌ NOT changing the `LLMClient` or `SummaryCache` Protocol signatures in V1
  (promoting cache-aside onto the Protocol or adding methods is an S3 architect call).
- ❌ NOT a bespoke LLM rate-limit/retry/backoff engine in V1 (A-A7) — graceful skip
  on error is the V1 policy; tuned retry is a V2 concern.
- ❌ NOT collecting from GitHub — S4 never calls S2/GitHub; it consumes `RawItem`
  from pipeline data only (hard architectural boundary).
- ❌ NOT a message queue/broker, DB server, or web framework (V1 over-engineering ban).
- ❌ NOT sending any data to a third party other than the single operator-configured
  LLM provider (privacy non-negotiable).
