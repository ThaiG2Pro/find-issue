# Proposal: V3-003 — Upstash Redis state backend (`v3-upstash-state`)

> Type: **CR** · Rigor: **lite** · Scope: **tiny** · Ticket: **V3-003**

## Why

V3-002 made osspulse run on GitHub Actions, but a CI runner is **stateless**: the JSON
state file (`.osspulse/state.json`) that makes runs idempotent/delta-aware is discarded
when the runner dies. V3-002 worked around this by committing `state.json` back into the
repo (`git commit [skip ci]`) — a fragile mechanism (needs `contents: write`, force-add of
a gitignored path, a clean-tree guard, and it leaks seen-issue history into git history).

Upstash Redis exposes a plain **HTTP REST API** (not the TCP redis protocol), so it works
from any serverless/stateless environment including GitHub Actions. Persisting seen-state
in Upstash lets the CI run be idempotent **without** committing anything back to the repo.
Free tier (10k commands/day) comfortably covers 1 run/day over a small watchlist.

## What Changes

- **NEW** adapter `UpstashStateStore` (`src/osspulse/state/upstash_store.py`) — implements the
  existing `osspulse.ports.StateStore` Protocol (`load`/`save`) **plus** the `is_seen`/
  `mark_seen` helpers the pipeline actually calls, backed by the `upstash-redis` HTTP client.
  One Redis hash per repo: key `osspulse:state:{repo}`, field `{item_type}:{item_id}`,
  value = `first_seen_at` UTC ISO-8601 (`…Z`).
- **NEW** backend selection in `pipeline._build_store()` — a new helper (mirroring the existing
  `_build_cache`/`_build_etag_cache`) that picks the backend by env-var presence: both
  `UPSTASH_REDIS_REST_URL` **and** `UPSTASH_REDIS_REST_TOKEN` set → `UpstashStateStore`;
  otherwise → the existing `JsonFileStateStore(config.state_path)` (unchanged behavior).
- **NEW** Python dependency `upstash-redis` (pinned).
- **UNCHANGED**: `osspulse.ports.StateStore` Protocol signature; `JsonFileStateStore`
  behavior; the `[state] state_path` config; all existing state-store ACs (AC-3-001..018).

## Capabilities

- **New Capabilities**: `upstash-state` — an alternate, network-backed state backend and the
  env-driven backend-selection rule. (Conceptually part of the S3 State Store bounded context;
  it does not change the existing JSON-file requirements, it adds an alternative — so it is an
  ADDED concern, per OpenSpec guidance, not a MODIFIED one.)
- **Modified Capabilities**: none. No existing state-store requirement's behavior changes.

## Impact

- **Affected**: `src/osspulse/state/upstash_store.py` (new), `src/osspulse/pipeline.py`
  (add `_build_store()` + widen the `state` param type from the concrete `JsonFileStateStore`
  to a shared seen-tracker type — see R-2), `pyproject.toml` (add `upstash-redis`), README/
  `.env.example` (document the two Upstash secrets).
- **Runtime deps**: an Upstash Redis database (operator-provisioned) + its REST URL/token.
  When the two env vars are absent, zero new runtime dependency (local dev keeps using the
  JSON file).
- **No change** to collector, summarizer, renderer, delivery, or the summary-cache (that stays
  on its own `REDIS_URL` TCP client — see Non-Goals).

## Non-Goals

- ❌ Migrating the **LLM summary cache** to Upstash — it already has its own Redis
  (`REDIS_URL`, redis-py TCP, best-effort) and different failure semantics. Separate concern.
- ❌ **TTL / expiry** on state keys — seen-state is retained indefinitely (idempotency history).
- ❌ **Multi-user / multi-tenant** namespacing — single operator; a fixed `osspulse:state:`
  key prefix is sufficient.
- ❌ Changing the `osspulse.ports.StateStore` Protocol signature (`load`/`save` stay as-is).
- ❌ Removing the V3-002 git-commit-back workflow in this CR (it can be retired later once
  Upstash is proven; this CR only makes Upstash available as the CI backend).
- ❌ A migration tool to copy an existing local `state.json` into Upstash (fresh start on CI is
  acceptable — worst case the first CI run re-renders once).

## Assumptions

- **[CONFIRMED]** Backend is chosen by **presence of both** `UPSTASH_REDIS_REST_URL` and
  `UPSTASH_REDIS_REST_TOKEN`; missing either → fall back to `JsonFileStateStore`. *Source: user
  scope constraints 2 & 4.*
- **[CONFIRMED]** Client is the `upstash-redis` pip package (HTTP REST). *Source: user scope 1.*
- **[CONFIRMED]** Key layout: one hash per repo, `osspulse:state:{repo}`, field
  `{item_type}:{item_id}`, value `first_seen_at`. *Source: user scope 3.*
- **[CONFIRMED]** The `StateStore` Protocol is not changed; a new adapter only. *Source: scope 5.*
- **[ASSUMED]** Because the pipeline calls `is_seen`/`mark_seen` (NOT `load`/`save`), the Upstash
  adapter MUST implement those helpers with byte-for-byte identical semantics to
  `JsonFileStateStore` — write-once `first_seen_at`, empty-list no-op, `repo+item_type+item_id`
  identity. This is the real contract, larger than the Protocol. *Informed from pipeline.py; see R-1.*
- **[ASSUMED]** When the two env vars ARE set but Upstash errors at runtime, the run **fails loud**
  (`StateError` → exit 1) rather than silently falling back to the local file or degrading —
  because this is the **idempotency** store; a silent degrade would drop or re-render items.
  Fallback is a *construction-time* choice on env-var absence only, never a runtime catch.
  *Informed default; contrast with the best-effort summary/ETag caches (v2-cache-etag lesson).*
- **[ASSUMED]** `first_seen_at` write-once is enforced with `HSETNX` (set-if-absent per field),
  so a re-marked item keeps its original timestamp without a read-modify-write race.

## Edge Cases (scope=tiny → the categories that genuinely apply)

- **E-1 (data integrity / idempotency)**: Upstash reachable but a `mark_seen` write errors
  mid-run → MUST raise `StateError`, NOT swallow it. A swallowed write loses idempotency (the
  item is rendered now but never recorded → re-rendered next run, or worse, reported seen when
  it is not). Fail loud so the next run safely re-processes.
- **E-2 (state transition / backward compat)**: An existing local user with no Upstash env vars
  → unchanged `JsonFileStateStore` path, no new dependency exercised, all AC-3-* still hold.
- **E-3 (idempotency)**: Re-running the same items → `HSETNX` is a no-op on existing fields, so
  `first_seen_at` is preserved and no duplicate render occurs (mirrors AC-3-004).
- **E-4 (input boundary)**: Empty `item_id` → field keys safely as `"{item_type}:"` (e.g.
  `"issue:"`), accepted exactly like the JSON store (EC-002), not rejected.
- **E-5 (integration — the whole point)**: A GitHub Actions runner with both env vars set →
  seen-state reads/writes go to Upstash and survive the runner being destroyed, so the next
  scheduled run is delta-aware with **no** git commit-back.
- **E-6 (information disclosure / permission)**: The REST URL/token must NEVER appear in a log
  line, error message, or committed file — only read from env (`${{ secrets.* }}` on CI).
- **E-7 (data / key encoding)**: A repo slug contains `/` and `.` (`vercel/next.js`) → valid
  inside a Redis key (`osspulse:state:vercel/next.js`); no escaping needed, no collision with
  the field separator `:` because the field is `{item_type}:{item_id}` within the per-repo hash.

## Early Risk Flags (incl. STRIDE — feature adds a network dependency + secrets)

- **R-1 (Contract wider than the Protocol — the core trap)**: `osspulse.ports.StateStore`
  declares only `load`/`save`, but `pipeline._partition_new` / `_collect_all` call
  `state.is_seen(...)` and `state.mark_seen(...)` directly on the concrete adapter. Any new
  backend that implements ONLY `load`/`save` would `AttributeError` at runtime. The Upstash
  adapter MUST implement `is_seen`/`mark_seen` too, with identical semantics. Architect: confirm
  whether to add a richer internal Protocol (e.g. a `SeenTracker` with `is_seen`/`mark_seen`) in
  `ports.py` for the type hint — that ADDS a Protocol, it does NOT change `StateStore`, so scope
  constraint 5 is still honored.
- **R-2 (Type-hint coupling)**: `_partition_new(items, state: JsonFileStateStore)` and
  `_collect_all(..., state: JsonFileStateStore)` are typed to the concrete class. To accept the
  Upstash backend they must widen to the shared seen-tracker type (or duck-typing). Behavior
  unchanged; type annotation only.
- **R-3 (Information disclosure — STRIDE I)**: The Upstash REST token is a bearer credential.
  Mitigation: read only from env, never log the URL/token, never write to a committed file; on
  CI supply via `${{ secrets.* }}`.
- **R-4 (Availability / idempotency — STRIDE D)**: If Upstash is down and the code silently fell
  back to the (empty, on a fresh CI runner) local file, the run would re-render everything or
  lose seen-state. Mitigation: env-vars-set ⇒ Upstash is authoritative ⇒ runtime failure is
  fatal (`StateError`), never a silent local fallback (see E-1).
- **R-5 (Tampering — STRIDE T)**: Upstash data is remote and shared by anyone with the token.
  Low sensitivity (public-repo issue IDs), accepted; noted so an operator with a private
  watchlist uses a dedicated database + rotates the token.

Figma: N/A (CLI / backend infra — no UI).
