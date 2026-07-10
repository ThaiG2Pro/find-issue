# S3 — Full Design: scheduler-cli-7 (osspulse run — V1 pipeline wiring)

## Sketch — Gap Analysis

### ACs Reviewed
- AC-7-001 … AC-7-022 — all 22 ACs (CONFIRMED) reviewed against real producer signatures.

### BRs / INTs Reviewed
- BR-7-001 … BR-7-012 (12) · INT-7-001 … INT-7-006 (6) · Decision D-1.

### Real signatures verified (producers, not stubs)
- `GitHubCollector(token: str, config: CollectorConfig = CollectorConfig(), *, client=None, sleep=time.sleep)` · `.fetch_items(repo: str, lookback_days: int) -> list[RawItem]` · errors: `CollectorError` base → `InvalidRepoError` / `AuthError` / `RateLimitError` / `NetworkError` (`github/errors.py`).
- `JsonFileStateStore(state_path: str | Path)` · `.mark_seen(items: list[RawItem]) -> None` (atomic, write-once `first_seen_at`, empty list = no-op) · raises `StateError`.
- `LiteLLMSummarizer(*, provider: str, api_key: str | None, cache: SummaryCache, config: SummarizerConfig, completion=litellm.completion)` · `.summarize_items(items: list[RawItem]) -> list[SummarizedItem]` (batch, skip-log-continue).
- `RedisSummaryCache(client: redis.Redis)` — `get`/`set` may raise; best-effort swallowing lives in the summarizer.
- `SummarizerConfig(model: str, request_timeout_seconds=30.0, input_char_cap=8000, max_sentences=2, max_summary_chars=600)` — **`model` is REQUIRED (no default)**.
- `render(items: list[SummarizedItem], *, lookback_days: int) -> str` — empty list → non-empty "No new items in the last N days" doc.
- `FileDelivery(output_path: str)` / `StdoutDelivery(stream=None)` · `.deliver(content: str) -> None` · raises `DeliveryError`; stdout does NOT catch `BrokenPipeError`.
- `Config` (frozen): `watched_repos`, `lookback_days`, `github_token`, `llm_provider`, `llm_api_key`, `state_path`, `output_destination`, `output_path`. **No `llm_model`, no `redis_url`.**

### Gaps Found
- **GAP-001 [CRITICAL → resolved in design, ADR-002]**: `Config` carries no LLM `model` string and no Redis connection, but the LLM-enabled path needs `SummarizerConfig(model=...)` (required) + a `SummaryCache`. The proposal Non-Goal forbids Config redesign. Resolved at design level by deriving a default model from `provider` and constructing Redis best-effort — **no Config change**, no S2 return. See ADR-002.
- **GAP-003 [MINOR → pinned, ADR-005]**: AC-7-006 exit code when ALL repos fail. Kept **exit 0** (success-with-warnings — a digest was delivered). Pinned in §Error Mapping. No distinct code added (confirmed at Mini-gate A).
- No contradictory BRs, no undefined data relationships. **No critical gaps require an S2 return — proceeding to full design.**

---

## Context

OSS Pulse has six working units (S1 Config, S2 Collector, S3 State, S4 Summarizer, S5 Renderer,
S6 Delivery) but no orchestration: `osspulse.pipeline.run_pipeline` is `raise NotImplementedError`
and `cli.py run` delivers a hardcoded stub string. S7 closes the V1 loop by implementing
`run_pipeline(config)` as the linear wiring of the five stages and rewriting `cli.run` to call it,
preserving the delivery-6 CLI exit-code contract (ADR-003) and adding collector/summarizer error
boundaries. S7 changes **no port signatures** — it only consumes the frozen exports of changes 2–6.

Constraints: CLI-only (no HTTP API, no DB), no new runtime deps, Redis best-effort, secrets
(`GITHUB_TOKEN` / `llm_api_key`) must never reach logs/errors/digest (RF-1, HIGH).

## Goals / Non-Goals

**Goals:**
- Implement `run_pipeline(config: Config) -> None` wiring Config → Collector → State → Summarizer → Renderer → Delivery, replacing the `NotImplementedError` stub and the hardcoded CLI string (AC-7-001/002/003/016).
- Per-repo failure isolation + auth-fatal + rate-limit-terminal-but-deliver (AC-7-004/005/006/017).
- Batch summarize once; no-LLM placeholder path (AC-7-007/008/018/022).
- Record seen for idempotency, decoupled from summarization (AC-7-010/011/019).
- Preserve CLI error contract; never leak secrets (AC-7-012/013/014/020; RF-1).
- Per-repo + run-summary observability logging (AC-7-015/021).

**Non-Goals (inherited from proposal):**
- No cron/scheduler, no seen-suppression (V1 records only), no discussions/releases, no push delivery, no Config field additions, no port signature changes, no locking, no new CLI subcommands.

## Architecture Overview

### System Components
```
config.toml + env ──► load_config() ──► Config
                                          │
                              cli.run (Typer, error boundary + exit codes)
                                          │ run_pipeline(config)
                                          ▼
   ┌──────────────────────────── osspulse.pipeline.run_pipeline ────────────────────────────┐
   │  construct adapters from Config (token→collector, api_key→summarizer; never on self)    │
   │  for repo in config.watched_repos:                                                      │
   │      collector.fetch_items(repo, lookback_days)  ──► isolate per-repo errors            │
   │      state.mark_seen(items)                       (decoupled from summarize)            │
   │  aggregate all RawItems ──► summarize_items(all) | no-LLM wrap                           │
   │  render(summarized, lookback_days)  ──► one digest string                                │
   │  delivery.deliver(digest)           ──► one call                                         │
   └──────────────────────────────────────────────────────────────────────────────────────┘
        GitHubCollector   JsonFileStateStore   LiteLLMSummarizer+RedisSummaryCache   render()   FileDelivery/StdoutDelivery
```

### Module Structure (files touched)
```
src/osspulse/
  pipeline.py   # MODIFY — implement run_pipeline (orchestration + error taxonomy + logging)
  cli.py        # MODIFY — call run_pipeline; extend except-boundary (Collector/State/Summarizer errors)
```
`pipeline.py` is the **only** module permitted to import multiple stages (AC-7-002). No stage module
(`github`, `state`, `summarizer`, `cache`, `render`, `delivery`) imports another stage.
`run_pipeline` replaces the `raise NotImplementedError` stub and `cli.run` stops delivering the
hardcoded `"osspulse: pipeline not yet implemented"` string (AC-7-003). All repos' items are
aggregated into a single flat `render(...)` call, not one render per repo (AC-7-016).

### Cross-stage dependency note
`pipeline.py` imports: `osspulse.config`/`models` (Config, RawItem, SummarizedItem),
`osspulse.github` (collector + errors), `osspulse.state`, `osspulse.summarizer` (+ `cache`),
`osspulse.render`, `osspulse.delivery`. This is the sanctioned cross-stage importer; AC-7-002 is
asserted by a static import test scoped to the stage modules (pipeline.py excluded).

## ADR (Architecture Decision Records)

### ADR-001: Linear orchestration in a single `run_pipeline` function (no orchestrator class)
#### Context
S7 wires 5 stages one-directionally. Need a structure that keeps the token/key off any retained
object (BR-7-006, RF-1) and matches the established functional style (`render()` is a free function).
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Single `run_pipeline(config)` free function; adapters are locals | Tokens stay in local scope, never on `self`; simplest; matches `render()` style | One longer function (mitigated by private `_helpers`) |
| (b) `Pipeline` class holding adapters as attributes | OO grouping | Token/key would live on `self` → RF-1 risk; over-engineered for a linear flow |
#### Decision
**(a)** — free function with private module-level helpers (`_collect_all`, `_summarize`, `_log_run_summary`).
Adapters are locals; the token is passed only to `GitHubCollector(...)` and the key only to
`LiteLLMSummarizer(...)`, never stored on a shared object (BR-7-006).
#### Consequences
- Positive: no secret-bearing object outlives the call; testable by injecting a fake Config + monkeypatched adapter constructors.
- Negative: the function coordinates several concerns — split into named helpers for readability.
#### Status: Accepted

### ADR-002: Derive LLM model + Redis cache inside the pipeline — NO Config change (resolves GAP-001)
#### Context
`LiteLLMSummarizer` needs `SummarizerConfig(model=...)` (required) and a `SummaryCache` (Redis
client). `Config` carries `llm_provider`/`llm_api_key` only; the proposal Non-Goal forbids adding
Config fields. Deviation from "Config already carries every field S7 needs" must be justified.
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Pipeline derives model via a `_PROVIDER_MODEL` default map (`openai`→`openai/gpt-4o-mini`, `ollama`→`ollama/llama3`, else `<provider>/<provider>`); build Redis best-effort from `REDIS_URL` env (default `redis://localhost:6379`), wrap in try/except → on failure use a no-op in-memory cache | No Config change (honors Non-Goal); zero-config default works; AC-7-009 degradation satisfied by best-effort construction | A hidden default model not surfaced in config (documented in README + ADR) |
| (b) Add `llm_model` + `redis_url` to `Config` | Explicit, user-tunable | Violates the no-Config-redesign Non-Goal → requires S2 return (cost 3×) |
| (c) Hardcode one model constant + always best-effort Redis | Simplest | No per-provider correctness (ollama ≠ openai model string) |
#### Decision
**(a)**. Pipeline owns a private `_PROVIDER_MODEL: dict[str,str]` with a deterministic fallback
`f"{provider}/{provider}"`, and a `_build_cache()` that constructs `RedisSummaryCache(redis.Redis.from_url(url))`
inside try/except; any connection/import error → a `_NullCache` (get→None, set→no-op) so AC-7-009
degrades to re-summarize without crashing. `REDIS_URL` read from `os.environ` (not Config).
**Deviation justified**: Non-Goal "no Config redesign" (proposal) — chosen over option (b) to avoid
an S2 return; spec evidence = AC-7-009 already presumes best-effort cache. README documents the
default model + `REDIS_URL` override.
#### Consequences
- Positive: V1 works with zero extra config; AC-7-007/009 satisfiable; Non-Goal respected.
- Negative: model choice is convention-driven; surfaced in README and revisited in V2 (config fields).
#### Status: Accepted

### ADR-003: Exception → action taxonomy (the riskiest area — AC-7-004/005/017)
#### Context
Per-repo `fetch_items` can raise four collector errors with different required behaviors; auth is
fatal (shared token), rate-limit is terminal-but-deliver, 404/network are per-repo skip. A wrong
mapping is the single most error-prone area for S4 (analyst risk flag).
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Explicit per-class catch order: `AuthError` (re-raise fatal) → `RateLimitError` (break collection, deliver) → `InvalidRepoError`/`NetworkError`/other `CollectorError` (skip+continue) | Precise; matches spec exactly; each branch testable | More branches |
| (b) Single `except CollectorError` with isinstance dispatch | Compact | Easy to mis-order; `AuthError`/`RateLimitError` are subclasses of `CollectorError` so order is fragile |
#### Decision
**(a)** — catch the **most-specific subclasses first**. Because `AuthError`, `RateLimitError`,
`InvalidRepoError`, `NetworkError` all subclass `CollectorError`, the per-repo try block orders:
`except AuthError` → re-raise (fatal); `except RateLimitError` → log WARN + stop the repo loop +
proceed to render/deliver what was collected; `except (InvalidRepoError, NetworkError, CollectorError)`
→ log WARN + skip that repo + continue. A bare unknown `CollectorError` falls into the skip bucket
(never crash). The exception→action table below is normative.
#### Consequences
- Positive: deterministic mapping; auth never wasted across repos; rate-limit still delivers partial.
- Negative: `RateLimitError` uses loop-break control flow — documented in §Sequence Flows.
#### Status: Accepted

### ADR-004: No-secret-logging discipline reused from upstream (RF-1, AC-7-014, BR-7-012)
#### Context
Token + api_key flow through adapter construction. A leak into a log line, error message, or the
digest exposes the operator's credentials (RF-1 HIGH).
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Log only repo names / counts / our own exception-class messages; pass token→collector ctor + key→summarizer ctor only; never log a raw upstream exception | Reuses collector-2 ADR-004 + summarizer-llm-4 ADR-008 proven discipline; testable by log-capture | Requires discipline on every `logger.*` call |
| (b) Trust upstream adapters not to leak; no pipeline-level assertion | Less code | RF-1 is HIGH — no guarantee a tokened URL isn't in a re-raised exception str |
#### Decision
**(a)**. The pipeline logs `repo.full_name`, integer counts, and `str(our_error)` only. It NEVER
logs a raw upstream exception object (collector errors are already token-safe by construction —
`github/errors.py` composes messages from status+repo+static reason only). A log-capture test
(AC-7-014) asserts neither secret substring appears in stderr/logs/digest.
#### Consequences
- Positive: RF-1 mitigated + tested; consistent with the whole codebase.
- Negative: error messages are slightly less detailed (acceptable — operator sees error class + repo).
#### Status: Accepted

### ADR-005: All-repos-fail and rate-limit both exit 0 if a digest is delivered (AC-7-006/017; resolves GAP-003)
#### Context
When every repo is skipped (all 404/network) or a terminal rate-limit stops collection, zero or
partial items remain. Need to decide the exit code. Operator-signal concern was raised at S2.
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Exit 0 (success-with-warnings) whenever a digest (incl. the no-new-items doc) was delivered | Matches analyst decision + spec; `render([])` is a valid delivered artifact; exit 1 reserved for fatal config/auth/delivery | An operator wanting a non-zero "nothing collected" signal disagrees |
| (b) Distinct exit code 2 = delivered-but-empty | Operator can script on it | Spec/decisions pin exit 0; would change the CLI contract + cascade to AC wording → S2 |
#### Decision
**(a)** — exit 0 if delivery succeeded. Exit 1 is reserved exclusively for `ConfigError`,
`AuthError`, and `DeliveryError`. Confirmed at Mini-gate A; no distinct code added.
#### Consequences
- Positive: consistent with `_decisions.jsonl` AC-7-006/017; no contract churn.
- Negative: "all repos failed" is visible only via WARN logs + the no-new-items digest, not the exit code (RF-4 logging mitigates).
#### Status: Accepted

### ADR-006: No-LLM path constructs `SummarizedItem` wrappers with a fixed placeholder (D-1, AC-7-008/022)
#### Context
When `config.llm_provider is None`, the summarizer must not be constructed/called, yet `render()`
requires `list[SummarizedItem]`. The placeholder must be visible (renderer omits empty summaries).
#### Options
| Option | Pros | Cons |
|--------|------|------|
| (a) Wrap each `RawItem` as `SummarizedItem(raw=item, summary="(no summary — LLM disabled)")` | Renderer emits non-empty summary verbatim → visibly marks skip (AC-7-022); zero LLM cost | none material |
| (b) Empty-string summary | — | Renderer omits empty/whitespace summaries (AC-5-017) → ambiguous; rejected by D-1 update |
#### Decision
**(a)** — fixed module constant `NO_LLM_PLACEHOLDER = "(no summary — LLM disabled)"`. The
summarizer is neither imported-for-construction nor called on this path (BR-7-010).
#### Consequences
- Positive: matches the stakeholder-updated D-1; tested by AC-7-022 (placeholder visible in output).
- Negative: placeholder text is user-facing copy — kept as a single named constant.
#### Status: Accepted

## API Design

**N/A — CLI-only tool, no inbound HTTP API.** No `openapi.yaml` is produced, citing
github-collector-2 ADR-007, state-store-3 ADR-004, and digest-renderer-5 ADR-005 (the established
"no openapi.yaml when a change has no inbound HTTP API" precedent). The only interface is the Typer
command `osspulse run --config <path>` (unchanged signature; behavior changes from stub → real).

### Internal contract (stage data flow, one-directional)
| Stage | Entry signature consumed | Produces |
|-------|--------------------------|----------|
| Collector | `fetch_items(repo: str, lookback_days: int) -> list[RawItem]` | `list[RawItem]` per repo |
| State | `mark_seen(items: list[RawItem]) -> None` | (side effect: atomic state write) |
| Summarizer | `summarize_items(items: list[RawItem]) -> list[SummarizedItem]` | survivors |
| Renderer | `render(items: list[SummarizedItem], *, lookback_days: int) -> str` | one digest string |
| Delivery | `deliver(content: str) -> None` | (side effect: file/stdout) |

## DB Schema

**N/A — no database.** V1 state is a JSON file owned by `JsonFileStateStore` (state-store-3,
doc shape `{version:1, seen:{repo:{"type:id":first_seen_at}}}`). S7 only calls `mark_seen`; it does
not read or alter the schema. No migration.

## Error Mapping (Exception → Action table — NORMATIVE)

| Exception (source) | Scope | Action | Exit | Log level | AC / BR |
|--------------------|-------|--------|------|-----------|---------|
| `ConfigError` (config.py, pre-pipeline) | run | `Error: <msg>` stderr, no traceback | 1 | — | AC-7-012, BR-7-004 |
| `AuthError` (collector) | run (shared token) | stop immediately, `Error: <msg>` (no token), no traceback | 1 | WARN once | AC-7-005, BR-7-002 |
| `RateLimitError` (collector, terminal) | collection | stop repo loop, render+deliver what was collected | 0 | WARN | AC-7-017, BR-7-008 |
| `InvalidRepoError` (collector) | per-repo | log + skip repo, continue | 0 (if delivered) | WARN | AC-7-004, BR-7-001 |
| `NetworkError` (collector) | per-repo | log + skip repo, continue | 0 (if delivered) | WARN | AC-7-004, BR-7-001 |
| other `CollectorError` | per-repo | log + skip repo, continue (never crash) | 0 (if delivered) | WARN | AC-7-004, BR-7-001 |
| `StateError` (state save) | run | `Error: <msg>`, no traceback | 1 | — | AC-7-012 (contract), BR-7-004 |
| per-item LLM failure (inside `summarize_items`) | per-item | summarizer skips+logs internally; pipeline renders survivors | 0 | (summarizer) | AC-7-007/018, BR-7-009 |
| Redis unreachable | cache | best-effort → miss/no-op (`_NullCache` or summarizer swallow) | 0 | WARN | AC-7-009 |
| `DeliveryError` (delivery) | run | `Error: <msg>`, no traceback | 1 | — | AC-7-020, BR-7-004 |
| `BrokenPipeError` (stdout consumer closed) | run | redirect stdout→devnull, clean exit | 0 | — | AC-7-013, INT-7-001 |
| all repos skipped (zero items) | run | `render([])` no-new-items doc, deliver | 0 | WARN summary | AC-7-006 |

Rule: **secrets never appear** in any message/log/digest (BR-7-012, AC-7-014). The pipeline logs only
repo names, counts, and our own exception-class messages — never a raw upstream exception.

## Sequence Flows

### Flow 1 — Happy path (LLM configured, ≥1 repo with new issues) [AC-7-001/007/016]
```
cli.run → load_config → run_pipeline(config)
  build: collector=GitHubCollector(token); state=JsonFileStateStore(state_path)
         summarizer=LiteLLMSummarizer(provider,key,cache=_build_cache(),config=SummarizerConfig(model=_model_for(provider)))
  all_items=[]
  for repo in watched_repos:
      items = collector.fetch_items(repo.full_name, lookback_days)   # may raise → ADR-003
      state.mark_seen(items)                                          # decoupled (AC-7-019)
      log INFO "collected {len(items)} from {repo}"                   # AC-7-015
      all_items += items
  summarized = summarizer.summarize_items(all_items)                  # ONE call (BR-7-009)
  digest = render(summarized, lookback_days=lookback_days)            # ONE call
  delivery.deliver(digest)                                            # ONE call (BR-7-007)
  log INFO run-summary (repos, collected, summarized, skipped)        # AC-7-021
  → exit 0
```

### Flow 2 — No LLM provider [AC-7-008/022, ADR-006]
```
llm_provider is None → DO NOT construct/call summarizer
  summarized = [SummarizedItem(raw=it, summary=NO_LLM_PLACEHOLDER) for it in all_items]
  render → deliver → exit 0   (placeholder visible per item, AC-7-022)
```

### Flow 3 — Per-repo isolation + auth-fatal + rate-limit-terminal [AC-7-004/005/017, ADR-003]
```
for repo in watched_repos:
    try: items = collector.fetch_items(...)
    except AuthError:        log WARN; re-raise → cli prints Error: <msg>, exit 1   (FATAL, AC-7-005)
    except RateLimitError:   log WARN "rate limit"; break loop (stop collecting)    (AC-7-017)
    except (InvalidRepoError, NetworkError, CollectorError):
                             log WARN "skipped: <reason>"; continue                 (AC-7-004)
    else: state.mark_seen(items); all_items += items
# after loop (normal end OR rate-limit break): summarize → render → deliver → exit 0
```

### Flow 4 — All repos fail [AC-7-006]
```
every repo → except (InvalidRepoError|NetworkError) → skip
all_items == [] → summarize_items([])→[] (or skip) → render([]) = "no new items" doc
deliver(doc) → log WARN summary "0 collected" → exit 0
```

## Edge Cases (mapped from proposal EC-001..020)
- EC-001 single repo → one `## {repo}` section (no special-casing).
- EC-002/EC-006-related empty repo → contributes nothing; all-empty → Flow 4.
- EC-003 empty `RawItem` fields → summarizer/renderer degrade per field (no crash).
- EC-004/EC-005 first run / idempotent re-run → `mark_seen` write-once `first_seen_at`; byte-identical digest (AC-7-011).
- EC-006/EC-007 overlapping writes → atomic `os.replace` in state + delivery (last-writer-wins; no lock in V1).
- EC-008 summarizer returns fewer → render survivors only (AC-7-018); skipped count logged.
- EC-009/AC-7-019 mark_seen before summarize fails → seen recorded, decoupled.
- EC-010 missing `GITHUB_TOKEN` → `ConfigError` pre-pipeline, exit 1.
- EC-011 → AuthError fatal (Flow 3). EC-012 → InvalidRepoError skip. EC-013 → RateLimitError terminal-deliver.
- EC-014 LLM per-item error → summarizer skip-log-continue. EC-015 Redis down → `_NullCache`/miss (AC-7-009).
- EC-016/EC-020 missing parent dir → `DeliveryError` exit 1 (delivery does NOT mkdir).
- EC-017 missing config file → `ConfigError` exit 1. EC-018 SIGPIPE on stdout → `BrokenPipeError` clean exit 0.
- EC-019 remote provider needs key → already enforced by `load_config`; S7 does not re-validate.

## Performance
- Single-operator, one-shot CLI; watchlist is small (3–5 repos typical). No concurrency in V1
  (repos processed sequentially in `watched_repos` order — deterministic, A8). Collector already
  bounds pages/items via `CollectorConfig`; summarizer bounds input via `input_char_cap` + timeout.
- One `summarize_items` batch call, one `render`, one `deliver` — no per-repo fan-out of expensive
  ops (BR-7-007/009). Redis cache-aside reduces repeat LLM cost across runs (best-effort).
- RF-2 (cost/DoS): terminal rate-limit stops collection cleanly; `lookback_days>365` already warns
  at config load. No new guard needed for V1.

## Security
Addresses every STRIDE threat from `stride-threat-model.md` (gate PASS):
- **RF-1 (I, HIGH)** → ADR-004: token→collector ctor, key→summarizer ctor only; never on a retained
  object (BR-7-006); log only repo/counts/our-error-class; log-capture test asserts no secret in
  stderr/logs/digest (AC-7-014, BR-7-012).
- **RF-3 (T, MED)** → reuse atomic writes (delivery-6 + state-store-3); S7 adds NO non-atomic write path.
- **RF-4 (R, LOW)** → per-repo outcome log + run-summary line (AC-7-015/021, BR-7-005).
- **RF-2 (D, MED)** → terminal rate-limit handling (AC-7-017); config lookback warn.
- **RF-5 (S) / RF-6 (E)** → N/A / LOW: CLI-only, read-only public-repo token scope; no new surface.
No new STRIDE analysis required — design reuses upstream mitigations; no Critical/High left unmitigated.

## Risk Assessment
- [Error-taxonomy mis-mapping] → ADR-003 normative table + Flow 3 + dedicated tests per branch.
- [Secret leak via raw upstream exception] → ADR-004: never log raw exception objects; log-capture test.
- [GAP-001 hidden model default surprises user] → README documents default model + `REDIS_URL`; revisit as Config fields in V2.
- [Import-isolation regression] → AC-7-002 static import test (stage modules only; pipeline.py is the sanctioned importer).
- [Rate-limit break control flow] → documented in Flow 3; test asserts partial digest delivered + exit 0.

## Implementation Guide

### Recommended Order
1. `pipeline.py` — module constants + helpers: `NO_LLM_PLACEHOLDER`, `_PROVIDER_MODEL` map + `_model_for(provider)`, `_NullCache`, `_build_cache()`, `logger = logging.getLogger("osspulse.pipeline")`.
2. `pipeline.py` — `_collect_all(config, collector, state, logger)` implementing Flow 3 (per-repo isolation, auth re-raise, rate-limit break, mark_seen). Returns `(all_items, stats)`.
3. `pipeline.py` — `_summarize(config, all_items)` implementing LLM vs no-LLM branch (ADR-006), returns `list[SummarizedItem]`.
4. `pipeline.py` — `run_pipeline(config)` wiring: build adapters → `_collect_all` → `_summarize` → `render` → `delivery.deliver` → run-summary log.
5. `cli.py` — call `run_pipeline(cfg)`; extend the `except` boundary to add `AuthError`/`CollectorError(fatal)`/`StateError` → `Error: <msg>` exit 1, keeping existing `BrokenPipeError`/`DeliveryError`/`ConfigError` handlers and ordering.
6. Tests: `tests/test_pipeline.py` (flows 1–4, error taxonomy, no-LLM, log-capture/secret, import-isolation) + `tests/test_cli_run.py` (exit codes, BrokenPipe). All external adapters mocked — never real APIs.

### Patterns to Follow (with file paths)
- Per-module error class + CLI catch: `src/osspulse/delivery/errors.py` + current `cli.py` `except` ladder (extend, don't replace).
- Atomic write reuse (no new write path): `src/osspulse/state/json_store.py:save`, `src/osspulse/delivery/file_delivery.py:deliver`.
- No-secret-logging: `src/osspulse/github/errors.py` (token-safe messages), `src/osspulse/summarizer/client.py` (`__api_key` private; logs identity/class only).
- Batch summarize: `src/osspulse/summarizer/client.py:summarize_items` (call ONCE).
- Renderer empty-input doc: `src/osspulse/render/renderer.py:render` (returns non-empty no-new-items doc).
- Adapter construction (DI ctor injection): `GitHubCollector.__init__`, `LiteLLMSummarizer.__init__`, `RedisSummaryCache.__init__`.

### Gotchas
- `SummarizerConfig.model` has **no default** — `_model_for(provider)` MUST supply it (GAP-001/ADR-002).
- Catch collector exceptions **most-specific-first** — `AuthError`/`RateLimitError` are subclasses of `CollectorError`; wrong order silently mis-routes (ADR-003).
- `mark_seen([])` is a safe no-op — call it even for empty repo results; don't guard with `if items`.
- The no-LLM path must NOT construct `LiteLLMSummarizer` at all (BR-7-010) — branch before building it.
- Never `logger.exception(...)` / log a raw upstream exception object — log `type(exc).__name__` or our own message (RF-1).
- `RateLimitError` uses `break` then proceeds to render — do not `return`/`raise`; partial digest must still deliver (AC-7-017).
- `cli.py` `except` order: keep `BrokenPipeError` first; add new fatal collector/state errors before the generic handlers; preserve exit codes.
- `pipeline.py` is the only allowed cross-stage importer — do not add stage-to-stage imports (AC-7-002).
