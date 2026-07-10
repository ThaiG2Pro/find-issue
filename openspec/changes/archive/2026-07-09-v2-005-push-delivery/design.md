## Sketch — Gap Analysis

**No critical gaps found.** httpx is already a dependency (`httpx>=0.27`), `DeliveryError`
+ CLI catch already exist, and the renderer emits stable `## {repo}` boundaries to split
on. All 15 ACs map to concrete design elements below.

## Context

V1 delivers the digest to a file or stdout via the `Delivery` port
(`deliver(content: str) -> None`) with two structural adapters (`FileDelivery`,
`StdoutDelivery`) selected in `pipeline.py` from `config.output_destination`. V2-005 adds a
third destination `"discord"` that POSTs the rendered Markdown to a Discord webhook. The
digest often exceeds Discord's 2000-character `content` limit, so it must be split into
multiple messages. The webhook URL is a bearer secret + SSRF vector, so it is env-var-only
and validated at config load.

**Constraints (from living spec + memory):**
- `Delivery` port signature is FROZEN — `deliver(content: str) -> None` (living spec AC-6-003; memory/analyst/delivery-6 port-drift lesson).
- Delivery modules must NOT import `osspulse.github/summarizer/cache/render` (AC-6-002, AC-V2-005-003).
- One error class per infra module, surfaced at CLI as `Error: <msg>` + exit 1 (memory/architect/delivery-6).
- OSS Pulse is a CLI tool with no HTTP API → no `openapi.yaml` (precedent: delivery-6 ADR-007).

## Goals / Non-Goals

**Goals:**
- Add `DiscordDelivery` implementing the frozen `Delivery` port (AC-V2-005-001, AC-V2-005-002), POSTing the digest via httpx over HTTPS.
- Split a >2000-char digest into ≤2000-char messages at `## ` repo boundaries (AC-V2-005-004, AC-V2-005-005), hard-split by line as fallback, counting Unicode characters.
- Resolve + validate the webhook URL (https + Discord host allowlist) at config load, fail-fast.
- Fatal push semantics with an explicit ~10s timeout; never leak the URL.

**Non-Goals:**
- Multi-channel / parallel delivery, Slack, Email (→ V3). Retry/backoff, Discord embeds (→ V4). No port-signature change. No rollback of partial multi-message pushes.

## Architecture Overview

**Dependencies (from other changes):** delivery-6 (`Delivery` port, `DeliveryError`, adapter pattern, CLI catch); github-collector-2 (`httpx.Client` + timeout usage pattern); digest-renderer-5 (`render(...) -> str`, `## {repo}` boundary format).

```
config.py  ──[output].destination="discord" + webhook env]──▶ Config(output_destination, webhook_url, webhook_env)
                                    │ validate https + host allowlist at load (fail-fast ConfigError)
                                    ▼
pipeline.py  ──elif "discord"──▶ DiscordDelivery(webhook_url, timeout=10.0)
                                    │ .deliver(digest_str)
                                    ▼
discord_delivery.py: _split_for_discord(content) → [msg1, msg2, …]  (each ≤2000 chars)
                     for each msg: httpx.post(url, json={"content": msg})  → raise DeliveryError on any failure
```

Layering: `delivery/` is a leaf infra module — imports only stdlib + httpx + `osspulse.delivery.errors`. No upstream imports (AC-V2-005-003).

## Decisions (ADRs)

### ADR-001 — Reuse httpx (no new dependency)
**Context.** DiscordDelivery needs an HTTPS client with a timeout. The proposal left "httpx vs new dep" open.
**Options.**
| Option | Pros | Cons |
|--------|------|------|
| A. Reuse `httpx` (already `httpx>=0.27`) | No new dep; same client the collector uses; native `timeout=` | none material |
| B. Add `requests` | Familiar API | New dependency for no gain; another supply-chain surface |
| C. stdlib `urllib.request` | Zero deps | Clunky timeout/error handling; manual JSON; more code |
**Decision.** **A** — reuse httpx. It is already a first-class dependency (`github/client.py` uses `httpx.Client(timeout=...)`), so this adds zero supply-chain surface and reuses a known pattern.
**Consequences.** DiscordDelivery constructs a short-lived `httpx.Client(timeout=...)` (or module-level `httpx.post` with `timeout=`). Timeout maps directly to AC-V2-005-010.

### ADR-002 — Character-based two-level split (repo boundary → line fallback)
**Context.** Digest > 2000 chars must split; Discord counts **characters**, not bytes (AC-V2-005-007); a single repo section can alone exceed 2000 (AC-V2-005-006).
**Options.**
| Option | Pros | Cons |
|--------|------|------|
| A. Split at `## ` repo boundaries, then hard-split any oversized piece by line, measured in `len(str)` chars | Preserves readable repo blocks; guarantees ≤2000; matches renderer output | Two-level logic to test |
| B. Blind fixed-size char chunks every 2000 | Trivial | Cuts mid-line/mid-word; ugly, unreadable |
| C. Byte-based split | — | WRONG: over-splits non-ASCII ("Khác", emoji); Discord counts chars |
**Decision.** **A** — greedy accumulate `## ` sections into a message while ≤2000 chars; a section that alone exceeds 2000 is line-split (and, defensively, a single line > 2000 is char-sliced). All measured with `len(s)` (Python str length = Unicode code points).
**Consequences.** `_split_for_discord(content, limit=2000)` is a pure function → easy unit tests for boundary (2000/2001), oversized section, and non-ASCII cases. The leading `# OSS Pulse Digest` header rides with the first message.

### ADR-003 — Config-load URL resolution + https/host allowlist (fail-fast)
**Context.** Webhook URL is a bearer secret (T1) and an SSRF vector (T2/T3). Must resolve from env + validate before the pipeline runs.
**Options.**
| Option | Pros | Cons |
|--------|------|------|
| A. Resolve env var + validate https + Discord host allowlist in `load_config`; `ConfigError` on any failure | Fail-fast before any network; secret never in config file; SSRF blocked at boundary | Config gains delivery-specific knowledge |
| B. Validate lazily inside DiscordDelivery at deliver time | Keeps config thin | Fails late (after full pipeline runs); scatters security check |
**Decision.** **A** — mirror the existing `_resolve_token`/`_resolve_llm` env pattern in `config.py`. Validate: non-empty, `urlparse` scheme == `https`, host ∈ {`discord.com`, `discordapp.com`}. Raise `ConfigError` otherwise.
**Consequences.** `Config` gains `webhook_url: str | None` (resolved value) + `webhook_env: str` (source name, default `DISCORD_WEBHOOK_URL`). AC-V2-005-012/013/014/015 all resolve at load. DiscordDelivery receives the already-validated URL — it does not re-read env.

### ADR-004 — No openapi.yaml (CLI tool, no HTTP API)
**Context.** R5/R9 expect an openapi.yaml for API changes.
**Decision.** N/A — OSS Pulse exposes no HTTP API (it is an outbound HTTP *client*). The integration seam is a Python Protocol + config + CLI wiring (INT-V2-005-001), not an endpoint. **Rule cited:** R5/R9. **Precedent:** delivery-6 ADR-007, digest-renderer-5 ADR-005, state-store-3 ADR-004 set this exact CLI-only exception.
**Consequences.** No openapi.yaml in this change dir; cross-artifact-audit treats API coverage as N/A.

## API Design

_(unchanged — no HTTP API; see ADR-004.)_ The only external contract is the **outbound**
Discord webhook call: `POST {webhook_url}` with header `Content-Type: application/json` and
body `{"content": "<=2000-char chunk>"}`, expecting a 2xx. This is a client call, not an
endpoint we expose.

## DB Schema

_(unchanged — no database; state is JSON files, and this change adds none.)_

## Error Mapping

| Condition | Raised | Surfaced | AC |
|-----------|--------|----------|-----|
| Webhook env var unset/empty (destination=discord) | `ConfigError` | `Error:` stderr, exit 1, at load | AC-V2-005-013 |
| Webhook URL not https | `ConfigError` | same, at load | AC-V2-005-014 |
| Webhook host not in allowlist | `ConfigError` | same, at load | AC-V2-005-015 |
| Invalid `destination` value | `ConfigError` | same, at load | AC-6-012 |
| HTTP non-2xx (404/429/5xx) | `DeliveryError` | `Error:` stderr, exit 1 | AC-V2-005-008 |
| Connection/DNS error | `DeliveryError` | same | AC-V2-005-009 |
| Timeout (~10s) | `DeliveryError` | same | AC-V2-005-010 |
| Multi-message msg _k_ fails | `DeliveryError` | same; msgs 1..k-1 already sent (no rollback) | AC-V2-005-008, RISK-1 |

**URL-leak guard (T1, AC-V2-005-011):** `DeliveryError` messages are composed from the
HTTP status / exception *type*, NEVER the URL or `httpx` request repr (which embeds the URL).
The run-summary log line names the destination (`discord`) only.

## Sequence Flows

**Flow 1 — config load (fail-fast):** read `[output]`; if `destination=="discord"` → env name = `webhook_env` or `DISCORD_WEBHOOK_URL` → read env → assert non-empty, https, host∈allowlist → else `ConfigError` → store on `Config`.

**Flow 2 — deliver:** `pipeline` builds `DiscordDelivery(cfg.webhook_url, timeout=10.0)` → `.deliver(digest)` → `msgs = _split_for_discord(digest)` → for each: `client.post(url, json={"content": msg})`; on non-2xx or transport error → `DeliveryError` (no URL in msg) → propagate to CLI → exit 1. All 2xx → return.

## Edge Cases

Covered by proposal EC-001..016. Design-specific handling:
- EC-007/008 (2000 / 2001 chars): `_split_for_discord` boundary — `len(content) <= 2000` → single msg.
- EC-009 (single section > 2000): line-split fallback; defensively char-slice a single >2000 line.
- EC-010 (empty / "No new items"): one short msg, verbatim (mirrors AC-6-020).
- EC-011 (non-ASCII): `len(str)` counts code points, not bytes.
- EC-016 (URL leak): error/log never contains URL.

## Performance

Negligible. One digest per run; typically 1–3 sequential POSTs. httpx timeout bounds worst
case (~10s × n messages). No connection pooling needed for a handful of POSTs; a single
`httpx.Client` reused across the loop is sufficient.

## Security

- **T1 (High, URL leak):** env-var-only secret; never logged; `DeliveryError` text excludes URL; run-summary names destination only. (AC-V2-005-011)
- **T2/T3 (Medium, mis-route/SSRF):** https-scheme + Discord-host allowlist at config load blocks http:// and non-Discord/internal hosts. (AC-V2-005-014/015; ADR-003)
- **T4 (Medium, DoS):** explicit ~10s httpx timeout → fatal `DeliveryError`, pipeline never hangs. (AC-V2-005-010)
- **T5 (Low):** HTTPS enforced → TLS integrity. **T6 (Low):** run-summary records push outcome.
All Critical/High threats mitigated (STRIDE gate PASS).

## Risk Assessment

- [RISK-1: partial multi-message delivery] → No transactional rollback exists in Discord. Accepted; `DiscordDelivery` sends sequentially and fails fatally at the first failure. The run-summary log MAY note messages sent before failure (developer's discretion; not an AC). Documented so it is not treated as a bug at S5.
- [Split logic emits a >2000 message] → line-split + defensive char-slice guarantee ≤2000; unit-tested at boundaries.
- [Byte-vs-char mistake] → ADR-002 mandates `len(str)`; explicit non-ASCII test (AC-V2-005-007).

## Implementation Guide

**Recommended order** (data/config → adapter → wiring → tests):
1. `models.py` — add `Config.webhook_url: str | None = None`, `Config.webhook_env: str = "DISCORD_WEBHOOK_URL"`.
2. `config.py` — extend `[output]` parsing: accept `"discord"`; parse optional `webhook_env`; resolve env; validate https + host allowlist; `ConfigError` on failure. Mirror `_resolve_token` structure.
3. `delivery/discord_delivery.py` — `_split_for_discord(content, limit=2000)` pure fn + `DiscordDelivery` class (`__init__(webhook_url, timeout=10.0, client=None)`, `deliver(content)`). Raise `DeliveryError` from httpx errors WITHOUT the URL.
4. `delivery/__init__.py` — export `DiscordDelivery`.
5. `pipeline.py` (~line 288) — add `elif config.output_destination == "discord": delivery = DiscordDelivery(config.webhook_url, timeout=10.0)`.
6. Tests — see tasks.md (split boundaries, non-ASCII, config validation, HTTP error mapping, URL-leak, import-decoupling).

**Patterns to follow:**
- Adapter: `src/osspulse/delivery/file_delivery.py` (structural port impl, no subclassing).
- Secret env resolution: `config.py` `_resolve_token` / `_resolve_llm`.
- httpx client + timeout: `src/osspulse/github/client.py` (`httpx.Client(timeout=...)`).
- Error class + CLI catch: `delivery/errors.py` `DeliveryError`; `cli.py` already catches it → reuse, do NOT add a new error class.

**Gotchas:**
- Count `len(str)` (chars), NEVER `len(content.encode())` (bytes) — AC-V2-005-007.
- Do NOT put the webhook URL in any `DeliveryError` message, log line, or exception chain that renders the URL (httpx `RequestError` repr can include it — build the message from `type(exc).__name__` / status, not `str(exc)` if it embeds the URL).
- Do NOT `mkdir`/touch the filesystem — discord path writes nothing (unlike FileDelivery).
- Keep `delivery/discord_delivery.py` free of upstream imports (AC-V2-005-003) — inject the client for testing instead of importing anything.
- A 204 (Discord's typical webhook success) is 2xx — treat any 2xx as success, not just 200.
