## ADDED Requirements

### Requirement: Discord push delivery POSTs the digest to a webhook
The Delivery stage SHALL provide a `DiscordDelivery` adapter that, when
`output_destination = "discord"`, delivers the rendered Markdown digest to a Discord
webhook via HTTPS POST. `DiscordDelivery` SHALL implement the existing `Delivery`
Protocol (`deliver(self, content: str) -> None`) structurally — the port signature is
UNCHANGED. The adapter SHALL send the digest in the Discord `content` JSON field and
SHALL NOT import `osspulse.github`, `osspulse.summarizer`, `osspulse.cache`, or
`osspulse.render` (preserves AC-6-002).

> ACs: AC-V2-005-001 [CONFIRMED], AC-V2-005-002 [CONFIRMED], AC-V2-005-003 [CONFIRMED]
> Business rules: BR-V2-005-001
> Integration: INT-V2-005-001
> Decision: CLAR-1, CLAR-2

#### Scenario: Discord delivery POSTs the digest content over HTTPS (AC-V2-005-001) [CONFIRMED]
- **WHEN** `deliver(content)` is called on a `DiscordDelivery` configured with a valid webhook URL and `content` is ≤ 2000 characters
- **THEN** the adapter issues exactly one HTTPS POST to the webhook URL with a JSON body whose `content` field equals `content`, and returns normally on a 2xx response

#### Scenario: DiscordDelivery implements the Delivery port without changing it (AC-V2-005-002) [CONFIRMED]
- **WHEN** the `Delivery` Protocol is inspected
- **THEN** its method is still `deliver(self, content: str) -> None` (unchanged) and `DiscordDelivery` satisfies it structurally, exactly like `FileDelivery` and `StdoutDelivery`

#### Scenario: DiscordDelivery does not couple to upstream pipeline modules (AC-V2-005-003) [CONFIRMED]
- **WHEN** the `osspulse.delivery.discord_delivery` module is imported
- **THEN** it does NOT import `osspulse.github`, `osspulse.summarizer`, `osspulse.cache`, or `osspulse.render` (verified by static import inspection)

### Requirement: A digest exceeding 2000 characters is split into multiple messages
When the digest exceeds Discord's 2000-character `content` limit, Discord delivery SHALL
split it into multiple messages, each ≤ 2000 characters, and POST them **sequentially**
in order. Splitting SHALL occur first at repo-section (`## `) boundaries; if a single
section still exceeds 2000 characters, that section SHALL be hard-split by line so that
no message exceeds 2000 characters. The 2000-character limit SHALL be measured in
Unicode characters (code points), not UTF-8 bytes, to match Discord's own counting.

> ACs: AC-V2-005-004 [CONFIRMED], AC-V2-005-005 [CONFIRMED], AC-V2-005-006 [CONFIRMED], AC-V2-005-007 [CONFIRMED]
> Business rules: BR-V2-005-002, BR-V2-005-003
> Decision: CLAR-4, CLAR-5

#### Scenario: A digest at or under 2000 chars is sent as one message (AC-V2-005-004) [CONFIRMED]
- **WHEN** the digest is exactly 2000 characters or fewer
- **THEN** exactly one POST is made and no splitting occurs

#### Scenario: A digest over 2000 chars is split at repo boundaries into ordered messages (AC-V2-005-005) [CONFIRMED]
- **WHEN** the digest is 2001+ characters and contains multiple `## ` repo sections
- **THEN** it is split into ≥ 2 messages at `## ` boundaries, each message is ≤ 2000 characters, and the messages are POSTed sequentially in document order

#### Scenario: A single repo section over 2000 chars is hard-split by line (AC-V2-005-006) [CONFIRMED]
- **WHEN** one `## ` repo section by itself exceeds 2000 characters
- **THEN** that section is further split on line boundaries so that every resulting message is ≤ 2000 characters (no message exceeds the limit)

#### Scenario: The 2000 limit counts Unicode characters, not bytes (AC-V2-005-007) [CONFIRMED]
- **WHEN** the digest contains multi-byte non-ASCII text (e.g. "Khác", emoji) with a character count ≤ 2000 but a UTF-8 byte count > 2000
- **THEN** it is sent as a single message (the limit is measured in characters, matching Discord), not incorrectly split

### Requirement: Discord push failure is fatal with a clear CLI error
Discord delivery SHALL raise `DeliveryError` on any POST failure, which the CLI surfaces
as a one-line `Error: <message>` on **stderr** and exits non-zero (`1`). This applies when
a Discord POST fails with an HTTP 4xx/5xx response, a connection/DNS error, or by exceeding
the request timeout. No raw Python stacktrace
SHALL be shown. The webhook URL SHALL NOT appear in the error message. The HTTPS request
SHALL use an explicit timeout (default ~10 seconds) so a hung Discord endpoint cannot block
the pipeline indefinitely. In a multi-message push, if message _k_ fails, delivery SHALL fail
fatally at that point (messages already delivered are accepted; there is no rollback).

> ACs: AC-V2-005-008 [CONFIRMED], AC-V2-005-009 [CONFIRMED], AC-V2-005-010 [CONFIRMED], AC-V2-005-011 [CONFIRMED]
> Business rules: BR-V2-005-004
> Risk: T1 (URL leak), T4 (DoS via hang)
> Decision: CLAR-3

#### Scenario: An HTTP error response surfaces a clean fatal error (AC-V2-005-008) [CONFIRMED]
- **WHEN** the webhook responds with a non-2xx status (e.g. 404, 429, 500)
- **THEN** delivery raises `DeliveryError`, the CLI prints `Error: <message>` on stderr, exits non-zero, and shows no Python stacktrace

#### Scenario: A network failure surfaces a clean fatal error (AC-V2-005-009) [CONFIRMED]
- **WHEN** the POST fails due to a connection or DNS error
- **THEN** delivery raises `DeliveryError`, the CLI exits non-zero with `Error: <message>` on stderr and no stacktrace

#### Scenario: A hung endpoint is bounded by a request timeout (AC-V2-005-010) [CONFIRMED]
- **WHEN** the webhook does not respond within the configured request timeout
- **THEN** the request is aborted, delivery raises `DeliveryError` (timeout), and the CLI exits non-zero without hanging

#### Scenario: The webhook URL never appears in the error output (AC-V2-005-011) [CONFIRMED]
- **WHEN** any Discord delivery error is surfaced on stderr
- **THEN** the error message does NOT contain the webhook URL (only a generic description of the failure)

## MODIFIED Requirements

### Requirement: Destination selection is config-driven
The destination SHALL be selected from a `[output]` config section:
`destination` (one of `"file"` | `"stdout"` | `"discord"`, default `"file"`) and
`output_path` (string, default `"./digest.md"`, used only when `destination = "file"`).
When `destination = "discord"`, the webhook URL SHALL be read from an environment
variable — the variable name defaults to `DISCORD_WEBHOOK_URL` and MAY be overridden by
an optional `[output] webhook_env` key — and SHALL NOT be read from the config file
itself. At load time `config.py` SHALL validate the resolved webhook URL is present,
non-empty, uses the `https` scheme, and has a host in the Discord allowlist
(`discord.com`, `discordapp.com`); any failure SHALL raise `ConfigError` before the
pipeline runs (fail fast, not at delivery time). The `Config` dataclass SHALL gain the
fields needed to carry the resolved webhook URL and its source env-var name. All existing
`file` / `stdout` validation behavior is unchanged.

> ACs: AC-6-010 [CONFIRMED], AC-6-011 [CONFIRMED], AC-6-012 [CONFIRMED], AC-6-013 [CONFIRMED], AC-V2-005-012 [CONFIRMED], AC-V2-005-013 [CONFIRMED], AC-V2-005-014 [CONFIRMED], AC-V2-005-015 [CONFIRMED]
> Business rules: BR-6-007, BR-6-008, BR-V2-005-005
> Integration: INT-6-002, INT-V2-005-001
> Risk: T2 (mis-route), T3 (SSRF)

#### Scenario: Default destination is a file at ./digest.md when [output] is absent (AC-6-010) [CONFIRMED]
- **WHEN** a config file has no `[output]` section
- **THEN** `load_config` returns a `Config` with `output_destination = "file"` and `output_path = "./digest.md"`

#### Scenario: A configured file destination and path are loaded (AC-6-011) [CONFIRMED]
- **WHEN** the config has `[output]` with `destination = "file"` and `output_path = "./out/today.md"`
- **THEN** `load_config` returns a `Config` with `output_destination = "file"` and `output_path = "./out/today.md"`

#### Scenario: An invalid destination value fails config validation (AC-6-012) [CONFIRMED]
- **WHEN** the config has `[output]` with `destination = "ftp"` (any value other than `"file"`/`"stdout"`/`"discord"`)
- **THEN** `load_config` raises `ConfigError` with a clear message, before the pipeline runs

#### Scenario: An empty output_path with file destination fails validation (AC-6-013) [CONFIRMED]
- **WHEN** the config has `destination = "file"` and `output_path = ""`
- **THEN** `load_config` raises `ConfigError` with a clear message (does not default silently)

#### Scenario: A discord destination with the webhook env var set loads successfully (AC-V2-005-012) [CONFIRMED]
- **WHEN** the config has `destination = "discord"` and the environment provides `DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/123/abc"`
- **THEN** `load_config` returns a `Config` carrying the resolved webhook URL, and `output_path` is ignored

#### Scenario: A discord destination with no webhook env var fails validation (AC-V2-005-013) [CONFIRMED]
- **WHEN** the config has `destination = "discord"` and the webhook env var is unset or empty
- **THEN** `load_config` raises `ConfigError` with a clear message, before the pipeline runs

#### Scenario: A non-https webhook URL fails validation (AC-V2-005-014) [CONFIRMED]
- **WHEN** `destination = "discord"` and the webhook env var is `http://discord.com/api/webhooks/123/abc` (not https)
- **THEN** `load_config` raises `ConfigError` (scheme must be https)

#### Scenario: A non-Discord webhook host fails validation (AC-V2-005-015) [CONFIRMED]
- **WHEN** `destination = "discord"` and the webhook env var host is not `discord.com`/`discordapp.com` (e.g. `https://evil.example/x`)
- **THEN** `load_config` raises `ConfigError` (SSRF / mis-route guard — host must be a Discord domain)

## Business Rules
- BR-V2-005-001: `DiscordDelivery` implements the `Delivery` port structurally and consumes the rendered Markdown **string** only — it never imports upstream pipeline modules (extends BR-6-001/BR-6-002 to the Discord adapter).
- BR-V2-005-002: The 2000-character Discord `content` limit is measured in **Unicode characters** (code points), never UTF-8 bytes.
- BR-V2-005-003: A multi-message push splits at repo (`## `) boundaries first; a single section still over the limit is hard-split by line so **no** message ever exceeds 2000 characters. Messages are POSTed sequentially in document order.
- BR-V2-005-004: A Discord push failure (HTTP 4xx/5xx, network/DNS error, or timeout) is **fatal** — `DeliveryError` → `Error:` on stderr → exit 1. No retry in V2. The webhook URL is never present in any error message, log line, or run-summary.
- BR-V2-005-005: When `destination = "discord"`, the webhook URL is resolved from an environment variable (default `DISCORD_WEBHOOK_URL`, overridable via `[output] webhook_env`) and is validated at config-load time to be a non-empty `https` URL whose host is in the Discord allowlist (`discord.com`, `discordapp.com`); the URL is never read from or stored in the config file.

## Integration Points
- INT-V2-005-001: S7 CLI/pipeline selects `DiscordDelivery(webhook_url, timeout=...)` when `config.output_destination == "discord"` and calls `.deliver(rendered_string)` — the same string handoff seam as INT-6-001 (renderer `render(...) -> str` → delivery). The webhook URL is carried on `Config` (resolved from env at load), not imported by `delivery/`.
