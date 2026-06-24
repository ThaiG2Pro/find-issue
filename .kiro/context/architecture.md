# Architecture

## Style
**Linear pipeline + ports/adapters (hexagonal-lite).** Data flows one direction
through stages S1→S7. Every external dependency (GitHub, LLM, delivery, state,
cache) sits behind an interface (port) with a concrete adapter, so it can be mocked
in tests and swapped later.

## Layers & Boundaries
- **Core / domain**: pipeline orchestration + data models (raw item, summarized
  item, digest). Pure logic, no direct I/O.
- **Ports**: interfaces — `GitHubClient`, `LLMClient`, `StateStore`, `SummaryCache`,
  `Delivery`.
- **Adapters / infrastructure**: concrete implementations — httpx GitHub client,
  LiteLLM summarizer client, JSON-file state store, Redis cache, file/stdout delivery.
- **Interface**: Typer CLI (`S7`) wires config → ports → pipeline.

Rule: core depends on port interfaces only, never on concrete adapters. Adapters
depend on core models, not on each other. **S2 (GitHub I/O) and S4 (LLM I/O) must
never call each other directly** — they communicate only through pipeline data.

## Key Patterns
- **Ports & adapters** for every external dependency.
- **Pipeline / pipes-and-filters** — each stage transforms and passes data forward.
- **Cache-aside** for LLM summaries (check Redis → call LLM on miss → store).
- **Idempotency via state store** — skip items already seen/summarized.

## Transaction & Consistency
No DB transactions in V1. Consistency is achieved by idempotency: the JSON state
store records seen items, and the run is re-runnable without duplicate output.
State writes should be atomic (write-temp-then-rename) to survive crashes mid-run.
Redis cache is best-effort — a cache miss/failure must degrade gracefully (re-summarize),
never crash the pipeline.

## Directory Map
```
src/osspulse/
  cli.py            # S7 — Typer entrypoint, wiring
  config.py         # S1 — config + watchlist load/validate
  pipeline.py       # core orchestration (S1→S6 flow)
  models.py         # domain data models (RawItem, SummarizedItem, Digest)
  ports.py          # interfaces: GitHubClient, LLMClient, StateStore, SummaryCache, Delivery
  github/           # S2 — httpx GitHub collector adapter (REST V1, GraphQL V2)
  summarizer/       # S4 — LiteLLM adapter + cache-aside logic
  state/            # S3 — JSON-file state store adapter
  cache/            # Redis summary-cache adapter
  render/           # S5 — Markdown digest renderer
  delivery/         # S6 — file/stdout (V1), email/webhook (V2)
tests/              # pytest, GitHub/LLM mocked
```

## Anti-patterns (do NOT do)
- Coupling S2 and S4 (mixing GitHub I/O with LLM I/O in one unit).
- Calling real GitHub/LLM APIs from tests.
- Hardcoding or committing secrets; reading tokens from anywhere but env/`.env`.
- Adding a DB server, queue/broker, or web framework in V1 (over-engineering — the
  spec explicitly forbids it until there is a clear reason).
- Producing duplicate digests / re-summarizing already-seen items (breaks idempotency).
- Scanning beyond the user's watchlist.
