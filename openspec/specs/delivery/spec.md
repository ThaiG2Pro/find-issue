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

