## ADDED Requirements

### Requirement: Discord delivery can POST the digest as Embeds when opted in
When `discord_use_embeds` is `true`, the `DiscordDelivery` adapter SHALL deliver the
rendered Markdown digest as Discord **Embeds** — a JSON body of the shape
`{"embeds": [ {"title", "description", "color", "footer": {"text"}}, ... ]}` — instead of
the plain-text `{"content": ...}` body. The adapter SHALL build **one embed per repo
section**, splitting the rendered digest at `## ` boundaries exactly as the plain-text
splitter does: each embed's `title` SHALL be the repo section header line with the leading
`## ` removed (e.g. `vercel/next.js — 1 ngày qua`) and each embed's `description` SHALL be
that section's body. The port signature SHALL remain `deliver(self, content: str) -> None`
(UNCHANGED) and the adapter SHALL NOT import `osspulse.github`, `osspulse.summarizer`,
`osspulse.cache`, or `osspulse.render` (preserves AC-6-002 / AC-V2-005-003). When
`discord_use_embeds` is `false` (the default) the adapter SHALL POST the existing
plain-text `{"content": ...}` body unchanged.

> ACs: AC-V4-001-001 [CONFIRMED], AC-V4-001-005 [CONFIRMED]
> Business rules: BR-V4-001-001, BR-V4-001-002
> Integration: INT-V4-001-001
> Risk: T1 (URL leak — preserved)

#### Scenario: Embed mode POSTs one embed per repo section (AC-V4-001-001) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and `deliver(content)` is called with a digest containing two `## ` repo sections that fit within all embed limits
- **THEN** the adapter issues an HTTPS POST whose JSON body has an `embeds` array of two objects, where each object's `title` equals its repo section header text without the leading `## ` and each `description` equals that section's body, and returns normally on a 2xx response

#### Scenario: Embed mode is off by default and preserves plain-text delivery (AC-V4-001-005) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `false` (or the `[discord]` section is absent) and `deliver(content)` is called
- **THEN** the adapter POSTs the existing plain-text JSON body whose `content` field equals the (split) digest string, and sends NO `embeds` field — byte-identical to the pre-change behavior

### Requirement: Embed color is deterministic across runs
Each embed's `color` SHALL be an integer selected from a fixed palette of 5–6 colors by a
**stable** hash of the repo slug (`hashlib`-based, e.g. `int(md5(slug)) % len(palette)`),
so that a given repo maps to the SAME color on every run and across processes. The adapter
SHALL NOT use Python's builtin `hash()` for color selection (it is process-salted via
`PYTHONHASHSEED` and would break determinism, violating the project idempotency principle).

> ACs: AC-V4-001-002 [CONFIRMED]
> Business rules: BR-V4-001-003
> Risk: Idempotency (project non-negotiable)

#### Scenario: The same repo yields the same color on repeated runs (AC-V4-001-002) [CONFIRMED]
- **WHEN** the embed for repo `owner/name` is built in two separate adapter invocations (simulating two runs / two processes)
- **THEN** both embeds carry the identical integer `color` value, and that value is a member of the fixed palette

#### Scenario: Different repos are colored from the palette deterministically (AC-V4-001-002b) [CONFIRMED]
- **WHEN** embeds are built for several distinct repo slugs
- **THEN** each color is drawn from the fixed palette by a stable hash of the slug (builtin `hash()` is NOT used), so the mapping is reproducible

### Requirement: Embed payloads respect Discord's embed limits with plain-text fallback
Embed delivery SHALL respect Discord's limits: at most **10 embeds per request** and each
embed `description` at most **4096 Unicode characters** (code points, not UTF-8 bytes,
matching the existing content-limit convention). When more than 10 repo sections exist, the
adapter SHALL batch embeds into multiple sequential POST requests of ≤ 10 embeds each, in
document order. When a single repo section's body exceeds 4096 characters, the adapter SHALL
split that section's `description` by line across multiple embeds so no `description`
exceeds 4096 characters. When an embed body cannot be formed within these limits, or when
the digest contains no `## ` repo section (e.g. the "No new items" document), the adapter
SHALL fall back to the existing plain-text `content` delivery path so the run never fails
purely due to embed formatting.

> ACs: AC-V4-001-003 [CONFIRMED], AC-V4-001-004 [CONFIRMED], AC-V4-001-006 [CONFIRMED]
> Business rules: BR-V4-001-004, BR-V4-001-005
> Risk: DoS-via-hang (timeout preserved across batched requests)

#### Scenario: An over-length section description is split by line across embeds (AC-V4-001-003) [CONFIRMED]
- **WHEN** one repo section body exceeds 4096 Unicode characters in embed mode
- **THEN** that section is emitted as multiple embeds whose `description` fields are each ≤ 4096 characters (split on line boundaries), and no `description` exceeds the limit; the limit is measured in code points, so a body ≤ 4096 chars but > 4096 UTF-8 bytes is NOT split

#### Scenario: More than 10 repo sections are batched into multiple requests (AC-V4-001-004) [CONFIRMED]
- **WHEN** the digest contains 11+ `## ` repo sections in embed mode
- **THEN** the adapter issues ≥ 2 sequential POST requests, each carrying ≤ 10 embeds, in document order, and returns normally when all responses are 2xx

#### Scenario: A digest with no repo section falls back to plain text (AC-V4-001-006) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and `content` is the S5 "No new items in the last N days" document (no `## ` section)
- **THEN** the adapter delivers it via the existing plain-text `content` path (one `{"content": ...}` POST), not as an embed, and returns normally on 2xx

### Requirement: Embed delivery failure stays fatal without leaking the webhook URL
A POST failure in embed mode (HTTP 4xx/5xx, connection/DNS error, or timeout) SHALL raise
`DeliveryError`, surfaced by the CLI as a one-line `Error: <message>` on stderr with a
non-zero exit and no Python stacktrace — identical to plain-text failure semantics
(BR-V2-005-004). The webhook URL SHALL NOT appear in any error message. In a multi-request
embed push, a failure on request _k_ SHALL be fatal at that point (earlier requests already
delivered; no rollback), and the same explicit request timeout SHALL bound every request.

> ACs: AC-V4-001-007 [CONFIRMED]
> Business rules: BR-V4-001-006
> Risk: T1 (URL leak — preserved), T4 (DoS via hang — preserved)

#### Scenario: An embed POST error surfaces a clean fatal error without the URL (AC-V4-001-007) [CONFIRMED]
- **WHEN** an embed-mode POST responds non-2xx, fails to connect, or exceeds the timeout
- **THEN** the adapter raises `DeliveryError`, the CLI prints `Error: <message>` on stderr, exits non-zero, shows no stacktrace, and the message does NOT contain the webhook URL

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
pipeline runs (fail fast, not at delivery time). An optional `[discord]` config section
MAY provide `use_embeds` (boolean, default `false`); it SHALL be validated fail-fast as a
strict boolean (a non-boolean value such as `"yes"` or `1` SHALL raise `ConfigError` at
load), and its resolved value SHALL be carried on `Config` as `discord_use_embeds`. The
`Config` dataclass SHALL gain the fields needed to carry the resolved webhook URL, its
source env-var name, and `discord_use_embeds`. All existing `file` / `stdout` validation
behavior is unchanged.

> ACs: AC-6-010 [CONFIRMED], AC-6-011 [CONFIRMED], AC-6-012 [CONFIRMED], AC-6-013 [CONFIRMED], AC-V2-005-012 [CONFIRMED], AC-V2-005-013 [CONFIRMED], AC-V2-005-014 [CONFIRMED], AC-V2-005-015 [CONFIRMED], AC-V4-001-008 [CONFIRMED]
> Business rules: BR-6-007, BR-6-008, BR-V2-005-005, BR-V4-001-007
> Integration: INT-6-002, INT-V2-005-001, INT-V4-001-001
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

#### Scenario: use_embeds defaults to false when the [discord] section is absent (AC-V4-001-008a) [CONFIRMED]
- **WHEN** a config file has no `[discord]` section (or no `use_embeds` key)
- **THEN** `load_config` returns a `Config` with `discord_use_embeds = false`

#### Scenario: A non-boolean use_embeds fails config validation (AC-V4-001-008) [CONFIRMED]
- **WHEN** the config has `[discord]` with `use_embeds = "yes"` (or any non-boolean such as `1`)
- **THEN** `load_config` raises `ConfigError` with a clear message, before the pipeline runs (strict `type(v) is not bool` check, mirroring `delta.enabled`)

## Business Rules
- BR-V4-001-001: In embed mode the payload is `{"embeds": [...]}`; in plain-text mode it stays `{"content": ...}`. The mode is chosen solely by `Config.discord_use_embeds`; no other behavior (destination selection, URL resolution, error handling) changes.
- BR-V4-001-002: Embed conversion is derived entirely from the rendered Markdown string inside the adapter — `DiscordDelivery` never imports `osspulse.render` or any upstream module (extends BR-V2-005-001). Embed `title` = repo header minus `## `; `description` = section body; `footer.text` = `OSS Pulse • {timestamp}`.
- BR-V4-001-003: Embed `color` is chosen from a fixed 5–6 color palette by a STABLE hash (`hashlib`) of the repo slug — never Python's builtin `hash()` (process-salted). The same repo maps to the same color on every run/process (idempotency).
- BR-V4-001-004: Embed limits are enforced in Unicode code points: ≤ 10 embeds per request (batch into sequential requests when exceeded) and ≤ 4096 chars per `description` (split by line when exceeded). Never send an embed exceeding these limits.
- BR-V4-001-005: When an embed body cannot be formed within limits, or the digest has no `## ` section, the adapter falls back to the existing plain-text `content` path; embed formatting alone never causes a run failure.
- BR-V4-001-006: An embed-mode POST failure (4xx/5xx, network, timeout) is fatal exactly like plain text (`DeliveryError` → `Error:` on stderr → exit 1), the webhook URL never appears in any message, and every request is bounded by the existing explicit timeout (extends BR-V2-005-004).
- BR-V4-001-007: `[discord] use_embeds` is validated fail-fast as a strict boolean at config load (`type(v) is not bool`), defaulting to `false`; a non-boolean raises `ConfigError` before the pipeline runs (mirrors the `delta.enabled` bool-trap guard).

## Integration Points
- INT-V4-001-001: S7 CLI/pipeline constructs `DiscordDelivery(webhook_url, timeout=..., use_embeds=config.discord_use_embeds)` when `config.output_destination == "discord"` and calls `.deliver(rendered_string)` — the same string handoff seam as INT-V2-005-001. The `use_embeds` flag is carried on `Config` (parsed at load), not imported by `delivery/`.
