## Why

OSS Pulse has five working pipeline stages (S2 Collector, S3 State Store, S4 Summarizer,
S5 Renderer, S6 Delivery) and S1 Config, but **nothing wires them together**: `cli.py run`
loads config and emits a hardcoded stub string (`"osspulse: pipeline not yet implemented"`),
and `pipeline.py:run_pipeline` is a bare `raise NotImplementedError`. S7 closes the V1 loop —
the single `osspulse run` entry point that orchestrates Config → Collect → (record seen) →
Summarize → Render → Deliver end-to-end, satisfying the "V1 done" criterion in PROJECT_SPEC §5:
*run `osspulse run` on 3–5 real repos → readable Markdown file, no rate-limit crash*.

## What Changes

- Implement `osspulse.pipeline.run_pipeline(config: Config) -> None` (today a `NotImplementedError`)
  as the linear orchestration of the five existing stages, constructing each adapter from `Config`
  and passing data one direction (no stage imports another stage).
- Rewrite `osspulse.cli.py run` to call the real pipeline instead of the stub `deliver(...)` string,
  preserving the existing `BrokenPipeError` / `DeliveryError` / `ConfigError` exit-code contract
  (ADR-003 from delivery-6) and adding the collector/summarizer error boundaries.
- Iterate the watchlist (`config.watched_repos`): collect issues per repo, **record seen items**
  in the State Store (S3 write side, for V1 — full delta is V2), summarize survivors, aggregate
  across all repos, render ONE digest, deliver once.
- Per-repo and per-item **graceful degradation**: a single repo/issue failure (network, 4xx,
  LLM error) must NOT abort the whole run — log + skip + continue, per `conventions.md` error model.
- Wire the LLM summarizer only when an LLM provider is configured; when no provider is set,
  deliver the raw (unsummarized) digest rather than crash — keeps "Tuần 1 digest without LLM"
  (PROJECT_SPEC §9) reachable and the run useful with zero LLM cost.
- **NOT BREAKING**: no public port signature changes. S7 only *consumes* the frozen
  interfaces exported by changes 2–6.

## Capabilities

### New Capabilities
- `scheduler-cli`: The `osspulse run` CLI command and the `run_pipeline` orchestrator that wires
  Config → GitHubCollector → JsonFileStateStore → LiteLLMSummarizer → render() → Delivery into a
  single idempotent end-to-end V1 run, with per-repo/per-item error isolation and the CLI exit-code
  contract. (Cron/scheduler is V2 and explicitly out of scope here.)

### Modified Capabilities
<!-- None. S7 consumes the frozen ports/exports of changes 2–6 without changing any spec-level
     requirement of those capabilities. pipeline.py and cli.py are wiring code newly specified by
     this capability, not a requirement change to an existing capability. -->
(none)

## Impact

- **Code (modified)**: `src/osspulse/pipeline.py` (implement `run_pipeline`),
  `src/osspulse/cli.py` (call real pipeline, keep exit-code contract).
- **Code (consumed, unchanged)**: `github/` (`GitHubCollector.fetch_items`), `state/`
  (`JsonFileStateStore.load/save/is_seen/mark_seen`), `summarizer/`
  (`LiteLLMSummarizer.summarize_items`), `cache/` (`RedisSummaryCache`), `render/` (`render()`),
  `delivery/` (`FileDelivery`/`StdoutDelivery`).
- **Config (consumed, unchanged)**: `Config` already carries every field S7 needs
  (`watched_repos`, `lookback_days`, `github_token`, `llm_provider`, `llm_api_key`, `state_path`,
  `output_destination`, `output_path`). S7 does NOT redesign Config (watch-item from baton).
- **Dependencies**: no new runtime deps. Redis is optional (cache best-effort; missing Redis must
  degrade, not crash).
- **Tests**: new `tests/test_pipeline.py` + `tests/test_cli_run.py` with ALL external adapters
  (GitHub/LLM/cache) mocked — never call real APIs (architecture.md anti-pattern).
- **Docs**: README "Usage" section — `osspulse run` example + the no-LLM-provider behavior.

Figma: N/A (CLI tool, no UI — consistent with collector-2 ADR-007, renderer-5 ADR-005).

## Non-Goals (Out of Scope)

Explicitly NOT in this change (deferred or forbidden per PROJECT_SPEC §5):
- **Cron / scheduler** — `osspulse run` is a one-shot CLI; periodic scheduling is V2 (PROJECT_SPEC §3 [P1], §6 S7 V2). No daemon, no background process.
- **Real delta / seen-item suppression** — V1 records seen state (`mark_seen`) but does NOT filter already-seen items out of the digest. Suppression is V2 (A4, PROJECT_SPEC §6 S3).
- **Discussions / Releases sources** — V1 collects issues only (collector-2 scope). Discussions (GraphQL) + releases are V2.
- **Push delivery (email/webhook)** — V1 delivers to file/stdout only (delivery-6). Email/Discord/Slack is V2.
- **Config redesign** — `Config` already carries every field S7 needs; this change does not add or change config fields (baton watch-item).
- **Port signature changes** — S7 consumes the frozen ports of changes 2–6 unchanged; no MODIFIED capability.
- **Concurrency control / locking** — no file lock for overlapping runs; atomic writes (last-writer-wins) are accepted for a single-operator tool.
- **New CLI subcommands** (`add`/`list`/`remove` watchlist management) — only `run` is in scope here.
- **Meta-summary / insights (S8)** — V3, not touched.

## Assumptions

- **A1 [CONFIRMED]**: S7 only orchestrates existing stages; it changes no port signatures.
  Source: `ports.py` (all ports frozen), cross-spec-context constraints for changes 2–6.
- **A2 [CONFIRMED]**: One run produces ONE digest aggregating ALL watched repos (not one file
  per repo). Source: renderer-5 `render(items: list[SummarizedItem], *, lookback_days)` takes a
  flat list and emits per-repo `## {repo}` sections internally; delivery-6 `deliver(content: str)`
  is called once. PROJECT_SPEC §4 user flow shows a single digest with multiple `##` repo blocks.
- **A3 [CONFIRMED]**: The summarizer entry point for the pipeline is the batch
  `summarize_items(list[RawItem]) -> list[SummarizedItem]` (graceful skip-log-continue), NOT the
  per-item `summarize()`. Source: summarizer-llm-4 cross-spec constraint "Future pipeline wiring
  calls `summarize_items()` (not `summarize()`)" + `client.py:140`.
- **A4 [CONFIRMED]**: State Store in V1 is **write-only for idempotency recording** — S7 calls
  `mark_seen` for collected items; it does NOT yet filter out already-seen items (that filtering =
  full delta = V2). Source: PROJECT_SPEC §6 "S3 V1 (ghi), V2 (dùng cho delta)"; state-store-3
  proposal. *This keeps V1 honest: we record seen state now, consume it for delta in V2.*
- **A5 [CONFIRMED]**: When `config.llm_provider is None`, the pipeline delivers an unsummarized
  digest (each item's "summary" = empty/placeholder) rather than erroring. Source: PROJECT_SPEC §9
  milestone "Tuần 1 … digest thô, chưa có LLM". *Decision recorded as D-1 below.*
- **A6 [ASSUMED]**: Per-repo failure isolation boundary = catch `CollectorError` (and subclasses
  AuthError/RateLimitError/NetworkError/InvalidRepoError) around each repo's `fetch_items`; on
  catch, log a warning and continue to the next repo. A whole-run-fatal error (bad config) still
  exits 1. Needs architect confirmation of exact catch granularity at S3.
- **A7 [ASSUMED]**: Redis summary cache is constructed best-effort; if Redis is unreachable at
  construction or call time, the summarizer already degrades (summarizer-llm-4 cache-aside is
  best-effort) — S7 does not add extra Redis handling. Validate the construction path at S3.
- **A8 [ASSUMED]**: Run ordering is deterministic — repos processed in `config.watched_repos`
  order; the renderer already sorts repos alphabetically for output, so processing order does not
  affect digest bytes. Low risk; documented.

## Decisions

- **D-1**: No-LLM-provider path delivers a digest with a visible placeholder summary (A5).
  Considered (a) hard-error when no provider, (b) skip summarization and render with an **empty**
  summary, (c) skip summarization and render with the fixed placeholder
  `"(no summary — LLM disabled)"`. Chose (c) — matches PROJECT_SPEC §9 Tuần-1 milestone, makes the
  tool useful at zero LLM cost, AND makes it visually unambiguous that summaries were intentionally
  skipped (not silently lost). The renderer omits empty/whitespace summaries (AC-5-017) but emits
  any non-empty summary verbatim, so a non-empty placeholder is the way to surface the no-LLM state
  in the output. Drives AC-7-008, AC-7-022, BR-7-010. (Updated from empty-string after stakeholder
  request 2026-06-30.)

## Edge Cases

### Input boundary
- **EC-001**: Watchlist with exactly 1 repo → digest with a single `## {repo}` section. Expected:
  works; no special-casing of the singleton.
- **EC-002**: A repo returns **zero** new issues in `lookback_days` → that repo contributes no
  items; if ALL repos are empty, `render()` returns the non-empty "no new items" doc
  (renderer-5 No-new-items doc), delivered normally, exit 0.
- **EC-003**: A `RawItem` with empty `title`/`body`/`url` (collector-2: fields may be empty
  strings) flows through summarize+render without crashing. Expected: summarizer skips fully-empty
  items (summarizer-llm-4 AC-4-018), renderer degrades per field (renderer-5 RF-2).

### State transition
- **EC-004**: First-ever run (no state file yet) → State Store creates state on `save`; all items
  are "new". Expected: no error; `mark_seen` writes fresh state atomically.
- **EC-005**: Re-run immediately with no new GitHub activity → same items collected again; V1
  re-marks seen (write-once `first_seen_at` preserved — state-store-3 constraint) and re-delivers
  a byte-identical digest (idempotent, delivery-6 AC-6-018). Expected: no duplicate/garbled output.

### Concurrency
- **EC-006**: Two `osspulse run` processes overlap writing the same state file → state-store-3
  atomic `os.replace` guarantees one complete file wins, never a corrupt merge. Expected: last
  writer wins cleanly; documented as acceptable for a single-operator tool (no locking in V1).
- **EC-007**: Overlapping runs writing the same `output_path` → delivery-6 atomic write guarantees
  no partial file. Expected: one complete digest, never truncated.

### Data integrity
- **EC-008**: Summarizer returns FEWER items than collected (some skipped/failed) → only survivors
  are rendered; the run still succeeds. Expected: digest reflects survivors; skipped items logged,
  not silently counted as summarized.
- **EC-009**: `mark_seen` is called for an item but summarization later fails for it → seen-state
  and summary are decoupled; the item is recorded seen (collected) even if not summarized.
  Expected: V1 records what was *collected*; acceptable (re-summarize is cheap via cache in V2).

### Permission / secrets
- **EC-010**: `GITHUB_TOKEN` missing → `load_config` already raises `ConfigError` before the
  pipeline starts (config.py) → `Error: GITHUB_TOKEN is required`, exit 1. Expected: fail fast,
  token never logged.
- **EC-011**: GitHub returns 401/403 (bad/again-expired token) mid-run for a repo → collector
  raises `AuthError`; S7 treats auth failure as **fatal** (all repos share one token) → exit 1
  with a clear message, NOT a per-repo skip. Expected: distinguish auth (fatal) from per-repo 404
  (skip).

### Integration failure
- **EC-012**: One repo 404s / is private / renamed (`InvalidRepoError` or 404) → log warning,
  skip that repo, continue others; run still exits 0 if any repo succeeded. Expected: one bad repo
  doesn't kill the digest.
- **EC-013**: GitHub rate limit hit (429 / `RateLimitError` after collector's own backoff
  exhausted) → S7 surfaces a clear message; remaining repos for this run are skipped (cannot
  proceed without quota). Expected: no crash/stacktrace; partial digest from repos already
  collected is still delivered if any.
- **EC-014**: LLM provider times out / errors for some items → summarizer degrades (skip-log-
  continue, summarizer-llm-4); those items rendered without a summary or omitted per summarizer
  contract; run continues. Expected: LLM failure never aborts the whole digest.
- **EC-015**: Redis cache unreachable → cache-aside treats as miss, re-summarizes; no crash.
  Expected: graceful degradation (best-effort cache).
- **EC-016**: Output path's parent directory does not exist → delivery-6 does NOT mkdir
  (AC-6-014); `FileDelivery` raises `DeliveryError` → `Error: <msg>`, exit 1. Expected: clear
  error, no partial file.

### UI/UX (CLI)
- **EC-017**: `osspulse run --config missing.toml` → `ConfigError` "cannot read … file not
  found", exit 1. Expected: clear one-line stderr message, no traceback.
- **EC-018**: `osspulse run` piped to `head` then closed (SIGPIPE) on stdout delivery →
  `BrokenPipeError` handled at CLI top level (delivery-6 ADR-003), clean exit 0. Expected: no
  `BrokenPipeError` traceback.

### Business rule
- **EC-019**: `llm_provider` configured but `llm_api_key` resolution already enforced by
  `load_config` (remote provider requires key) → S7 trusts config; no second validation.
  Expected: no duplicate validation, single source of truth (config.py).
- **EC-020**: A run where every repo fails (all 404 / all rate-limited) → no items collected;
  `render([], lookback_days)` returns the "no new items" doc; delivered; **exit code** =
  decided at S2 (success-with-warnings vs failure). Flagged for AC.

## Early Risk Flags

STRIDE domain: **Tokens/Secrets + External Integration** (`security.stride_analysis = auto` →
applies because S7 handles `GITHUB_TOKEN` and the LLM key end-to-end). No auth/payment/PII/upload.

- **RF-1 (Information disclosure — HIGH)**: `GITHUB_TOKEN` / `llm_api_key` must never appear in
  any log line, error message, or the delivered digest. The pipeline logs repo names, item ids,
  counts, and error *types* only. Mitigation: reuse the established no-secret-logging discipline
  (collector-2 ADR-004, summarizer-llm-4 ADR-008). Drives a security AC + a static/log-capture test.
- **RF-2 (Denial of service / cost — MEDIUM)**: A large watchlist × large `lookback_days` could
  exhaust GitHub quota or run up LLM cost. Mitigation: collector already backs off on rate limit;
  S7 stops cleanly on `RateLimitError`. `lookback_days > 365` already warns (config.py). No new
  guard needed for V1; note for monitoring.
- **RF-3 (Tampering / integrity — MEDIUM)**: Partial/corrupt digest or state file on crash.
  Mitigation: both delivery (delivery-6) and state store (state-store-3) write atomically
  (temp + `os.replace`). S7 must not introduce a non-atomic write path.
- **RF-4 (Repudiation / observability — LOW)**: Without run logging, a silent partial failure
  (some repos skipped) is invisible. Mitigation: log per-repo outcome (collected N / skipped:
  reason) at INFO/WARN so the operator can see what happened. Drives an observability AC.
- **RF-5 (Spoofing — N/A)**: No inbound surface (CLI-only, single operator). No authn to spoof.
- **RF-6 (Elevation of privilege — LOW)**: Token scope is read-only public-repo (project
  principle); S7 issues only the GETs the collector already makes. No new privilege surface.

STRIDE gate: **PASS** — no Critical; RF-1 (High) has an established mitigation + a test plan.
