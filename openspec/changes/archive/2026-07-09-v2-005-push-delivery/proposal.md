## Why

V1 delivers the digest only to a local file or stdout — the user must actively open
the tool/file to read it. PROJECT_SPEC V2 (Nhóm C, [P1]) calls for **one push channel**
so the digest reaches the user without them pulling it. Per the V2 spec's "choose one
channel first" guidance, we implement **Discord webhook** — the simplest transport
(single HTTPS POST, one secret, no auth handshake, renders Markdown near-directly).

## What Changes

- Add a new **Discord webhook** delivery adapter (`DiscordDelivery`) that POSTs the
  rendered Markdown digest to a Discord webhook URL.
- Add `"discord"` as a third value for `output.destination` (alongside `"file"`,
  `"stdout"`), mutually exclusive — one destination per run (preserves BR-7-007
  "deliver once").
- Discord's **2000-char content limit** → the digest is split into multiple sequential
  messages at repo-section (`## repo`) boundaries; a single section still >2000 chars is
  hard-split by line at 2000.
- Webhook URL is a **secret** read from an env var (default `DISCORD_WEBHOOK_URL`,
  variable name configurable in `[output]`) — never from the config file, never logged.
- Config load validates the URL is `https://` + a Discord host (`discord.com` /
  `discordapp.com`) and fails fast (`ConfigError`) otherwise (SSRF / mis-route guard).
- Push failure (HTTP 4xx/5xx, timeout, network error) is **fatal**: `DeliveryError` →
  one-line `Error:` on stderr → exit 1 (consistent with file delivery). Explicit request
  timeout (~10s) prevents hanging the pipeline.

## Capabilities

### New Capabilities
- _None._

### Modified Capabilities
- `delivery`: ADD the Discord push destination + adapter; MODIFY the "Destination
  selection is config-driven" requirement to accept `"discord"` and parse the webhook
  env-var + host validation. All existing file/stdout requirements are unchanged.

## Impact

- **Code**: new `src/osspulse/delivery/discord_delivery.py`; `src/osspulse/delivery/__init__.py`
  export; `config.py` (`[output]` parsing + URL/env validation); `models.py` `Config`
  (new fields for webhook env-var name); `pipeline.py` delivery selection (`elif "discord"`).
- **Deps**: reuses the HTTP client already used by the GitHub collector (`httpx`) — no new
  dependency expected (architect confirms at S3).
- **Ports**: `Delivery` Protocol (`deliver(content: str) -> None`) is **unchanged** —
  `DiscordDelivery` implements it structurally, like `FileDelivery`/`StdoutDelivery`.
- **Config/secret**: new env var `DISCORD_WEBHOOK_URL`; documented in `.env.example` +
  README. No secret committed.

Figma: N/A (CLI tool, no UI)

## Non-Goals

Cố ý KHÔNG làm trong V2-005 (để dành roadmap — xem PROJECT_SPEC §5):
- ❌ **Đa kênh song song** (vừa file vừa Discord trong 1 lần chạy) — giữ deliver-once (BR-7-007). → V3.
- ❌ **Slack webhook / Email SMTP** — chỉ Discord trước (CLAR-1). → V3.
- ❌ **Retry + backoff / tôn trọng 429 Retry-After** — push fail là fatal, không retry (CLAR-3). → V4.
- ❌ **Discord rich embeds** — chỉ plain `content`, không dùng embed schema (CLAR-4). → V4.
- ❌ **Rollback multi-message** — Discord không có API rollback; partial delivery được chấp nhận (RISK-1).
- ❌ Đổi `Delivery` port signature — giữ nguyên `deliver(content: str) -> None`.

## Assumptions

### [CONFIRMED] — resolved via clarification (2026-07-08) + SPEC LOCK sign-off (2026-07-08)
- Channel is **Discord webhook**, implemented first (CLAR-1).
- Push is a **third `output_destination`** value `"discord"`, mutually exclusive with
  file/stdout — deliver once (CLAR-2).
- Push failure is **fatal** (`DeliveryError`, exit 1) with an explicit ~10s timeout (CLAR-3).
- Digest >2000 chars is **split into multiple messages** at repo-section boundaries (CLAR-4).
- Webhook URL from **env var** (default `DISCORD_WEBHOOK_URL`); a section still >2000
  chars is **hard-split by line** at 2000 (CLAR-5).
- **URL validation** = scheme `https` + host ∈ {`discord.com`, `discordapp.com`} at config
  load, fail-fast `ConfigError` (STRIDE T2/T3; AC-V2-005-014/015). Signed off at SPEC LOCK.
- **Discord adapter does not import upstream modules** (AC-V2-005-003) — extends AC-6-002.
- **2000 limit counts Unicode characters, not bytes** (AC-V2-005-007).
- **Webhook URL never leaks** to logs/errors/run-summary (AC-V2-005-011; STRIDE T1).
- **discord + empty webhook env var → `ConfigError`** at load (AC-V2-005-013).

### [ASSUMED] — informed guess, validate in S3
- **HTTP client** = reuse `httpx` (already a dependency for the GitHub collector) rather
  than add `requests`. Architect confirms at S3.
- **Split unit** = Discord `content` field, plain string (not embeds). Messages POSTed
  **sequentially**; if message _k_ fails, the push fails fatally (partial delivery of
  earlier messages is accepted — same "deliver what succeeded then error" spirit as the
  pipeline's partial-results behavior).
- **Empty/`No new items` digest** is still pushed as a single short message (delivered
  verbatim, mirrors AC-6-020 for file/stdout).

### [SAFE] — documented, low risk
- Webhook URL as a secret via env var — matches `security.md` + existing
  `github_token`/`llm_api_key` pattern (source: config.py `_resolve_token`).
- Delivery does NOT import upstream pipeline modules — living-spec constraint AC-6-002.
- `Delivery` port signature unchanged — living spec + memory/analyst/delivery-6 (port drift lesson).

## Edge Cases

### Integration failure
- EC-001: Webhook returns HTTP 404 (deleted/invalid webhook) → `DeliveryError`, `Error:` stderr, exit 1, no URL in message.
- EC-002: Webhook returns HTTP 429 (rate limited) → treated as fatal `DeliveryError` (no retry in V2; note Retry-After for V3).
- EC-003: Webhook returns HTTP 5xx (Discord outage) → `DeliveryError`, exit 1.
- EC-004: Network unreachable / DNS failure → `DeliveryError`, exit 1, no stacktrace.
- EC-005: Request exceeds ~10s timeout → `DeliveryError` (timeout), exit 1 (pipeline not hung).
- EC-006: Multi-message push — message 1 succeeds, message 2 fails → fatal error surfaced; earlier messages already delivered (partial, accepted).

### Input boundary
- EC-007: Digest exactly 2000 chars → single message, no split.
- EC-008: Digest 2001 chars → split into ≥2 messages, each ≤2000.
- EC-009: A single repo section >2000 chars → hard-split by line at 2000; no message exceeds the limit.
- EC-010: Empty / "No new items" digest → single short message, delivered verbatim (not suppressed).
- EC-011: Digest with non-ASCII (e.g. "Khác", emoji) → UTF-8 byte length counted correctly against the 2000 limit (Discord counts characters, not bytes — must count Unicode code points/chars, not bytes).

### Data integrity / config
- EC-012: `destination = "discord"` but env var unset/empty → `ConfigError` at load (fail fast, before pipeline runs).
- EC-013: Webhook URL is `http://` (not https) → `ConfigError` (STRIDE T3).
- EC-014: Webhook URL host is not a Discord domain (e.g. `https://evil.example/x`) → `ConfigError` (STRIDE T2/T3 SSRF guard).
- EC-015: `destination = "discord"` with a stray `output_path` set → `output_path` ignored (like stdout mode).

### Permission / security
- EC-016: Webhook URL must never appear in any log line, error message, or run-summary (STRIDE T1) — only the adapter name/destination.

## Early Risk Flags

From `stride-threat-model.md` (Gate: **PASS**, 0 Critical):
- **T1 (High, Info-disclosure)**: webhook URL is a bearer secret — must not leak via logs/errors/config. Mitigation: env-var only, never logged, never in error text.
- **T2 (Medium, Info-disclosure)**: digest sent to a wrong/malicious URL. Mitigation: https + Discord-host allowlist at config load.
- **T3 (Medium, Spoofing/SSRF)**: attacker-set URL → SSRF to internal host. Mitigation: same allowlist (T2) blocks http:// and non-Discord hosts.
- **T4 (Medium, DoS)**: Discord hang → pipeline blocks. Mitigation: explicit ~10s timeout → fatal.
- **T5 (Low, Tampering)**: in-transit alteration. Mitigation: HTTPS.
- **T6 (Low, Repudiation)**: no push record. Mitigation: run-summary log line (destination + outcome, no URL).

**RISK-1 (for architect)**: partial multi-message delivery semantics — if message _k_ of _n_ fails, messages 1..k-1 are already in Discord. Accepted as [ASSUMED]; architect decides whether to note it in the run-summary. No transactional rollback (Discord has no such API).
