# Proposal: Delivery (S6) — ticket 6

## Why
The pipeline (Config → Collector → State Store → Summarizer → Renderer → **Delivery**)
ends at a sink. S5 (`render/renderer.py`) already produces a **single Markdown digest
string** (`render(...) -> str`); something must write that string somewhere a human can
read it. PROJECT_SPEC §5 (MVP "done" criterion) requires: run `osspulse run` on 3–5 real
repos → produce **a readable Markdown file** (`§5: "Xuất digest ra Markdown file (và/hoặc
stdout)"`). PROJECT_SPEC §6/§7 place **S6 Delivery** as the terminal sink after S5, with
**V1 = file**; email/webhook are **V2 — explicitly out of scope** (PROJECT_SPEC §5 V2,
§6 "V1 (file), V2 (push)").

This change builds the **S6 Delivery** stage: it consumes only the rendered Markdown
**string** and delivers it to a destination chosen by config — **file** (written
atomically) or **stdout**. It is the last stage and the only one (besides the state
store) that touches the user-facing filesystem.

## What Changes
- **NEW** capability `delivery`: a `Delivery` port whose concrete V1 adapters write the
  rendered Markdown string to (a) a **file** or (b) **stdout**, selected by config.
- **PORT SIGNATURE CHANGE (ports.py)**: the existing `Delivery` Protocol is
  `send(self, digest: Digest) -> None`, but S5 emits a `str`, not a `Digest`
  (renderer-5 explicitly produces and hands off a Markdown string — `render(...) -> str`).
  The Protocol SHALL be changed to consume the rendered string:
  `deliver(self, content: str) -> None`. This keeps S6 decoupled from S2/S4 and from the
  `Digest` domain model (S6 only ever sees the final string). Decision D-1; see Assumptions A-R1.
- **NEW** config key `[output]` section → `destination` ("file" | "stdout", default "file")
  and `output_path` (default `"./digest.md"`, used only when `destination = "file"`).
  Recorded in `_glossary.md`. The `Config` dataclass (`models.py`) gains two fields;
  `config.py` parses and validates the new section.
- **NEW** atomic file write: write to a temp file in the **same directory** as the target,
  `fsync`, then `os.replace` (atomic rename) → a crash mid-write never leaves a partial or
  corrupt digest file (architecture.md "write-temp-then-rename"; matches the state store's
  V1 approach).
- **NEW** stdout delivery: write the string to `sys.stdout` (V1), so the digest can be
  piped/redirected. No file written when `destination = "stdout"`.
- **NEW** error contract: a non-writable path / missing parent directory / permission
  error surfaces as `Error: <message>` on **stderr** and a non-zero exit (`1`), per
  conventions.md CLI error contract — no raw stacktrace for handled errors.

## Capabilities
- **New Capabilities**: `delivery` →
  `openspec/changes/delivery-6/specs/delivery/spec.md`
- **Modified Capabilities**: `ports.py` `Delivery` Protocol signature changes
  (`send(Digest)` → `deliver(str)`); `models.py` `Config` gains `output_destination`
  and `output_path` fields. No other capability touched: S6 consumes only the rendered
  string through pipeline data — never imports `osspulse.github`, `osspulse.summarizer`,
  `osspulse.cache`, or `osspulse.render` internals.

## Impact
- **Code**: new `src/osspulse/delivery/` adapters (file + stdout) implementing the
  `Delivery` port. `ports.py` `Delivery` signature updated. `config.py` + `models.py`
  gain the `[output]` config. `cli.py`/`pipeline.py` wire S5 string → S6 deliver (wiring
  at S4; this change specifies behavior only).
- **External**: **none** — stdlib file I/O + `sys.stdout` only. No SMTP, no HTTP, no new
  dependency (V1 hard constraint).
- **Security/Privacy**: no secrets in the delivery path; no tokens/PII written or logged.
  The digest content is already-rendered public-repo data. The only new egress is the
  local filesystem path the operator chose. STRIDE: low — one new sink is a
  local-file/stdout write under operator control (see Early Risk Flags).
- **Idempotency**: re-running overwrites the target file deterministically (atomic
  replace) — never appends, never produces duplicate/partial output (PROJECT_SPEC §7).

Figma: N/A (CLI tool, no UI).

## Scope
### In Scope (V1)
- Deliver the rendered Markdown **string** to a **file** (atomic write) or **stdout**.
- Config-driven destination selection (`[output]` section).
- CLI error contract for unwritable destinations (stderr `Error:` + exit 1).
- Deterministic overwrite (idempotent re-run).

### Out of Scope (V2 / deliberate)
- ❌ Email (SMTP) delivery — V2.
- ❌ Webhook / Discord / Slack delivery — V2.
- ❌ Multiple simultaneous destinations / fan-out — V2.
- ❌ Append/rotate/history of past digests — not in V1 (overwrite only).
- ❌ Any network egress from the delivery path.
- ❌ Compression, encryption, or upload of the digest.

## User Stories

### US-1: Deliver digest to a file
**As an** OSS Pulse operator **I want** the digest written to a Markdown file at a
configured path **So that** I can open/read/share it after a run, with no risk of a
corrupt file if the run crashes mid-write.

### US-2: Deliver digest to stdout
**As an** OSS Pulse operator **I want** to send the digest to stdout instead of a file
**So that** I can pipe or redirect it (e.g. `osspulse run > today.md`) in a shell workflow.

### US-3: Clear failure when the destination is unwritable
**As an** OSS Pulse operator **I want** a clear one-line error and a non-zero exit when
the digest cannot be written **So that** I know the run failed and why, without a stacktrace.

## Assumptions

### [CONFIRMED]
- A-C1 [CONFIRMED]: S6 input is the rendered Markdown **string** from S5 `render(...) -> str`
  — never the `Digest` model, never raw/summarized items. Source: renderer-5 proposal/handoff
  ("S6 consumes the returned Markdown string"), architecture.md S5→S6 boundary.
- A-C2 [CONFIRMED]: V1 destinations are **file and stdout only**; email/webhook are V2.
  Source: PROJECT_SPEC §5 V1/V2, §6 ("V1 (file), V2 (push)").
- A-C3 [CONFIRMED]: File writes are atomic via write-temp-then-`os.replace` in the same
  directory. Source: architecture.md "State writes should be atomic (write-temp-then-rename)";
  watch_item.
- A-C4 [CONFIRMED]: No new external dependency — stdlib `os`/`pathlib`/`sys` only.
  Source: stack.md V1, watch_item.
- A-C5 [CONFIRMED]: Errors surface as `Error: <message>` on stderr + non-zero exit (1),
  no stacktrace for handled errors. Source: conventions.md CLI error contract.
- A-C6 [CONFIRMED]: Re-running overwrites the target file deterministically (no append, no
  duplicate). Source: PROJECT_SPEC §7 idempotency.
- A-C7 [CONFIRMED]: Digest is written as **UTF-8** (the digest contains Vietnamese labels,
  e.g. the "Khác" bucket from S5). Source: glossary "Khác bucket", S5 renderer output.

### [ASSUMED] (informed guesses — confirm at SPEC LOCK)
- A-A1 [ASSUMED]: Config key is a `[output]` TOML section with `destination` ("file" |
  "stdout", default **"file"**) and `output_path` (default **"./digest.md"**). Rationale:
  mirrors the existing optional `[state]` section style in `config.py` (`state_path`
  default `"./.osspulse/state.json"`). If absent, default to file at `./digest.md`.
- A-A2 [ASSUMED]: A **missing parent directory** for `output_path` is treated as an
  **error** (surfaced, exit 1) — S6 does NOT silently `mkdir -p` the parent. Rationale:
  fail-fast convention; avoids creating unexpected directory trees. (Alternative: auto-create
  parent — flagged for the gate.)
- A-A3 [ASSUMED]: stdout delivery writes the digest **followed by a single trailing
  newline** and nothing else to stdout (no log lines on stdout), so piped output is clean.
  Rationale: clean-pipe Unix convention; logs go to stderr.
- A-A4 [ASSUMED]: An **empty / no-new-items** digest string (S5 always returns a non-empty
  "No new items" doc, never "") is still delivered verbatim — S6 does not special-case it
  or suppress the file. Rationale: S5 guarantees a non-empty doc (AC-5-008/009); S6 is a dumb sink.
- A-A5 [ASSUMED]: When `destination = "stdout"`, `output_path` is **ignored** (not validated,
  no file touched). Rationale: keeps the two modes independent.

## Edge Cases
1. (input boundary) `output_path` parent directory does not exist → error, exit 1 (A-A2).
2. (permission) `output_path` points to a read-only directory / no write permission → `Error:` + exit 1.
3. (permission) `output_path` is an existing **directory** (not a file) → error, exit 1.
4. (data integrity) Process crashes mid-write → atomic replace guarantees old file intact or new file complete, never a partial file (A-C3).
5. (data integrity) Re-run with same input → file overwritten deterministically, byte-identical to a fresh write; no append (A-C6).
6. (integration) stdout is a closed/broken pipe (e.g. `osspulse run | head`) → handled gracefully (BrokenPipeError) without a stacktrace.
7. (i18n / data integrity) Digest contains non-ASCII ("Khác", titles with emoji/CJK) → written as UTF-8, not the platform default encoding (A-C7).
8. (input boundary) Empty / "No new items" digest string → still delivered as a non-empty doc (A-A4).
9. (state transition) `destination` config value is neither "file" nor "stdout" → config validation error at load (fail fast), not at delivery time.
10. (input boundary) `output_path` is empty string when `destination = "file"` → config validation error.
11. (concurrency) Two `osspulse run` invocations target the same `output_path` concurrently → atomic replace means the file is always one complete digest (last writer wins); no interleaving/corruption (best-effort; V1 is single-operator).
12. (data integrity) Temp file left behind if `os.replace` fails after temp write → temp is in the target dir with a recognizable name; failure surfaces as an error (does not clobber the existing target).
13. (input boundary) `output_path` is a relative path → resolved relative to the process CWD (documented behavior, consistent with `state_path`).
14. (permission) Disk full / `ENOSPC` during temp write → `Error:` + exit 1; existing target file untouched (atomic).

---

## Early Risk Flags
See the spec delta file (`specs/delivery/spec.md`) — the `### Early Risk Flags` section is
authored there after the ACs, per the SDLC workflow (risk scan after S2).
