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
Discord delivery SHALL raise `DeliveryError` on any POST failure that is **not recovered by
retry**, which the CLI surfaces as a one-line `Error: <message>` on **stderr** and exits
non-zero (`1`). A **transient** failure — an HTTP `429`, any HTTP `5xx`, a connection/DNS error
(`httpx.RequestError`), or a request timeout (`httpx.TimeoutException`) — SHALL first be retried
with exponential backoff (see "Discord delivery retries transient failures with exponential
backoff"); `DeliveryError` is raised for such a failure only after the retry budget is exhausted.
A **non-transient** HTTP `4xx` other than `429` (`400`/`401`/`403`/`404`) SHALL remain fatal on
the first attempt with no retry. No raw Python stacktrace SHALL be shown. The webhook URL SHALL
NOT appear in the error message. The HTTPS request SHALL use an explicit timeout (default ~10
seconds) so a hung Discord endpoint cannot block the pipeline indefinitely; the timeout applies
to **each** attempt. In a multi-message push, if message _k_ fails fatally (after its own retry
budget is exhausted), delivery SHALL fail fatally at that point (messages already delivered are
accepted; there is no rollback).

> ACs: AC-V2-005-008 [CONFIRMED], AC-V2-005-009 [CONFIRMED], AC-V2-005-010 [CONFIRMED], AC-V2-005-011 [CONFIRMED], AC-001-010 [CONFIRMED]
> Business rules: BR-V2-005-004, BR-001-001, BR-001-002
> Risk: T1 (URL leak), T4 (DoS via hang — now bounded by max_retries)
> Decision: CLAR-3

#### Scenario: A non-transient HTTP error response surfaces a clean fatal error (AC-V2-005-008) [CONFIRMED]
- **WHEN** the webhook responds with a non-transient non-2xx status (e.g. 400, 401, 403, 404)
- **THEN** delivery raises `DeliveryError` after one attempt, the CLI prints `Error: <message>` on stderr, exits non-zero, and shows no Python stacktrace

#### Scenario: A network failure surfaces a clean fatal error after retries (AC-V2-005-009) [CONFIRMED]
- **WHEN** the POST fails due to a connection or DNS error on every attempt (retry budget exhausted)
- **THEN** delivery raises `DeliveryError`, the CLI exits non-zero with `Error: <message>` on stderr and no stacktrace

#### Scenario: A hung endpoint is bounded by a request timeout on every attempt (AC-V2-005-010) [CONFIRMED]
- **WHEN** the webhook does not respond within the configured request timeout on every attempt (retry budget exhausted)
- **THEN** each request is aborted at the timeout, delivery raises `DeliveryError` (timeout) after the retries, and the CLI exits non-zero without hanging

#### Scenario: The webhook URL never appears in the error output (AC-V2-005-011) [CONFIRMED]
- **WHEN** any Discord delivery error is surfaced on stderr (including one raised after retries are exhausted)
- **THEN** the error message does NOT contain the webhook URL (only a generic description of the failure)

#### Scenario: The final DeliveryError after retries never leaks the URL (AC-001-010) [CONFIRMED]
- **WHEN** all retry attempts fail (transient) and the adapter raises the final `DeliveryError`
- **THEN** its message is built from the HTTP status code or the exception *type name* only, and contains neither the webhook URL nor `str(exc)`/`repr(request)`

### Requirement: Discord delivery can POST the digest as Embeds when opted in
When `discord_use_embeds` is `true`, the `DiscordDelivery` adapter SHALL deliver the digest
as Discord **Embeds** — a JSON body of the shape
`{"embeds": [ {"title", "description", "color", "footer": {"text"}}, ... ]}` — instead of the
plain-text `{"content": ...}` body. The adapter SHALL build **one embed per item** grouped by
repo, preceded by **one header embed per repo**:
- **Header embed** (one per repo, emitted before that repo's item embeds): `color` =
  `0xFEE75C` (yellow), `title` = the repo name, `description` = `"{N} items — {lookback} ngày
  qua"` where `{N}` is the count of that repo's items shown.
- **Item embed** (one per surviving item): `title` = the item's title truncated to at most
  **256** Unicode code points (Discord's embed-title limit), `description` = the item's LLM
  summary, `color` = the item-type color (issue=`0xED4245`, release=`0x57F287`,
  discussion=`0x5865F2`, and a defined fallback color for any other type), `footer.text` =
  `"{repo} • {item_type} • OSS Pulse"`.
The adapter SHALL NOT import `osspulse.github`, `osspulse.summarizer`, or `osspulse.cache`
(the S5→S6 boundary is preserved; whether per-item data reaches the adapter via a widened
seam or in-adapter parsing is an architect decision, but no upstream *pipeline* module is
imported). When `discord_use_embeds` is `false` (the default) the adapter SHALL POST the
existing plain-text `{"content": ...}` body unchanged.

> ACs: AC-V4-001-001 [CONFIRMED], AC-V4-001-005 [CONFIRMED], AC-V4-002-009 [CONFIRMED], AC-V4-002-010 [CONFIRMED], AC-V4-002-011 [CONFIRMED]
> Business rules: BR-V4-001-001, BR-V4-001-002, BR-V4-002-006, BR-V4-002-007
> Integration: INT-V4-001-001, INT-V4-002-001
> Risk: T1 (URL leak — preserved)

#### Scenario: Embed mode emits a header embed plus one embed per item (AC-V4-002-009) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and a repo `owner/name` has 3 items shown
- **THEN** the request's `embeds` array contains, for that repo, a header embed first (`color = 0xFEE75C`, `title = "owner/name"`, `description = "3 items — {lookback} ngày qua"`) followed by 3 item embeds, each with `description` equal to that item's summary and `footer.text` equal to `"owner/name • {item_type} • OSS Pulse"`

#### Scenario: Item embed color is chosen by item type (AC-V4-002-010) [CONFIRMED]
- **WHEN** item embeds are built for an issue, a release, a discussion, and an item of an unrecognized type
- **THEN** their `color` values are `0xED4245`, `0x57F287`, `0x5865F2`, and the defined fallback color respectively, and no item is omitted from the embeds

#### Scenario: An over-length item title is truncated to 256 code points (AC-V4-002-011) [CONFIRMED]
- **WHEN** an item's title is longer than 256 Unicode code points in embed mode
- **THEN** the item embed's `title` is that title truncated to 256 code points (measured in code points, not UTF-8 bytes), and the untruncated title is not sent

#### Scenario: Embed mode is off by default and preserves plain-text delivery (AC-V4-001-005) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `false` (or the `[discord]` section is absent) and `deliver(content)` is called
- **THEN** the adapter POSTs the existing plain-text JSON body whose `content` field equals the (split) digest string, and sends NO `embeds` field — byte-identical to the pre-change behavior

#### Scenario: Embed mode POSTs a well-formed embeds body (AC-V4-001-001) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and the digest contains items for two repos that fit within all embed limits
- **THEN** the adapter issues an HTTPS POST whose JSON body has an `embeds` array containing a header embed and item embeds for each repo in document order, and returns normally on a 2xx response

### Requirement: Embed color is deterministic across runs
Each embed's `color` SHALL be a deterministic integer that is identical on every run and
across processes. Item embeds SHALL be colored from a **fixed item-type map** (issue =
`0xED4245`, release = `0x57F287`, discussion = `0x5865F2`, with a fixed fallback color for any
other type); header embeds SHALL use the fixed color `0xFEE75C`. Because colors are a fixed
lookup by item type (no hashing), the mapping is trivially stable. The adapter SHALL NOT use
Python's builtin `hash()` (process-salted via `PYTHONHASHSEED`) for any color selection.

> ACs: AC-V4-001-002 [CONFIRMED]
> Business rules: BR-V4-001-003, BR-V4-002-006
> Risk: Idempotency (project non-negotiable)

#### Scenario: The same item type yields the same color on repeated runs (AC-V4-001-002) [CONFIRMED]
- **WHEN** item embeds for the same item type are built in two separate adapter invocations (simulating two runs / two processes)
- **THEN** both carry the identical integer `color` from the fixed item-type map, and builtin `hash()` is not used

### Requirement: Embed payloads respect Discord's embed limits with plain-text fallback
Embed delivery SHALL respect Discord's limits: at most **10 embeds per request**, each embed
`description` at most **4096** Unicode characters (code points), and each embed `title` at
most **256** Unicode characters (code points, not UTF-8 bytes, matching the existing
content-limit convention). When the total number of embeds (header + item embeds) exceeds 10,
the adapter SHALL batch them into multiple sequential POST requests of ≤ 10 embeds each, in
document order. When a single embed `description` exceeds 4096 characters, the adapter SHALL
split it by line across multiple embeds so no `description` exceeds 4096 characters; an item
`title` exceeding 256 characters SHALL be truncated to 256. When an embed body cannot be
formed within these limits, or when there are no items to render (e.g. the "No new items"
digest), the adapter SHALL fall back to the existing plain-text `content` delivery path so the
run never fails purely due to embed formatting.

> ACs: AC-V4-001-003 [CONFIRMED], AC-V4-001-004 [CONFIRMED], AC-V4-001-006 [CONFIRMED], AC-V4-002-008 [CONFIRMED]
> Business rules: BR-V4-001-004, BR-V4-001-005, BR-V4-002-008
> Risk: DoS-via-hang (timeout preserved across batched requests)

#### Scenario: More than 10 embeds are batched into multiple requests (AC-V4-002-008) [CONFIRMED]
- **WHEN** a single repo has 10 items in embed mode (10 item embeds + 1 header embed = 11 embeds)
- **THEN** the adapter issues ≥ 2 sequential POST requests, each carrying ≤ 10 embeds, in document order, and returns normally when all responses are 2xx

#### Scenario: An over-length description is split by line across embeds (AC-V4-001-003) [CONFIRMED]
- **WHEN** one embed's `description` (an item summary) exceeds 4096 Unicode characters in embed mode
- **THEN** it is emitted as multiple embeds whose `description` fields are each ≤ 4096 characters (split on line boundaries), measured in code points

#### Scenario: More than 10 total embeds across repos are batched (AC-V4-001-004) [CONFIRMED]
- **WHEN** the digest yields 11+ total embeds (header + item embeds) in embed mode
- **THEN** the adapter issues ≥ 2 sequential POST requests, each carrying ≤ 10 embeds, in document order, and returns normally when all responses are 2xx

#### Scenario: A digest with no items falls back to plain text (AC-V4-001-006) [CONFIRMED]
- **WHEN** `discord_use_embeds` is `true` and `content` is the S5 "No new items in the last N days" document (no items / no `## ` section)
- **THEN** the adapter delivers it via the existing plain-text `content` path (one `{"content": ...}` POST), not as embeds, and returns normally on 2xx

### Requirement: Embed delivery failure stays fatal without leaking the webhook URL
An embed-mode POST failure that is not recovered by retry SHALL raise `DeliveryError`,
surfaced by the CLI as a one-line `Error: <message>` on stderr with a non-zero exit and no
Python stacktrace — identical to plain-text failure semantics (BR-V2-005-004). A failure is
"not recovered by retry" when it is a non-transient HTTP `4xx` other than `429`, or a transient
`429`/`5xx`/connection error/timeout whose retry budget has been exhausted. Transient embed-POST failures SHALL be retried with the same exponential-backoff
policy as plain-text POSTs before becoming fatal. The webhook URL SHALL NOT appear in any error
message. In a multi-request embed push, a failure on request _k_ (after its own retry budget) SHALL
be fatal at that point (earlier requests already delivered; no rollback), and the same explicit
request timeout SHALL bound every attempt of every request.

> ACs: AC-V4-001-007 [CONFIRMED], AC-001-008 [CONFIRMED]
> Business rules: BR-V4-001-006, BR-001-001
> Risk: T1 (URL leak — preserved), T4 (DoS via hang — preserved, bounded by max_retries)

#### Scenario: An embed POST error surfaces a clean fatal error without the URL (AC-V4-001-007) [CONFIRMED]
- **WHEN** an embed-mode POST responds with a non-transient non-2xx, or fails transiently on every attempt (retry budget exhausted)
- **THEN** the adapter raises `DeliveryError`, the CLI prints `Error: <message>` on stderr, exits non-zero, shows no stacktrace, and the message does NOT contain the webhook URL

#### Scenario: A transient embed POST is retried before failing (AC-001-008) [CONFIRMED]
- **WHEN** an embed batch POST returns HTTP `429` on the first attempt and HTTP `204` on the second
- **THEN** the embed POST is retried with backoff, `deliver` returns normally, and `sleep` is called once

### Requirement: Discord delivery retries transient failures with exponential backoff
The `DiscordDelivery` adapter SHALL retry a **transient** POST failure with exponential
backoff before giving up, so a momentary Discord rate-limit or server error does not abort
the run. The adapter's `__init__` SHALL accept three defaulted parameters — `max_retries: int`
(default `3`), `backoff_base: float` (default `1.0`), and `sleep: Callable[[float], None]`
(default `time.sleep`) — where `sleep` exists solely for test injection. A **transient**
failure SHALL be defined as an HTTP `429` response, any HTTP `5xx` response, an
`httpx.TimeoutException`, or an `httpx.RequestError` (connection/DNS/network). A
**non-transient** failure — any other non-2xx response, i.e. a `4xx` other than `429` such as
`400`/`401`/`403`/`404` — SHALL fail immediately with `DeliveryError` and SHALL NOT be retried
or slept on. On a transient failure the adapter SHALL make at most `max_retries + 1` total
attempts (one initial attempt plus up to `max_retries` retries); it SHALL wait
`backoff_base * 2 ** attempt` seconds before each retry, and when the failing response carries
a numeric `Retry-After` header it SHALL instead wait `max(Retry-After, backoff_base * 2 ** attempt)`
seconds. A missing, empty, or non-numeric `Retry-After` SHALL be ignored (fall back to the
pure backoff formula, never crash). The adapter SHALL call `sleep` only *between* attempts and
never after the final failed attempt. When all attempts are exhausted the adapter SHALL raise
`DeliveryError` whose message contains no webhook URL (AC-V2-005-011 preserved). Retry SHALL be
applied **per POST** (per split message and per embed batch); in a multi-message push each POST
has its own retry budget and already-delivered messages are NOT rolled back.

> ACs: AC-001-001 [CONFIRMED], AC-001-002 [CONFIRMED], AC-001-003 [CONFIRMED], AC-001-004 [CONFIRMED], AC-001-005 [ASSUMED], AC-001-006 [CONFIRMED], AC-001-007 [ASSUMED], AC-001-008 [CONFIRMED], AC-001-009 [ASSUMED], AC-001-011 [CONFIRMED]
> Business rules: BR-001-001, BR-001-002, BR-001-003, BR-001-004
> Risk: T1 (URL leak — preserved), T4 (DoS via hang — bounded by max_retries)

#### Scenario: A transient 5xx succeeds on retry (AC-001-001) [CONFIRMED]
- **WHEN** a POST returns HTTP `503` on the first attempt and HTTP `204` on the second, with `max_retries = 3`
- **THEN** `deliver` returns normally, exactly two POSTs are made, and the injected `sleep` is called exactly once (before the retry)

#### Scenario: Retries are exhausted then delivery fails (AC-001-002) [CONFIRMED]
- **WHEN** every attempt returns HTTP `500` with `max_retries = 3`
- **THEN** the adapter makes 4 total attempts, calls `sleep` 3 times, and finally raises `DeliveryError`

#### Scenario: A timeout on every attempt is retried then fatal (AC-001-003) [CONFIRMED]
- **WHEN** every attempt raises `httpx.TimeoutException` with `max_retries = 2`
- **THEN** the adapter makes 3 total attempts, calls `sleep` 2 times, and raises `DeliveryError` mentioning a timeout

#### Scenario: A non-transient 4xx fails immediately without retry (AC-001-004) [CONFIRMED]
- **WHEN** a POST returns HTTP `403` (or `400`/`401`/`404`)
- **THEN** the adapter raises `DeliveryError` after exactly one POST, and `sleep` is never called

#### Scenario: A network error is treated as transient (AC-001-005) [ASSUMED]
- **WHEN** a POST raises `httpx.RequestError` (e.g. `ConnectError`) on the first attempt and returns HTTP `204` on the second, with `max_retries = 3`
- **THEN** `deliver` returns normally, two POSTs are made, and `sleep` is called once

#### Scenario: Retry-After overrides the backoff wait when larger (AC-001-006) [CONFIRMED]
- **WHEN** a POST returns HTTP `429` with header `Retry-After: 5` and `backoff_base = 1.0` so the pure backoff wait for the first retry is `1.0`
- **THEN** the adapter waits `max(5, 1.0) = 5` seconds (the value passed to `sleep` is `5`) before the retry

#### Scenario: A missing or malformed Retry-After falls back to the backoff formula (AC-001-005b) [CONFIRMED]
- **WHEN** a POST returns HTTP `429` with no `Retry-After` header or a non-numeric one (e.g. `Retry-After: soon`) and `backoff_base = 1.0`
- **THEN** the adapter does not crash and waits `backoff_base * 2 ** attempt` seconds (the pure backoff formula) before the retry

#### Scenario: Backoff grows exponentially across retries (AC-001-007) [ASSUMED]
- **WHEN** three consecutive retries occur (all transient failures) with `backoff_base = 1.0`
- **THEN** the successive values passed to `sleep` are non-decreasing and follow `backoff_base * 2 ** attempt` (e.g. `1, 2, 4`), never a fixed constant

#### Scenario: Embed-mode POSTs use the same retry policy (AC-001-008) [CONFIRMED]
- **WHEN** an embed batch POST (`use_embeds = true`) returns HTTP `429` on the first attempt and HTTP `204` on the second
- **THEN** the embed POST is retried identically to a plain-text POST, `deliver` returns normally, and `sleep` is called once

#### Scenario: Per-message retry budget in a multi-message push (AC-001-009) [ASSUMED]
- **WHEN** a digest splits into 2 messages, message 1 succeeds on its first POST, and message 2 returns `503` once then `204`
- **THEN** message 1 is delivered once, message 2 is retried on its own budget and then delivered, and no already-delivered message is re-sent or rolled back

#### Scenario: max_retries = 0 reproduces single-attempt behavior (AC-001-011) [CONFIRMED]
- **WHEN** the adapter is constructed with `max_retries = 0` and a POST returns a transient HTTP `503`
- **THEN** the adapter makes exactly one POST, never calls `sleep`, and raises `DeliveryError` immediately

