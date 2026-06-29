# Delivery Specification (delta — change delivery-6)

## ADDED Requirements

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
`destination` (one of `"file"` | `"stdout"`, default `"file"`) and `output_path` (string,
default `"./digest.md"`, used only when `destination = "file"`). The `Config` dataclass SHALL
gain `output_destination` and `output_path` fields, and `config.py` SHALL parse and validate
the `[output]` section at load time (fail fast on invalid values — not at delivery time).

> ACs: AC-6-010 [CONFIRMED], AC-6-011 [ASSUMED], AC-6-012 [CONFIRMED], AC-6-013 [ASSUMED]
> Business rules: BR-6-007, BR-6-008
> Integration: INT-6-002

#### Scenario: Default destination is a file at ./digest.md when [output] is absent (AC-6-010) [CONFIRMED]
- **WHEN** a config file has no `[output]` section
- **THEN** `load_config` returns a `Config` with `output_destination = "file"` and `output_path = "./digest.md"`

#### Scenario: A configured file destination and path are loaded (AC-6-011) [ASSUMED]
- **WHEN** the config has `[output]` with `destination = "file"` and `output_path = "./out/today.md"`
- **THEN** `load_config` returns a `Config` with `output_destination = "file"` and `output_path = "./out/today.md"`

#### Scenario: An invalid destination value fails config validation (AC-6-012) [CONFIRMED]
- **WHEN** the config has `[output]` with `destination = "email"` (or any value other than `"file"`/`"stdout"`)
- **THEN** `load_config` raises `ConfigError` with a clear message, before the pipeline runs

#### Scenario: An empty output_path with file destination fails validation (AC-6-013) [ASSUMED]
- **WHEN** the config has `destination = "file"` and `output_path = ""`
- **THEN** `load_config` raises `ConfigError` with a clear message (does not default silently)

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

## Business Rules
- BR-6-001: Delivery consumes the rendered Markdown **string** only — never the `Digest`/`SummarizedItem`/`RawItem` models.
- BR-6-002: Delivery imports no upstream pipeline modules (`github`, `summarizer`, `cache`, `render`) — decoupled sink.
- BR-6-003: File writes are atomic: temp file in target dir → `fsync` → `os.replace`.
- BR-6-004: stdout mode writes only the digest (+ one trailing newline) to stdout; diagnostics go to stderr.
- BR-6-005: All output is UTF-8 encoded (digest contains Vietnamese/non-ASCII text).
- BR-6-006: In stdout mode, `output_path` is ignored and no file is written.
- BR-6-007: Destination is config-driven via `[output]`: `destination ∈ {file, stdout}` (default `file`), `output_path` (default `./digest.md`).
- BR-6-008: Config validation is fail-fast at load time — invalid `[output]` raises `ConfigError` before the pipeline runs.
- BR-6-009: Unwritable file destinations surface `Error: <message>` on stderr + non-zero exit; no stacktrace for handled errors.
- BR-6-010: A missing parent directory is an error; Delivery does NOT auto-create it.
- BR-6-011: Delivery overwrites deterministically and never appends (idempotent re-run).
- BR-6-012: Delivery delivers the S5 "No new items" doc verbatim; it never produces an empty/suppressed output.

## Integration Points
- INT-6-001: S5 Renderer (`render(...) -> str`) → S6 Delivery (`deliver(content: str)`) — string handoff via pipeline.
- INT-6-002: S1 Config (`Config.output_destination`, `Config.output_path`) → S6 Delivery (selects file vs stdout + path).
- INT-6-003: S7 CLI/pipeline wiring — `cli.py`/`pipeline.py` construct the chosen `Delivery` adapter from config and call `deliver(rendered_string)`.

## Error States
| Condition | Surfacing | Exit |
|-----------|-----------|------|
| Invalid `[output].destination` value | `ConfigError` → `Error:` on stderr (at load) | 1 |
| Empty `output_path` with file destination | `ConfigError` → `Error:` on stderr (at load) | 1 |
| Missing parent directory | `Error: <message>` on stderr | 1 |
| Permission denied on target | `Error: <message>` on stderr | 1 |
| Target is an existing directory | `Error: <message>` on stderr | 1 |
| Disk full (ENOSPC) | `Error: <message>` on stderr; existing target intact | 1 |
| Broken stdout pipe | handled (no stacktrace); clean exit | 0/non-zero per pipe |

## Non-functional Requirements
- **Security/Privacy**: no secrets, tokens, or PII in the delivery path or any log line. Only egress is the local filesystem path / stdout the operator configured. No network.
- **Dependencies**: stdlib only (`os`, `pathlib`, `sys`) — no new external dependency in V1.
- **Determinism**: byte-identical output for identical input (idempotency).

## Figma Design
Figma: N/A (CLI tool, no UI).

---

## Early Risk Flags
Lightweight risk scan after S2 (cost 1×). No 🔴 Critical risks block SPEC LOCK; the items
below are 🟡/🟢 and are already covered by ACs.

- **RF-1 — Partial-write corruption (🟡 Medium, mitigated).** A crash mid-write could leave a
  truncated/corrupt digest file. Mitigated by atomic temp-then-`os.replace` (AC-6-005, AC-6-006,
  BR-6-003). Watch: the temp file MUST be in the **same directory/filesystem** as the target, or
  `os.replace` is not atomic.
- **RF-2 — Silent data loss on unwritable path (🟡 Medium, mitigated).** If a write failure were
  swallowed, the operator would believe the digest was saved. Mitigated by fail-loud error contract
  (AC-6-014..017, BR-6-009): always surface `Error:` + non-zero exit.
- **RF-3 — Encoding corruption of non-ASCII content (🟢 Low, mitigated).** The digest contains
  Vietnamese ("Khác") and possibly emoji/CJK titles. Writing with the platform default encoding
  (e.g. cp1252 on Windows) would corrupt it. Mitigated by explicit UTF-8 (AC-6-004, BR-6-005).
- **RF-4 — Scope creep into V2 push channels (🟢 Low, governance).** Email/webhook are V2 and
  explicitly out of scope; the port (`deliver(str)`) is push-channel-agnostic so V2 can add adapters
  without a contract change. Watch at SPEC LOCK that no SMTP/HTTP creeps into V1.
- **RF-5 — Broken-pipe stacktrace on stdout (🟢 Low, mitigated).** Piping into a short-lived
  consumer raises `BrokenPipeError`; handle it so the operator sees no stacktrace (AC-6-009).
- **Security / STRIDE**: low. The only new capability is a local file/stdout write of
  already-public, already-rendered content under operator control. No new auth surface, no secrets,
  no network egress, no untrusted input crossing a trust boundary. Full STRIDE not triggered.
