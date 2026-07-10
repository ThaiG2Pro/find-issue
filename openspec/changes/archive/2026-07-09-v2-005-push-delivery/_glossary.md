| Term | Definition | Source | Phase |
|------|-----------|--------|-------|
| Discord webhook | A Discord-provided URL that accepts an HTTPS POST with a JSON body to post a message to a channel. Bearer secret (anyone with the URL can post). | Discord API | S1 |
| `output_destination = "discord"` | Third mutually-exclusive delivery destination value (alongside `file`, `stdout`). Selects `DiscordDelivery`. | CLAR-2 | S1 |
| `DiscordDelivery` | New adapter implementing the `Delivery` port (`deliver(content: str) -> None`) structurally; POSTs digest to the webhook. | proposal | S1 |
| 2000-char limit | Discord's max `content` length per message, measured in **Unicode characters** (not UTF-8 bytes). Digest is split to respect it. | Discord API / CLAR-4 | S1 |
| Repo-section boundary | A `## ` heading in the rendered digest marking one repo's block; the primary split point for multi-message push. | renderer output / CLAR-4 | S1 |
| Hard-split by line | Fallback split (on line boundaries at 2000 chars) when a single repo section alone exceeds 2000 chars. | CLAR-5 | S1 |
| Discord host allowlist | Config-load validation that the webhook URL is `https` + host ∈ {`discord.com`, `discordapp.com`}; blocks SSRF/mis-route. | STRIDE T2/T3 | S1 |
| `DISCORD_WEBHOOK_URL` | Default env var holding the webhook URL (secret). Name overridable via `[output] webhook_env`. Never read from the config file. | CLAR-5 / security.md | S1 |
| Fatal push | Push failure (HTTP error / network / timeout) → `DeliveryError` → `Error:` stderr → exit 1. Same contract as file delivery. | CLAR-3 | S1 |
| Partial multi-message delivery | If message k of n fails, messages 1..k-1 are already in Discord; no rollback (Discord has no such API). Accepted. | RISK-1 | S1 |
| `_split_for_discord` | Pure fn `(content, limit=2000) -> list[str]`: greedy-accumulate `## ` sections, hard-split oversized by line, char-slice a >limit line. Measures `len(str)`. | ADR-002 | S3 |
| Two-level split | Repo-boundary split first, line-split fallback for an oversized single section — guarantees every message ≤2000 chars. | ADR-002 | S3 |
| Discord host allowlist (validation) | `urlparse` scheme==https + host ∈ {discord.com, discordapp.com}, checked in `load_config`; else `ConfigError`. | ADR-003 | S3 |
| `webhook_env` | Optional `[output]` key naming the env var that holds the webhook URL; defaults to `DISCORD_WEBHOOK_URL`. | ADR-003 | S3 |
| 2xx = success | Any 2xx (incl. Discord's typical 204) is a successful POST — not only 200. | design gotcha | S3 |
