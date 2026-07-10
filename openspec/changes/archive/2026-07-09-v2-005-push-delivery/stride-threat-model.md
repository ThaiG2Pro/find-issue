# STRIDE Threat Model — V2-005 Push Delivery (Discord webhook)

**Domain**: Messaging / outbound external integration
**Config trigger**: `security.stride_analysis = auto` → runs (feature touches a secret (webhook URL) + outbound network).
**Data flow**: rendered Markdown digest (str) → DiscordDelivery.deliver() → HTTPS POST to `DISCORD_WEBHOOK_URL` → Discord.

## Executive Summary
No inbound endpoint — this is an **outbound** integration, so classic Spoofing/Elevation of a
listener don't apply. The real risks are: leaking the webhook URL (a bearer secret), leaking
digest content to a mis-configured URL, and SSRF/DoS via an attacker-controlled URL. All are
mitigated by env-var secret handling + a fixed Discord host allowlist + timeout.

| # | Category | Threat | Sev | Mitigation | Gate |
|---|----------|--------|-----|-----------|------|
| T1 | Information disclosure | Webhook URL (bearer secret) leaked via logs, error messages, or config commit | High | URL from env var only (never config file, AC); never log the URL — log adapter name only; error messages must not echo the URL | mitigated |
| T2 | Information disclosure | Digest content (public repo data, but still user's watchlist) sent to a wrong/malicious URL | Medium | Validate URL scheme=https AND host ∈ Discord domains (`discord.com`/`discordapp.com`) at config load — fail fast | mitigated |
| T3 | Spoofing / SSRF | Attacker-supplied `DISCORD_WEBHOOK_URL` pointing at an internal host (`http://169.254.169.254/…`) turns the tool into an SSRF vector | Medium | Same https+host allowlist (T2) blocks non-Discord hosts and http:// | mitigated |
| T4 | Denial of service | Discord unreachable / hangs → pipeline blocks forever | Medium | Explicit request timeout (~10s); on timeout raise DeliveryError (fatal, CLAR-3) | mitigated |
| T5 | Tampering | Digest altered in transit | Low | HTTPS enforced (T2 scheme check) — TLS integrity | mitigated |
| T6 | Repudiation | No record a push happened / failed | Low | Run-summary log line records destination + success/failure (no URL) | mitigated |

## Security ACs driven (for S2)
- Webhook URL read from env var only, never from config file, never logged. (→ AC secret handling)
- Config load validates URL is `https://` + Discord host allowlist; else `ConfigError` fail-fast. (→ AC T2/T3)
- Request has an explicit timeout; timeout → `DeliveryError` (fatal). (→ AC T4)
- Error/`Error:` stderr message never contains the webhook URL. (→ AC T1)

## Gate: **PASS**
No Critical. All High/Medium threats have a concrete mitigation + a test case. Proceed to S2.

```
[stride-analysis] V2-005 — push-delivery (Discord webhook)
Threats: 6 (Critical 0 / High 1 / Medium 3 / Low 2)
Domain : Messaging / outbound integration
Gate   : PASS
Feeds  : analyst Early Risk Flags · architect design security · qa-test-design
```
