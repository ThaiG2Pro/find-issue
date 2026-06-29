## Sketch — Gap Analysis

**No critical gaps found.** All 20 ACs (16 CONFIRMED + 4 ASSUMED-locked at SPEC LOCK), 12 BRs, 3 INTs, the 7-row Error States table, the 14 edge cases, and the 5 Early Risk Flags map to concrete design elements below. The 4 `[ASSUMED]` ACs (AC-6-009, AC-6-011, AC-6-013, AC-6-015, AC-6-020) are locked V1 decisions confirmed at SPEC LOCK (D-1, A-A1, A-A2 confirmed) — none is a spec blocker. **Proceeding to full design; no S3→S2 return recommended.**

Sketch (validated against `_handoff.md` §2/§4 + `_cross-spec-context.md` id 3/5):

- **Components**: 1 MODIFIED port `Delivery` (`ports.py`: `send(Digest)` → `deliver(content: str)`, D-1) + 1 new adapter package `src/osspulse/delivery/` (file adapter + stdout adapter + a `DeliveryError`) + 2 new `Config` fields (`output_destination`, `output_path`) parsed by `config.py`. No HTTP API, no DB, no migration, no new external dependency (stdlib `os`/`pathlib`/`sys` only — RF-4).
- **Flows**: (1) config load + `[output]` validation; (2) file delivery atomic temp→fsync→`os.replace`; (3) stdout delivery + broken-pipe handling; (4) error mapping to `Error:`+exit 1.
- **Pattern reuse (search-first → Adopt)**: the atomic write is the **exact state-store-3 ADR-002 pattern** (`tempfile.mkstemp(dir=target.parent)` + `os.fsync` + `os.replace`, same-fs guarantee) — reuse, do not reinvent (`json_store.py:save`). The `DeliveryError`→`Error: <msg>` exit-1 surface mirrors state-store-3 `StateError` (ADR-003) and `ConfigError`. The `[output]` config section mirrors the existing optional `[state]` section (`config.py` step 8). The CLI top-level already does `except ConfigError → Error:/Exit(1)` (`cli.py:run`) — extend that one boundary.

Cross-spec check (id 3 state-store-3, id 5 digest-renderer-5):
- digest-renderer-5 exports `render(...) -> str` — that exact string is S6's `deliver(content)` input (INT-6-001). S6 must NOT import `osspulse.render` (it receives the string through pipeline wiring) — constraint id 5 honored via AC-6-002/BR-6-002.
- state-store-3 froze: "do not add methods to a Protocol without a 2nd impl". Here the `Delivery` Protocol is **changed** (a MODIFIED capability, D-1), not extended with helpers — the single method is renamed/retyped; this is the locked decision, not a Protocol-growth violation.

Non-code micro-decisions resolved by ADRs below (not gaps): port redesign (ADR-001), atomic-write reuse (ADR-002), broken-pipe locus (ADR-003), config validation placement (ADR-004), no-openapi (ADR-005), error class (ADR-006).

---

## Context

**Background.** OSS Pulse pipeline: Config → Collector → State Store → Summarizer → **Renderer (S5)** → **Delivery (S6)** → CLI (S7). S5 (`render(...) -> str`) already produces a single Markdown digest string. S6 is the terminal sink: it writes that string somewhere a human can read it — a file (atomically) or stdout — selected by config. It is the last stage and the only one besides the state store that touches the user-facing filesystem.

**Current state.**
- `src/osspulse/delivery/__init__.py` exists but is empty (0 bytes). No adapter exists.
- `osspulse.ports.Delivery` is a stale stub: `def send(self, digest: Digest) -> None: ...` — it never matched the realized S5 `str` contract (D-1).
- `osspulse.models.Config` is a frozen dataclass with `state_path` as its last field; `config.py:load_config` parses an optional `[state]` section (step 8). There is no `[output]` handling yet.
- `cli.py:run` already wraps `load_config` in `try/except ConfigError` and emits `Error: {e}` on stderr + `raise typer.Exit(code=1)` — the established CLI error contract.
- `state/json_store.py:save` is the reference atomic-write implementation; `state/errors.py:StateError` is the reference per-module error class.

**Constraints (locked at S2 / SPEC LOCK):**
- S6 input is the rendered **string**, never `Digest`/`SummarizedItem`/`RawItem` (AC-6-001/003, BR-6-001).
- S6 imports no upstream pipeline module — not `github`, `summarizer`, `cache`, or `render` (AC-6-002, BR-6-002, cross-spec id 5).
- File writes are atomic: temp in target's parent dir → fsync → `os.replace` (AC-6-005, BR-6-003, RF-1).
- UTF-8 explicitly on every write (AC-6-004, BR-6-005, RF-3) — never platform default.
- No SMTP/HTTP/new dependency in V1 — stdlib only (RF-4).
- `[output]` validated fail-fast at `load_config`, not at delivery time (AC-6-012/013, BR-6-008).
- Missing parent dir = error, NO auto-mkdir (AC-6-014, BR-6-010 — confirmed at SPEC LOCK).
- Errors surface as `Error: <message>` on stderr + exit 1, no stacktrace for handled errors (AC-6-016, BR-6-009).

**Stakeholders.** S5 Renderer (upstream producer of the string), S1 Config (provides `output_destination`/`output_path`), S7 CLI/pipeline (wires S5 string → chosen adapter → `deliver()`; owns the top-level error/exit boundary), S5 QA (must add a STATIC import-isolation test for AC-6-002 + the atomicity/encoding/error tests).

## Goals / Non-Goals

**Goals:**
- Redesign the `Delivery` port to `deliver(self, content: str) -> None` (AC-6-001/003, D-1).
- A `FileDelivery` adapter that writes `content` atomically and as UTF-8 to `output_path` (AC-6-004/005/006).
- A `StdoutDelivery` adapter that writes `content` + one trailing newline to `sys.stdout`, nothing else, and handles a broken pipe without a stacktrace (AC-6-007/008/009).
- A `[output]` config section + two `Config` fields, validated fail-fast at load (AC-6-010..013).
- A clear `Error: <message>` + exit-1 contract for every unwritable-file condition, with the offending path named (AC-6-014..017).
- Idempotent, never-append, deterministic overwrite; "No new items" doc delivered verbatim (AC-6-018..020).
- Each adapter trivially testable (file via `tmp_path`, stdout via captured streams) with no real network/external service — single-operator local I/O only.

**Non-Goals:**
- ❌ Email (SMTP), webhook, Discord/Slack — V2 (RF-4).
- ❌ Multiple simultaneous destinations / fan-out — V2.
- ❌ Append / rotate / digest history — V1 is overwrite-only (AC-6-018).
- ❌ Auto-creating a missing parent directory (AC-6-014, locked).
- ❌ Any network egress, compression, or encryption from the delivery path.
- ❌ Wiring S5→S6 in `cli.py`/`pipeline.py` — this change specifies behavior; the wiring lands at S4 (INT-6-003).
- ❌ Touching the `Digest` model (it stays, but S6 never uses it).

## Architecture Overview

**Style:** ports/adapters (hexagonal-lite), consistent with `architecture.md` and the 4 prior changes. S6 is a terminal infrastructure adapter behind the `Delivery` port; the core/pipeline depends only on the port, never on the concrete adapter.

**Cross-spec dependencies (reuse, do not redesign):**
- `project-foundation`: `osspulse.ports.Delivery` Protocol (CHANGED here, D-1); `osspulse.models.Config` (gains 2 fields); `osspulse.config.load_config` (gains `[output]` parsing).
- `state-store-3` (id 3): **atomic-write pattern (ADR-002)** = `tempfile.mkstemp(dir=path.parent)` → write+`flush`+`os.fsync` → `os.replace` → cleanup-on-failure. **`DeliveryError` mirrors `StateError` (ADR-003)** → surfaces as `Error: <msg>` exit 1. Note one deliberate divergence: state store does `mkdir(parents=True)` before the temp write (AC-3-015); S6 **must NOT** mkdir (AC-6-014) — see ADR-002 §Consequences.
- `digest-renderer-5` (id 5): `render(...) -> str` is the producer of S6's `content` argument (INT-6-001); the no-import-of-upstream rule (id 5 constraint) carries into AC-6-002/BR-6-002.

**New / changed elements:**

| Element | Location | Role |
|---------|----------|------|
| `Delivery(Protocol)` (CHANGED) | `src/osspulse/ports.py` | `deliver(self, content: str) -> None` — replaces `send(self, digest: Digest)` (D-1, AC-6-001/003) |
| `FileDelivery` | `src/osspulse/delivery/file_delivery.py` | Concrete adapter: atomic UTF-8 file write (AC-6-004..006, AC-6-014..020) |
| `StdoutDelivery` | `src/osspulse/delivery/stdout_delivery.py` | Concrete adapter: writes to `sys.stdout` (UTF-8) + 1 newline; broken-pipe-safe (AC-6-007..009) |
| `DeliveryError` | `src/osspulse/delivery/errors.py` | Per-module error, mirrors `StateError`; surfaces as `Error: <msg>` exit 1 (ADR-006) |
| `Config.output_destination`, `Config.output_path` | `src/osspulse/models.py` | New frozen fields, defaults `"file"` / `"./digest.md"` (AC-6-010, BR-6-007) |
| `[output]` parsing + validation | `src/osspulse/config.py` | New `load_config` step; fail-fast `ConfigError` on invalid values (AC-6-010..013, BR-6-008) |
| package exports | `src/osspulse/delivery/__init__.py` | `FileDelivery`, `StdoutDelivery`, `DeliveryError` |

**Layer rule honored:** the delivery adapters depend only on stdlib + `osspulse.delivery.errors`; they import **nothing** from `osspulse.github`/`summarizer`/`cache`/`render` and reference no domain model (AC-6-002/003, BR-6-002, verified by a STATIC import test). Adapter selection (file vs stdout) is the CLI/pipeline's job at S4 (INT-6-003), not the adapter's.

## Decisions (ADRs)

### ADR-001: `Delivery` port redesigned to `deliver(self, content: str) -> None` (decoupled from `Digest`)

**Context.** The stub `Delivery.send(self, digest: Digest) -> None` never matched the realized S5 contract — `render(...)` emits a `str`, not a `Digest`. S6 must consume that string and stay decoupled from the domain models and from upstream modules (D-1, AC-6-001/003, BR-6-001/002).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Change the Protocol to `deliver(self, content: str) -> None` | Matches the realized S5 `str` output; S6 never touches `Digest`/items; one unambiguous method; push-channel-agnostic so V2 adapters add without a contract change (RF-4) | A MODIFIED capability — must update the stale stub + the `Digest` import in `ports.py` may become unused for `Delivery` (still used by other code) |
| B. Keep `send(Digest)`; rebuild a `Digest` inside S6 | No port change | Re-couples S6 to `Digest`+items (violates BR-6-001/002); duplicates rendering; S6 would need `render` to turn a `Digest` back to a string — circular |
| C. Add a second `deliver(str)` alongside `send(Digest)` | Backward-compatible | Two ways to deliver = ambiguous; dead `send` path; violates "one role-named method" convention |

**Decision.** **Option A** (locked: D-1, confirmed at SPEC LOCK). Change `ports.py` `class Delivery(Protocol)` from `def send(self, digest: Digest) -> None: ...` to `def deliver(self, content: str) -> None: ...`. The `Digest` model is untouched and stays in `models.py`; remove it from the `Delivery` signature only. `ports.py` keeps `from osspulse.models import Digest, RawItem, SummarizedItem` (other Protocols still reference `RawItem`/`SummarizedItem`; `Digest` may remain imported even though no port now uses it — do not remove blindly; verify no other reference before touching that import).

**Consequences.** Any pipeline wiring stub referencing `Delivery.send` must be updated at S4 (no such call site exists today — `cli.py`/`pipeline.py` do not yet wire S6). Both concrete adapters implement `deliver` structurally (no subclassing — Python structural typing, matching `JsonFileStateStore`/`MarkdownDigestRenderer`). The port stays a single method — no `flush`/`close`/path methods leak in (resists drift).

### ADR-002: Atomic file write reuses the state-store-3 temp-then-replace pattern (no auto-mkdir)

**Context.** A crash mid-write must never leave a partial/corrupt digest (RF-1, AC-6-005/006, BR-6-003). The project already solved this exactly once in `state/json_store.py:save` (state-store-3 ADR-002). The only divergence: state store *creates* the parent dir; S6 must *not* (AC-6-014, BR-6-010).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Reuse state-store-3 pattern: `tempfile.mkstemp(dir=Path(output_path).parent)` → `os.fdopen(fd, "w", encoding="utf-8")` write+`flush`+`os.fsync` → `os.replace(tmp, target)` → unlink temp on failure; do NOT mkdir | Proven, atomic (same-fs `os.replace` guarantee — RF-1); single-codebase pattern; UTF-8 forced at `os.fdopen`; missing parent surfaces naturally as the `mkstemp` `FileNotFoundError`/`OSError` → AC-6-014 falls out for free | Slightly more code than a naive `open().write()` |
| B. Naive `Path(output_path).write_text(content, encoding="utf-8")` | Simplest | Partial-file on crash (violates RF-1/AC-6-005/006); rejected |
| C. Temp file in the system temp dir (`/tmp`) then `os.replace` | Familiar | Cross-filesystem rename is NOT atomic and `os.replace` raises `OSError` across devices — defeats the guarantee (RF-1 watch item); rejected |

**Decision.** **Option A.** `FileDelivery.deliver(content)`:
1. `target = Path(self._output_path)`; `parent = target.parent`.
2. Create the temp file **in `parent`** via `tempfile.mkstemp(dir=parent)` — if `parent` does not exist, `mkstemp` raises `FileNotFoundError` (a subclass of `OSError`) → caught → `DeliveryError` naming the path (AC-6-014/015). **No `mkdir`.**
3. `with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(content); fh.flush(); os.fsync(fh.fileno())` (UTF-8 forced — RF-3/AC-6-004).
4. `os.replace(tmp_name, target)` — atomic same-fs rename (AC-6-005); overwrites any existing target in place, deterministically, never appends (AC-6-018/019).
5. On any `OSError`, in a `finally`, best-effort `os.unlink(tmp_name)` so a failed replace never clobbers the existing target and leaves no live partial (AC-6-006, EC-012); re-raise as `DeliveryError`.

**Consequences.** The "same-dir temp" detail is the load-bearing correctness fact (RF-1) — a documented gotcha in the Implementation Guide. Because the temp lives in the target's dir, a permission-denied dir / read-only dir / disk-full all surface at `mkstemp`/write/`fsync` as `OSError` → uniform `DeliveryError` (AC-6-016, EC-002/14). A target that is an existing *directory* makes `os.replace(tmp, dir)` raise `OSError` (or `IsADirectoryError`) → `DeliveryError` (AC-6-017, EC-003). **Divergence from state-store-3:** drop the `mkdir(parents=True, exist_ok=True)` step — S6 is fail-fast on a missing parent by product decision (AC-6-014), state store auto-creates by its (AC-3-015).

### ADR-003: Broken-pipe (`BrokenPipeError`) is handled at the CLI top level, not inside `StdoutDelivery`

**Context.** Piping `osspulse run | head` makes the consumer exit early; the next `sys.stdout.write`/flush raises `BrokenPipeError`. AC-6-009 requires no Python stacktrace and a clean exit. The locus must be chosen and justified (watch item).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Catch `BrokenPipeError` at the CLI top level (`cli.py:run`), alongside the existing `ConfigError`/`DeliveryError` handling | One handler for the whole-program pipe condition; matches Python's own recommended idiom (a broken pipe can fire on the *final* interpreter flush of `sys.stdout`, after `deliver` returns — only a top-level handler + `sys.stdout` redirection reliably suppresses that); keeps `StdoutDelivery` a dumb writer; the CLI already owns the exit-code boundary | The adapter alone can't fully guarantee suppression (the late flush is outside it) — so this is also the *only correct* locus |
| B. Catch `BrokenPipeError` inside `StdoutDelivery.deliver` only | Localized | Does NOT cover the interpreter's final flush of `sys.stdout` at process exit, which still prints `BrokenPipeError: ... Exception ignored` — fails AC-6-009 in the common `| head` case |
| C. Ignore `SIGPIPE` via `signal.signal(SIGPIPE, SIG_DFL)` | Unix-idiomatic, kills the process silently | POSIX-only (no Windows); changes process-wide signal disposition; heavy-handed for a portable CLI |

**Decision.** **Option A** — handle the broken pipe at the **CLI top level**. `StdoutDelivery.deliver` writes `content` + one `"\n"` to `sys.stdout` and `flush()`es; it does **not** swallow `BrokenPipeError`. The CLI `run` wraps the pipeline in a handler that, on `BrokenPipeError`, (a) redirects `sys.stdout` to `os.devnull` (`os.dup2`) so the interpreter's final flush cannot re-raise, and (b) exits cleanly with no stacktrace (per the standard CPython idiom). The exact exit code is per the spec's Error States row ("0/non-zero per pipe") — documented as a CLI-wiring detail for S4, not an adapter concern.

**Consequences.** `StdoutDelivery` stays trivially testable (assert it wrote `content`+`\n` to a captured stream; assert it raised on a broken stream). The top-level `BrokenPipeError` handler is an S4 wiring task in `cli.py` (listed in tasks.md with the AC ref) — it lives next to the existing `except ConfigError` block. RF-5 mitigated.

### ADR-004: `[output]` validated fail-fast in `config.py:load_config`, mirroring the `[state]` section

**Context.** `destination ∈ {file, stdout}` (default file) and `output_path` (default `./digest.md`) must be rejected at load time, not at delivery time (BR-6-008, AC-6-012/013). The existing optional `[state]` section (`load_config` step 8) is the template.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Add a `[output]` parse+validate step in `load_config`, raising `ConfigError` on a bad `destination` or empty `file` `output_path`; set `Config.output_destination`/`output_path` | Fail-fast before the pipeline runs (BR-6-008); reuses the proven `ConfigError`→CLI `Error:` surface; mirrors `[state]` step exactly; defaults fall out when `[output]` absent (AC-6-010) | Adds 2 fields to a frozen dataclass + one parse step |
| B. Validate lazily inside the adapter at `deliver` time | Less config code | Pipeline starts, does all the GitHub/LLM work, THEN fails on a typo'd destination — wastes a run + violates fail-fast (BR-6-008, EC-009); rejected |
| C. CLI flags (`--destination`/`--output`) only, no config | Quick override | project.md makes config the setup-once entry point; loses persistence; D-2 already rejected this |

**Decision.** **Option A.** In `load_config`, after the `[state]` step, add:
```
output_section = data.get("output", {})
destination = output_section.get("destination", "file")
if destination not in ("file", "stdout"):
    raise ConfigError(f"output.destination must be 'file' or 'stdout', got {destination!r}")
output_path = output_section.get("output_path", "./digest.md")
if destination == "file" and (not isinstance(output_path, str) or not output_path.strip()):
    raise ConfigError("output.output_path must be a non-empty string when destination='file'")
```
Pass `output_destination=destination`, `output_path=output_path` to `Config(...)`. Add fields to `Config` (frozen dataclass) with defaults `output_destination: str = "file"`, `output_path: str = "./digest.md"` (AC-6-010).

**Consequences.** When `destination = "stdout"`, `output_path` is not validated (A-A5/AC-6-007/BR-6-006) — it is simply carried and ignored by the chosen adapter. Validation reuses the bool/`isinstance` discipline already in `config.py` (`_validate_lookback`). Empty-string `output_path` with `file` → `ConfigError` (AC-6-013). Invalid `destination` → `ConfigError` (AC-6-012). Both surface via the existing `cli.py` `except ConfigError → Error:/Exit(1)`.

### ADR-005: No `openapi.yaml` for this change (CLI-only, no inbound HTTP API)

**Context.** R-API-003 makes `openapi.yaml` the mandatory S3 output *for endpoints*. This change exposes no HTTP endpoint — the only contracts are an internal Python Protocol and a TOML config section.

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. Omit `openapi.yaml`; document the Python Protocol + config contract in §API Design | Accurate; matches precedent (collector ADR-007, state ADR-004, summarizer, renderer ADR-005) | Deviates from R-API-003's literal "mandatory" |
| B. Author a stub `openapi.yaml` | Satisfies R-API-003 literally | Fabricates an HTTP surface that does not exist; misleading |

**Decision.** **Option A** — a deliberate, ADR-justified deviation. **Rule cited:** R-API-003 (`openapi.yaml` mandatory) + R-API-002 (URL conventions). **Reason:** OSS Pulse is a CLI tool with no HTTP API (conventions.md "N/A — no HTTP API"; project.md "No HTTP API; this is a CLI tool"). **Spec evidence:** proposal.md Impact "no HTTP API"; INT-6-001/002/003 define the seams as a Python Protocol + config + CLI wiring, not endpoints. **Precedent:** github-collector-2 ADR-007, state-store-3 ADR-004, digest-renderer-5 ADR-005 set this exact exception for CLI-only changes.

**Consequences.** No `openapi.yaml` produced. The cross-artifact-audit endpoint check is N/A: 0 endpoints in design = 0 paths. §API Design documents the internal contract instead. DESIGN REVIEW notes this (consistent) deviation.

### ADR-006: `DeliveryError` in `delivery/errors.py`, mirroring `StateError`

**Context.** File-write failures (missing parent, permission, is-a-directory, ENOSPC, failed replace) must surface as one `Error: <message>` line + exit 1, no stacktrace (AC-6-016, BR-6-009). The project already has one error class per infrastructure module (`ConfigError`, `StateError`).

**Options.**

| Option | Pros | Cons |
|--------|------|------|
| A. New `DeliveryError(Exception)` in `src/osspulse/delivery/errors.py`; CLI catches it like `ConfigError` | Consistent with `StateError` (ADR-003); a future 2nd delivery adapter imports it without pulling in `file_delivery`; clear ownership of the error surface | One new file (3 lines) |
| B. Reuse `ConfigError` for delivery failures | No new type | Conflates *config-time* (load) errors with *delivery-time* (write) errors — different phases; misleading message origin |
| C. Let raw `OSError` propagate to the CLI | No new type | Leaks the stdlib exception/stacktrace to the user (violates AC-6-016 "no stacktrace"); CLI can't distinguish handled vs unexpected |

**Decision.** **Option A.** Add `class DeliveryError(Exception)` in `delivery/errors.py` (docstring mirrors `StateError`). `FileDelivery` catches `OSError` (and its subclasses `FileNotFoundError`/`PermissionError`/`IsADirectoryError`) and re-raises `DeliveryError(f"cannot write digest to {target}: {exc}")` — the message **names the path** (AC-6-015). The CLI top-level (S4) adds `except DeliveryError` next to `except ConfigError`, emitting `Error: {e}` on stderr + `Exit(code=1)`.

**Consequences.** The CLI wiring (S4) gains one `except DeliveryError` arm. `StdoutDelivery` does not raise `DeliveryError` for a broken pipe — that is handled separately (ADR-003). `DeliveryError` never carries a secret/PII (digest content is already-public rendered data; the message is just the path + the OS error).

## API Design

**No HTTP API** (see ADR-005). The contracts are internal:

**Port** (`osspulse.ports`):
```python
class Delivery(Protocol):
    def deliver(self, content: str) -> None: ...   # was: send(self, digest: Digest) -> None  (D-1)
```

**Adapters** (`osspulse.delivery`):
```python
class FileDelivery:    # implements Delivery structurally
    def __init__(self, output_path: str) -> None: ...
    def deliver(self, content: str) -> None: ...   # atomic UTF-8 write (ADR-002)

class StdoutDelivery:  # implements Delivery structurally
    def __init__(self, stream: TextIO | None = None) -> None: ...  # default sys.stdout (testable seam)
    def deliver(self, content: str) -> None: ...   # write content + "\n"; flush; raises on broken stream
```

**Config contract** (`osspulse.models.Config`, `[output]` TOML section):
```toml
[output]
destination = "file"          # "file" | "stdout"  (default "file")  — AC-6-010/012, BR-6-007
output_path = "./digest.md"   # default "./digest.md"; ignored when destination="stdout"  — AC-6-010/013, BR-6-006
```
- `Config.output_destination: str = "file"`, `Config.output_path: str = "./digest.md"` (frozen dataclass fields).

**Consumed by:** S7 CLI/pipeline (INT-6-003) — constructs `FileDelivery(cfg.output_path)` or `StdoutDelivery()` from `cfg.output_destination`, then calls `.deliver(rendered_string)`. **Input:** the string from `render(...)` (INT-6-001). **No** import of `osspulse.render` from `delivery/` (AC-6-002).

## DB Schema

**N/A — no database.** S6 persists only the digest file the operator configured (or stdout). No tables, no migrations, no ORM (stack.md V1). The only persisted artifact is the Markdown file at `output_path`, written atomically (ADR-002).

## Error Mapping

Aligned to the spec's Error States table. All file-write failures funnel through `DeliveryError` (ADR-006) → CLI `Error: <message>` + exit 1. Config-time failures funnel through `ConfigError` (ADR-004).

| Condition | Raised where | Type | Surfacing | Exit | AC / BR |
|-----------|--------------|------|-----------|------|---------|
| Invalid `[output].destination` (e.g. `"email"`) | `config.py:load_config` | `ConfigError` | `Error: output.destination must be 'file' or 'stdout', got 'email'` (stderr, at load) | 1 | AC-6-012, BR-6-008 |
| Empty `output_path` with `destination="file"` | `config.py:load_config` | `ConfigError` | `Error: output.output_path must be a non-empty string when destination='file'` (stderr, at load) | 1 | AC-6-013, BR-6-008 |
| Missing parent directory | `FileDelivery.deliver` (`mkstemp` → `FileNotFoundError`) | `DeliveryError` | `Error: cannot write digest to <output_path>: <os msg>` (names path) | 1 | AC-6-014/015, BR-6-009/010 |
| Permission denied on target dir | `FileDelivery.deliver` (`PermissionError`) | `DeliveryError` | `Error: cannot write digest to <output_path>: <os msg>` | 1 | AC-6-016, BR-6-009 |
| Target is an existing directory | `FileDelivery.deliver` (`os.replace` → `OSError`/`IsADirectoryError`) | `DeliveryError` | `Error: cannot write digest to <output_path>: <os msg>` | 1 | AC-6-017, BR-6-009 |
| Disk full (ENOSPC) during temp write/fsync | `FileDelivery.deliver` (`OSError`) | `DeliveryError` | `Error: cannot write digest to <output_path>: <os msg>`; existing target untouched (temp unlinked) | 1 | AC-6-016, BR-6-003/009 |
| `os.replace` fails after temp written | `FileDelivery.deliver` (`OSError`) | `DeliveryError` | `Error: ...`; existing target intact; temp cleaned up in `finally` | 1 | AC-6-006, EC-012 |
| Broken/closed stdout pipe | `cli.py:run` (top-level, ADR-003) | `BrokenPipeError` | handled — no stacktrace; redirect stdout→devnull; clean exit | 0/non-zero per pipe | AC-6-009, RF-5 |

No raw Python stacktrace is shown for any handled condition (AC-6-016). `DeliveryError` messages contain only the path + OS error text — no secrets/PII (security NFR).

## Sequence Flows

**Flow 1 — config load + `[output]` validation (S1, fail-fast):**
```
load_config(config.toml, env)
  ... existing steps (watchlist, lookback, token, llm, [state]) ...
  output_section = data.get("output", {})
  destination = output_section.get("destination", "file")           # AC-6-010 default
  if destination not in ("file","stdout"): raise ConfigError(...)    # AC-6-012
  output_path = output_section.get("output_path", "./digest.md")     # AC-6-010 default
  if destination=="file" and not output_path.strip(): raise ConfigError(...)  # AC-6-013
  return Config(..., output_destination=destination, output_path=output_path)
```

**Flow 2 — file delivery (atomic, happy + failure):**
```
FileDelivery(output_path).deliver(content):
  target = Path(output_path); parent = target.parent
  tmp = None
  try:
    fd, tmp = tempfile.mkstemp(dir=parent)            # missing parent -> FileNotFoundError  (AC-6-014/015)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:  # UTF-8 forced  (AC-6-004, RF-3)
        fh.write(content); fh.flush(); os.fsync(fh.fileno())   # ENOSPC -> OSError  (AC-6-016)
    os.replace(tmp, target); tmp = None               # atomic same-fs rename  (AC-6-005/018/019)
  except OSError as exc:
    raise DeliveryError(f"cannot write digest to {target}: {exc}") from exc   # (AC-6-016/017, BR-6-009)
  finally:
    if tmp is not None: os.unlink(tmp)  # best-effort; existing target never clobbered (AC-6-006, EC-012)
```

**Flow 3 — stdout delivery + broken-pipe (ADR-003):**
```
StdoutDelivery(stream=sys.stdout).deliver(content):
  stream.write(content); stream.write("\n"); stream.flush()   # content + 1 newline only (AC-6-007/008)
  # does NOT catch BrokenPipeError — propagates

cli.py:run  (S4 wiring):
  try: run_pipeline(); deliver(...)
  except BrokenPipeError:
    devnull = os.open(os.devnull, os.O_WRONLY); os.dup2(devnull, sys.stdout.fileno())  # suppress late flush
    raise typer.Exit(code=...)   # clean, no stacktrace (AC-6-009)
  except ConfigError as e:  typer.echo(f"Error: {e}", err=True); raise typer.Exit(1)
  except DeliveryError as e: typer.echo(f"Error: {e}", err=True); raise typer.Exit(1)   # ADR-006
```

**Flow 4 — adapter selection (S4 wiring, INT-6-003, behavior specified here):**
```
delivery = FileDelivery(cfg.output_path) if cfg.output_destination == "file" else StdoutDelivery()
delivery.deliver(render(items, lookback_days=cfg.lookback_days))   # the S5 string -> S6  (INT-6-001)
```

## Edge Cases

All 14 proposal edge cases handled by the flows above:

| EC | Handling | AC |
|----|----------|-----|
| 1 missing parent dir | `mkstemp` raises `FileNotFoundError` → `DeliveryError` naming path; no mkdir | AC-6-014/015 |
| 2 read-only dir / no perm | `mkstemp`/write raises `PermissionError` → `DeliveryError` | AC-6-016 |
| 3 target is a directory | `os.replace(tmp, dir)` raises `OSError`/`IsADirectoryError` → `DeliveryError` | AC-6-017 |
| 4 crash mid-write | Temp not yet replaced → target intact; atomic `os.replace` (ADR-002) | AC-6-005/006 |
| 5 re-run same input | `os.replace` overwrites byte-identically; never appends | AC-6-018 |
| 6 broken stdout pipe | Top-level `BrokenPipeError` handler + devnull redirect (ADR-003) | AC-6-009 |
| 7 non-ASCII ("Khác"/emoji) | `os.fdopen(..., encoding="utf-8")` (RF-3) | AC-6-004 |
| 8 empty/"No new items" doc | Delivered verbatim — S6 is a dumb sink (A-A4) | AC-6-020 |
| 9 invalid `destination` | `ConfigError` at load (Flow 1) | AC-6-012 |
| 10 empty `output_path` (file) | `ConfigError` at load (Flow 1) | AC-6-013 |
| 11 concurrent same-path runs | Atomic replace → last-writer-wins, one complete digest (single-operator, best-effort) | AC-6-005 |
| 12 temp left after failed replace | `finally: os.unlink(tmp)`; existing target never clobbered | AC-6-006 |
| 13 relative `output_path` | Resolved vs process CWD (consistent with `state_path`); documented | AC-6-011 |
| 14 disk full (ENOSPC) | `OSError` at write/fsync → `DeliveryError`; target untouched | AC-6-016 |

## Performance

- Each digest is a single in-memory string (S5 already built it); one `write` + `fsync` + `os.replace`. No streaming, no chunking needed in V1 — a digest is "readable in < 2 minutes" (project.md), i.e. small (KBs).
- `os.fsync` adds one disk-flush latency per run — acceptable and intentional (durability for RF-1). One run = one delivery; no hot loop.
- stdout path is a single buffered write + flush. No allocation hotspots.
- No caching, no concurrency primitives (single-operator, single delivery per run).

## Security

**STRIDE: NOT triggered** (confirmed at S2; the spec's Early Risk Flags §Security/STRIDE says "low … full STRIDE not triggered"). No `stride-threat-model.md` required.

Rationale: the only new capability is a local file/stdout write of **already-public, already-rendered** content under operator control. Per OWASP mapping:
- **No secrets / A02:** S6 never sees `GITHUB_TOKEN` or the LLM key; nothing to log-leak. `DeliveryError` messages carry only the path + OS error text — no secret/PII (R-SEC-001/002).
- **No injection / A03:** no SQL, no shell, no `eval`/`Function`/`innerHTML`. Content is written byte-for-byte to a local file; no interpreter sink.
- **No network egress / A10/SSRF:** stdlib file/stdout only; no SMTP/HTTP/URL fetch (RF-4). V2 push channels are explicitly out of scope.
- **Insecure design / A04:** atomic write + fail-loud error contract is the security-by-design control against silent data loss (RF-2).
- **Input validation / A05/R-SEC-003:** `[output]` config validated fail-fast at the boundary (ADR-004). The `content` argument is trusted internal pipeline data (already validated upstream), not untrusted external input.
- **Path handling:** `output_path` is operator-controlled local config (single-operator self-host tool); no traversal trust boundary is crossed. Relative paths resolve vs CWD (documented, EC-13).

No Critical/High threats → no DESIGN REVIEW security blocker.

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| RF-1: partial/corrupt digest on crash mid-write | Medium (functional) | ADR-002 atomic temp-in-same-dir → fsync → `os.replace`; QA asserts no partial target on simulated failure (AC-6-005/006). **Gotcha:** temp MUST be in `target.parent`, never `/tmp` (cross-fs `os.replace` is not atomic). |
| RF-2: silent data loss on unwritable path | Medium | ADR-006 fail-loud `DeliveryError` → `Error:` + exit 1 for every write failure (AC-6-014..017); never swallowed. |
| RF-3: non-ASCII corruption (platform default encoding) | Low | UTF-8 forced at `os.fdopen(encoding="utf-8")` and on stdout; QA round-trips "Khác"/emoji (AC-6-004). |
| RF-4: scope creep into V2 push channels | Low (governance) | stdlib-only adapters; `deliver(str)` port is push-channel-agnostic so V2 adds an adapter without a contract change. DESIGN REVIEW confirms no SMTP/HTTP. |
| RF-5: broken-pipe stacktrace on stdout | Low | ADR-003 top-level `BrokenPipeError` handler + devnull redirect suppresses the late interpreter flush (AC-6-009). |
| Import-isolation regression (someone imports `render`/`models` into `delivery/` later) | Medium | AC-6-002/003 STATIC import test (inspect `delivery/*.py`) — flagged for S5 QA; mirrors renderer AC-5-003 / summarizer AC-4-021. |
| Port-drift: I/O helper methods leak onto `Delivery` | Low | ADR-001 keeps the port at one `deliver(str)` method; documented gotcha. |

## Implementation Guide

**Recommended order** (foundational/port → error → adapters → config → exports → tests; matches the project's layering):
1. `src/osspulse/ports.py` — change `Delivery.send(self, digest: Digest)` → `deliver(self, content: str)` (ADR-001). Leave the `from osspulse.models import Digest, RawItem, SummarizedItem` import as-is unless verified unused.
2. `src/osspulse/delivery/errors.py` — add `class DeliveryError(Exception)` with a docstring mirroring `StateError` (ADR-006).
3. `src/osspulse/delivery/file_delivery.py` — `FileDelivery(output_path)` with the atomic-write `deliver` (ADR-002, Flow 2). Copy the structure of `state/json_store.py:save` but **drop the `mkdir`** and write `content` (not JSON).
4. `src/osspulse/delivery/stdout_delivery.py` — `StdoutDelivery(stream=None)` (default `sys.stdout`); `deliver` writes `content` + `"\n"` + `flush`; does NOT catch `BrokenPipeError` (ADR-003, Flow 3).
5. `src/osspulse/models.py` — add `output_destination: str = "file"` and `output_path: str = "./digest.md"` to the frozen `Config` dataclass (after `state_path`).
6. `src/osspulse/config.py` — add the `[output]` parse+validate step in `load_config` after the `[state]` step (ADR-004, Flow 1); pass the 2 new fields to `Config(...)`.
7. `src/osspulse/delivery/__init__.py` — export `FileDelivery`, `StdoutDelivery`, `DeliveryError` (replace the empty file).
8. Tests — per-AC unit tests (see tasks.md): atomic write + UTF-8 round-trip (`tmp_path`), failure modes (missing parent / perm / is-a-dir / failed replace via monkeypatch), stdout content+newline + broken-stream raise, config validation (good/invalid/empty), idempotent overwrite, "No new items" verbatim, and the STATIC import-isolation test.

> Note: the S4→S6 **wiring** in `cli.py`/`pipeline.py` (adapter selection from config + the top-level `BrokenPipeError`/`DeliveryError` handlers) is part of S4 build (INT-6-003); it is listed in tasks.md as wiring tasks. This change specifies the behavior and the handler shape (Flow 3/4).

**Patterns to follow (with file paths):**
- Atomic write → mirror `src/osspulse/state/json_store.py:save` (`tempfile.mkstemp(dir=...)` → `os.fdopen` → `fsync` → `os.replace` → `finally: unlink`), minus the `mkdir`.
- Per-module error class → mirror `src/osspulse/state/errors.py` (`StateError`).
- CLI error surface → mirror `src/osspulse/cli.py:run` (`except ConfigError → typer.echo("Error: …", err=True); raise typer.Exit(1)`); add `except DeliveryError` + `except BrokenPipeError` arms.
- Config section parse → mirror `config.py` step 8 (`[state]` → `state_path`) and the bool/`isinstance` discipline in `_validate_lookback`.
- Structural Protocol adapter (no subclassing) → mirror `JsonFileStateStore` / `MarkdownDigestRenderer`.

**Gotchas:**
- **Temp file MUST be in `Path(output_path).parent`, never the system temp dir** — cross-filesystem `os.replace` is NOT atomic and raises `OSError` (RF-1). This is the single load-bearing correctness fact.
- **Do NOT `mkdir` the parent** — S6 is fail-fast on a missing parent (AC-6-014); diverges from state-store-3 which *does* mkdir.
- **Force `encoding="utf-8"`** on the `os.fdopen` and ensure stdout writes UTF-8 — never rely on the platform default (RF-3, Windows cp1252 would corrupt "Khác").
- **`StdoutDelivery` must not swallow `BrokenPipeError`** — the suppression is the CLI top-level handler + devnull redirect (ADR-003); a local catch misses the interpreter's final flush.
- **`deliver` returns `None`** and is byte-preserving except the single stdout trailing newline (AC-6-001/008) — no transformation of `content`.
- **`delivery/__init__.py` is currently empty** — replace it, don't append a duplicate.
- **No import of `osspulse.render`/`models`/`github`/`summarizer`/`cache` from `delivery/`** (AC-6-002/003) — the STATIC import test enforces this; `DeliveryError` lives in `delivery/errors.py` precisely so a future adapter need not import `file_delivery`.
- **Validation lives in `config.py`, not the adapter** (BR-6-008) — the adapter assumes a valid `output_path` and only handles I/O failures.
