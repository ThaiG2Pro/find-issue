# delivery Specification

## Purpose
TBD - created by archiving change delivery-6. Update Purpose after archive.
## Requirements
### Requirement: Delivery consumes the rendered Markdown string only
The Delivery stage SHALL expose a `Delivery` port whose method
`deliver(self, content: str) -> None` accepts the **rendered Markdown digest string**
produced by S5 (`osspulse.render.renderer.render(...) -> str`). The `Delivery` Protocol
in `osspulse.ports` SHALL be changed from `send(self, digest: Digest) -> None` to
`deliver(self, content: str) -> None`. Delivery SHALL NOT import from `osspulse.github`,
`osspulse.summarizer`, `osspulse.cache`, or `osspulse.render`, and SHALL NOT depend on the
`RawItem`, `SummarizedItem`, or `Digest` domain models — it operates purely on the string.

> ACs: AC-6-001 [CONFIRMED], AC-6-002 [CONFIRMED], AC-6-003 [CONFIRMED]
> Business rules: BR-6-001, BR-6-002
> Integration: INT-6-001
> Decision: D-1 (port signature change)

#### Scenario: The Delivery port accepts a Markdown string (AC-6-001) [CONFIRMED]
- **WHEN** a `Delivery` adapter's `deliver(content)` is called with a non-empty Markdown string
- **THEN** the adapter delivers exactly that string to its destination with no transformation of the content (byte-preserving, aside from a single optional trailing newline)

#### Scenario: Delivery does not couple to upstream pipeline modules (AC-6-002) [CONFIRMED]
- **WHEN** the `osspulse.delivery` package is imported
- **THEN** it does NOT import `osspulse.github`, `osspulse.summarizer`, `osspulse.cache`, or `osspulse.render` (verified by static import inspection)

#### Scenario: Delivery operates on a string, not a Digest model (AC-6-003) [CONFIRMED]
- **WHEN** the `Delivery` Protocol is inspected
- **THEN** its method is `deliver(self, content: str) -> None` and it does not reference `Digest`, `SummarizedItem`, or `RawItem`

### Requirement: File delivery writes the digest atomically
When the configured destination is `file`, the Delivery stage SHALL write `content` to the
configured `output_path` **atomically**: write to a temporary file in the **same directory**
as the target, flush + `fsync` it, then `os.replace` (atomic rename) it onto the target path.
A crash or error at any point SHALL leave either the previous target file intact or the new
complete file in place — **never a partial or corrupt file**. The file SHALL be encoded as
**UTF-8**.

> ACs: AC-6-004 [CONFIRMED], AC-6-005 [CONFIRMED], AC-6-006 [CONFIRMED]
> Business rules: BR-6-003, BR-6-005
> Risk: RF-1 (partial-write corruption)

#### Scenario: A successful file delivery writes the exact digest as UTF-8 (AC-6-004) [CONFIRMED]
- **WHEN** `deliver(content)` is called for a writable `output_path` with `destination = "file"`
- **THEN** after the call the file at `output_path` exists and its UTF-8-decoded contents equal `content` (including non-ASCII labels such as "Khác")

#### Scenario: File write is atomic via temp-then-replace (AC-6-005) [CONFIRMED]
- **WHEN** file delivery writes the digest
- **THEN** it first writes a temporary file in the same directory as `output_path`, then performs an atomic `os.replace` onto `output_path` — at no observable point does `output_path` contain a partially-written file

#### Scenario: A write failure never corrupts an existing target file (AC-6-006) [CONFIRMED]
- **WHEN** an existing `output_path` file is present and the atomic replace step fails (e.g. simulated `os.replace` error)
- **THEN** the original `output_path` file is left unchanged (intact, complete) and the failure is surfaced as an error (no partial overwrite)

### Requirement: stdout delivery writes the digest to standard output
When the configured destination is `stdout`, the Delivery stage SHALL write `content` to
`sys.stdout` (UTF-8), followed by exactly one trailing newline, and SHALL write **nothing
else** to stdout (diagnostic/log lines go to stderr). No file SHALL be written in stdout mode,
and `output_path` SHALL be ignored.

> ACs: AC-6-007 [CONFIRMED], AC-6-008 [CONFIRMED], AC-6-009 [ASSUMED]
> Business rules: BR-6-004, BR-6-006

#### Scenario: stdout delivery writes the digest to standard output (AC-6-007) [CONFIRMED]
- **WHEN** `deliver(content)` is called with `destination = "stdout"`
- **THEN** `content` is written to `sys.stdout` and no file is created at `output_path`

#### Scenario: stdout output is clean and pipeable (AC-6-008) [CONFIRMED]
- **WHEN** stdout delivery runs
- **THEN** stdout contains `content` plus a single trailing newline and no log/diagnostic lines (those go to stderr), so the output is safe to redirect/pipe

#### Scenario: A broken/closed stdout pipe is handled gracefully (AC-6-009) [ASSUMED]
- **WHEN** stdout is a closed pipe (e.g. the run is piped into a consumer that exits early, raising `BrokenPipeError`)
- **THEN** the delivery does not emit a Python stacktrace to the user; it exits without an unhandled exception

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

### Requirement: Unwritable file destinations surface a clear CLI error
The Delivery stage SHALL surface any file-write failure as a one-line `Error: <message>` on
**stderr** and SHALL exit the run non-zero (`1`). This applies when `destination = "file"` and
the digest cannot be written — for example a missing parent directory, permission denied, the
target being a directory, or the disk being full. No raw Python stacktrace SHALL be shown for
these handled errors. A missing parent directory SHALL be treated as an error — Delivery SHALL
NOT silently create it.

> ACs: AC-6-014 [CONFIRMED], AC-6-015 [ASSUMED], AC-6-016 [CONFIRMED], AC-6-017 [CONFIRMED]
> Business rules: BR-6-009, BR-6-010
> Risk: RF-2 (silent data loss on unwritable path)

#### Scenario: Missing parent directory is an error, not auto-created (AC-6-014) [CONFIRMED]
- **WHEN** `output_path = "./nope/digest.md"` and `./nope/` does not exist
- **THEN** delivery surfaces `Error: <message>` on stderr, exits non-zero, and does NOT create `./nope/`

#### Scenario: A missing parent directory message names the path (AC-6-015) [ASSUMED]
- **WHEN** delivery fails because the parent directory is missing
- **THEN** the stderr message includes the offending `output_path` so the operator can fix it

#### Scenario: Permission-denied target surfaces a clean error (AC-6-016) [CONFIRMED]
- **WHEN** `output_path` is in a directory the process cannot write to (permission denied)
- **THEN** delivery surfaces `Error: <message>` on stderr, exits non-zero, and shows no Python stacktrace

#### Scenario: Target path that is an existing directory surfaces a clean error (AC-6-017) [CONFIRMED]
- **WHEN** `output_path` points to an existing directory (not a file)
- **THEN** delivery surfaces `Error: <message>` on stderr and exits non-zero without a stacktrace

### Requirement: Delivery is idempotent and never appends
Re-running delivery with the same `content` and `output_path` SHALL overwrite the target
file deterministically, producing a byte-identical result to a fresh write. Delivery SHALL
NEVER append to an existing file, SHALL NEVER produce duplicate output, and SHALL deliver the
S5 "No new items" document verbatim (S5 guarantees a non-empty string; Delivery does not
special-case or suppress it).

> ACs: AC-6-018 [CONFIRMED], AC-6-019 [CONFIRMED], AC-6-020 [ASSUMED]
> Business rules: BR-6-011, BR-6-012

#### Scenario: Re-delivering the same content overwrites deterministically (AC-6-018) [CONFIRMED]
- **WHEN** `deliver(content)` is called twice for the same `output_path` with the same `content`
- **THEN** the file after the second call is byte-identical to after the first (overwrite, not append); the file is not duplicated or grown

#### Scenario: Delivering different content replaces the previous file (AC-6-019) [CONFIRMED]
- **WHEN** `deliver(content_a)` then `deliver(content_b)` are called for the same `output_path`
- **THEN** the file contains exactly `content_b` (the previous `content_a` is fully replaced, not appended to)

#### Scenario: A "No new items" digest is delivered verbatim (AC-6-020) [ASSUMED]
- **WHEN** `content` is the S5 "No new items in the last N days" document (non-empty, no repo sections)
- **THEN** delivery writes that document as-is to the destination (file written / stdout printed); it is not suppressed and no empty file is produced

---

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

