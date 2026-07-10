## Sketch — Gap Analysis

**No critical gaps found.** The S2 spec delta (`specs/scheduler-cli/spec.md`) is fully
CONFIRMED (24 ACs, 7 BRs, 4 INTs, 15 edge cases), and all four architect watch-items from
`_handoff.md §2/§4` are resolvable at design time with the existing codebase contracts:

- **Lock API** — pinnable to `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on an advisory lock file; kernel
  auto-releases the fd on process death (confirmed below, ADR-004).
- **Lock path** — derivable as `Path(config.state_path).parent / "osspulse.lock"` with **no new
  `Config` field** (scheduler-cli-7 ADR-002 discipline holds; ADR-004).
- **Binary resolution** — `shutil.which("osspulse")` → fallback `os.path.abspath(sys.argv[0])`
  works for both a pipx/pip console-script and `python -m osspulse` (ADR-002).
- **Shared secret guard** — one `assert_no_secret(text, secrets)` helper reused by both generators
  (ADR-006).

### Sketch summary
- **Commands**: one new Typer subcommand `osspulse schedule` (flags: `--cron`, `--preset`,
  `--install`, `--uninstall`, `--github-actions`, `--output`, `--config`); `osspulse run` gains a
  single-instance lock + TTY/color hardening.
- **New module**: `src/osspulse/schedule/` package (cron spec validation + line generation, crontab
  managed-block install/uninstall behind a `CrontabClient` wrapper, GitHub Actions workflow
  generation, shared secret guard, errors).
- **New module**: `src/osspulse/lock.py` (single-instance advisory lock).
- **DB tables**: none (JSON state store only; lock is a zero-byte advisory file, not state).
- **Key flows**: (1) generate/print crontab line; (2) install/uninstall managed block; (3) emit
  Actions workflow; (4) `run` acquires lock → pipeline → release (benign skip on contention).

### Cross-spec dependencies (reuse, do not redesign)
- **scheduler-cli-7**: `run_pipeline(config)` + `osspulse run` error boundary/exit-code contract
  (ADR-005: 0 success incl. empty; 1 fatal). This change wraps `run` with the lock and reaffirms
  the contract for cron (AC-V2-002-018..020) — it does NOT change the pipeline body.
- **scheduler-cli-7 ADR-002**: derive adapter tunables in the pipeline/CLI, never add `Config`
  fields. Binding for the lock path (ADR-004).
- **state-store-3**: `Config.state_path` (default `./.osspulse/state.json`); atomic write pattern
  (`tempfile` in `state_path.parent` + `os.replace`). Lock co-locates with the state it guards.
- **github-collector-2 ADR-004** / **delivery ADR**: per-module single error class in
  `<module>/errors.py`, surfaced at the CLI as `Error: <msg>` exit 1. This change follows it with a
  new `ScheduleError`.

---

## Context

`osspulse run` (scheduler-cli-7) runs the full pipeline once, on demand. PROJECT_SPEC §8 fixes
scheduling to **OS cron (primary) + GitHub Actions cron (optional)** with **no background service**.
This change adds the `osspulse schedule` command that *generates and optionally installs* cron
artifacts, and makes `osspulse run` verifiably cron-safe (no TTY/prompt/color) and concurrency-safe
(single-instance lock). osspulse stays single-shot — the OS/CI owns the timer (BR-V2-002-007).

Constraints carried in: no daemon / no APScheduler (PROJECT_SPEC §8); no new `Config` field where a
value can be derived (scheduler-cli-7 ADR-002); every external call (`crontab`) behind a mockable
wrapper; generated artifacts must never inline a secret (BR-V2-002-001, RISK-001 HIGH).

## Goals / Non-Goals

**Goals:**
- `osspulse schedule` generates a print-only, absolute-path crontab line by default (AC-V2-002-001..008).
- `--install`/`--uninstall` manage an idempotent, byte-preserving marker-delimited block (AC-V2-002-009..013, -024).
- `--github-actions [--output]` emits a secretless, UTC-documented workflow (AC-V2-002-014..017).
- `osspulse run` is cron-safe (no prompt/TTY, deterministic exits, no ANSI on non-TTY) (AC-V2-002-018..020).
- `osspulse run` holds a single-instance advisory lock; overlap = benign WARN + exit 0; crash-safe (AC-V2-002-021..023).

**Non-Goals:**
- No daemon / in-process scheduler; no Windows Task Scheduler; no distributed/multi-host lock; no
  new digest content or delivery channel; no secret-vault integration (all per proposal §Non-Goals).

## Decisions

### ADR-001 — New `schedule/` package + `lock.py` module (where the code lives)

**Context**: The change adds cron-line generation, crontab install/uninstall (shells out to
`crontab`), Actions-workflow generation, and a run-time lock. scheduler-cli-7 sets the constraint
that `pipeline.py` is the only cross-stage importer and stage modules never import each other.

| Option | Pros | Cons |
|---|---|---|
| A. One flat `schedule.py` module | fewest files | mixes 3 concerns (cron gen, crontab I/O, YAML gen) + secret guard; hard to test in isolation; violates per-module error-class tidiness |
| B. `schedule/` package (submodules: `cron.py`, `crontab.py`, `workflow.py`, `secrets.py`, `errors.py`) + separate `lock.py` | each concern isolated + independently mockable; mirrors existing package layout (`github/`, `state/`, `delivery/`); lock is a `run`-time concern orthogonal to `schedule`, so it lives at top level next to `pipeline.py` | more files |
| C. Put lock inside `pipeline.py` | fewer files | lock is acquired at the CLI boundary (before `run_pipeline`) per AC-V2-002-021; burying it in pipeline blurs the boundary and complicates the benign-skip control flow at the CLI |

**Decision**: **B**. Create `src/osspulse/schedule/` (`cron.py`, `crontab.py`, `workflow.py`,
`secrets.py`, `errors.py`, `__init__.py`) and a top-level `src/osspulse/lock.py`. The lock is
acquired in `cli.run` around `run_pipeline` (matches AC-V2-002-021 "before invoking run_pipeline")
so the benign-skip (WARN + exit 0) is handled at the CLI error boundary alongside the existing
exit-code contract.

**Consequences**: Clean unit boundaries — `cron`/`workflow`/`secrets` are pure (no I/O, trivially
tested); `crontab` and `lock` isolate the OS calls behind mockable seams. `pipeline.py` body is
untouched (lock wraps it at the CLI). Six new files + tests.

### ADR-002 — Binary + config path resolution for the generated line

**Context**: AC-V2-002-004/-024 + BR-V2-002-006: the crontab line must use an **absolute** binary
path and config path so it runs under cron's minimal PATH/cwd; no cron-daemon PATH probing. Watch
item: must work for a pipx/pip console-script AND `python -m osspulse`.

| Option | Pros | Cons |
|---|---|---|
| A. `shutil.which("osspulse")` → fallback `os.path.abspath(sys.argv[0])` | `which` finds the installed console-script on PATH (pipx/pip case) returning an absolute path; `sys.argv[0]` abspath covers the `python -m`/local case; deterministic, no cron probe | `sys.argv[0]` for `python -m osspulse` is the module launcher path — documented gotcha (see Implementation Guide) |
| B. Hardcode `/usr/local/bin/osspulse` | simple | wrong under pipx (`~/.local/bin`), venv, or `python -m`; brittle |
| C. Add a `Config.binary_path` field | explicit | violates scheduler-cli-7 ADR-002 (no Config field for derivable tunables); analyst rejected it |

**Decision**: **A**. `resolve_binary()` returns `shutil.which("osspulse")` if found, else
`os.path.abspath(sys.argv[0])`. Config path resolved via `Path(config_path).resolve()` (absolute).
When neither yields an `osspulse` console-script (pure `python -m osspulse` invocation), the
resolved `sys.argv[0]` points at the entry module — documented, and the generator emits it verbatim
(cron runs it as-is). No PATH verification (AC-V2-002-024).

**Consequences**: One `resolve_binary()` helper in `schedule/cron.py`, injectable in tests (monkeypatch
`shutil.which`/`sys.argv`). Covers the two supported invocation styles; the `python -m` corner is a
documented README note, not a code branch.

### ADR-003 — Cron spec validation before any write (fail-fast)

**Context**: BR-V2-002-003 + AC-V2-002-006/-007: an invalid `--cron` expression, or `--cron` +
`--preset` together, must fail with `Error: <msg>` exit 1, no traceback, and **no** partial write /
crontab mutation. Need a 5-field cron validator without adding a heavy dependency.

| Option | Pros | Cons |
|---|---|---|
| A. Small in-repo 5-field validator (field count + per-field numeric-range/`*`/`,`/`-`/`/` check) | zero new dependency (stack is lean by principle); enough to reject `99 * * * *` and malformed specs; deterministic | not a full cron grammar (won't validate `@reboot` / names like `MON`) — acceptable, presets cover the common cases |
| B. Add `croniter`/`cron-descriptor` dependency | full grammar | new runtime dep for a tiny need; violates lean-stack principle; search-first says reuse-or-build — the need is small enough to build |
| C. No validation, let cron reject it later | trivial | violates BR-V2-002-003 fail-fast; a bad line silently never fires |

**Decision**: **A**. `validate_cron_expr(expr) -> None` (raises `ScheduleError`) checks: exactly 5
whitespace-separated fields; each field matches `*`, `*/n`, `n`, `n-m`, `n,m`, or `n-m/s` with each
number inside its field range (min 0-59, hour 0-23, dom 1-31, month 1-12, dow 0-7). Presets map to
known-valid constants so they bypass numeric validation. Mutual-exclusion (`--cron` + `--preset`)
checked at the CLI before resolution. **Validation runs before any I/O** — the resolve→validate→
(print|install|write) order guarantees no partial side effect.

**Consequences**: Self-contained, dependency-free, deterministic (audit-stable). Won't accept
`@reboot`/named fields — a documented limitation; operators needing those pass a raw line manually.

### ADR-004 — Single-instance lock: `fcntl.flock(LOCK_EX|LOCK_NB)` at `state_path.parent/osspulse.lock`

**Context**: BR-V2-002-004/-005 + AC-V2-002-021..023 + INT-V2-002-003. At most one `run` per state
file; overlap = benign skip (WARN + exit 0); crash (`kill -9`) must not leave a stale lock. Watch
items: pin the exact flock API + non-blocking semantics; confirm derive-not-Config-field.

| Option | Pros | Cons |
|---|---|---|
| A. `fcntl.flock(fd, LOCK_EX \| LOCK_NB)` on a dedicated lock file | kernel **auto-releases** the advisory lock when the fd closes on process death (incl. `kill -9`) → zero stale-lock heuristic (AC-V2-002-023); `LOCK_NB` makes a held lock raise `BlockingIOError` immediately → benign skip, never blocks (AC-V2-002-022); stdlib-only | Unix-only (accepted: OS cron = Unix per proposal §Non-Goals) |
| B. pidfile + manual staleness (pid alive? mtime age?) | cross-platform-ish | needs a staleness heuristic (the exact thing AC-V2-002-023 avoids); racy; analyst rejected |
| C. `Config.lock_path` field | explicit path | violates scheduler-cli-7 ADR-002; analyst rejected |

**Decision**: **A**. New `src/osspulse/lock.py` exposing a `single_instance_lock(state_path)`
**context manager**:
```
lock_path = Path(state_path).parent / "osspulse.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)   # same dir the state store creates
fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)     # non-blocking exclusive
except BlockingIOError:
    os.close(fd); raise LockHeldError            # → CLI: WARN + exit 0 (benign skip)
try:
    yield
finally:
    fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)       # explicit release; kernel also frees on death
```
Path is **derived** from `state_path.parent` — no `Config` field (ADR-002 upheld). The lock file is
an advisory zero-byte marker, **not** part of the state doc (never versioned/loaded).

**Consequences**: `run` acquires before `run_pipeline` and releases after (context manager makes
release exception-safe). Crash safety is the kernel's job — no pidfile, no mtime timeout. Testable
two ways: (1) a real two-fd flock test in a tmp dir (second acquire raises `LockHeldError`); (2) the
crash path asserted by closing the first fd and re-acquiring. `LockHeldError` is a distinct internal
exception (subclass of `ScheduleError`? no — see ADR-005) so the CLI can map it to exit 0, not exit 1.

### ADR-005 — Error taxonomy: `ScheduleError` (fatal, exit 1) vs `LockHeldError` (benign, exit 0)

**Context**: The per-module-one-error-class convention (delivery-6 memory) surfaces module errors as
`Error: <msg>` exit 1. But the lock contention path must exit **0** (AC-V2-002-022), so it cannot be
a plain fatal error mapped to exit 1.

| Option | Pros | Cons |
|---|---|---|
| A. `ScheduleError` (fatal→exit 1) in `schedule/errors.py`; `LockHeldError` a **separate** class in `lock.py` caught first → WARN + exit 0 | keeps the exit-1 error contract intact; benign skip is an explicit, first-matched branch; mirrors ADR-003 order-dependent except arms in pipeline | two error classes across two modules (acceptable — different modules, different exit codes) |
| B. One `ScheduleError` with a boolean `benign` flag | one class | CLI must inspect a flag to choose exit code — fragile; conflates two outcomes |
| C. Return a sentinel instead of raising for contention | no exception | breaks the context-manager pattern; awkward with `with` |

**Decision**: **A**. `schedule/errors.py` defines `ScheduleError(Exception)` for all fatal schedule
failures (invalid cron, `crontab` missing, unwritable `--output`). `lock.py` defines
`LockHeldError(Exception)` for benign contention. In `cli.run`, the `LockHeldError` handler is
ordered **first** (WARN via logger + `raise typer.Exit(code=0)`); `ScheduleError` maps to
`Error: <msg>` exit 1 like the other fatals. `schedule` command adds `ScheduleError` to its own
error boundary.

**Consequences**: Exit-code contract stays: 0 = success **or benign skip**; 1 = fatal. Two small
error classes. CLI error-arm ordering is load-bearing (documented, like pipeline ADR-003).

### ADR-006 — One shared secret guard reused by both generators (RISK-001 mitigation)

**Context**: RISK-001 (HIGH): a naive generator could inline `GITHUB_TOKEN`/LLM key into the
crontab line (AC-V2-002-005) or the Actions YAML (AC-V2-002-015). The Actions path is the hardest
surface. Analyst asks for **one** "no secret substring in any generated output" assertion reused by
both generators.

| Option | Pros | Cons |
|---|---|---|
| A. `assert_no_secret(text, secret_values)` in `schedule/secrets.py`, called at the end of BOTH generators before returning/writing | single choke-point; both surfaces provably covered; one test target; defense-in-depth (generators are written to never inline, guard is the backstop) | a redundant check by design (that's the point) |
| B. Rely on tests only (no runtime guard) | no runtime cost | a future edit could regress and only a test would catch it; no defense-in-depth |
| C. Redact secrets from output post-hoc | "safe by construction" | masks a bug instead of failing on it; could corrupt a legitimate line |

**Decision**: **A**. `collect_secret_values(env) -> list[str]` gathers non-empty `GITHUB_TOKEN` and
the resolved LLM key from the environment; `assert_no_secret(text, values)` raises `ScheduleError`
if any non-empty value appears as a substring of `text`. Both `cron.generate_line(...)` and
`workflow.generate_workflow(...)` call it on their final output before returning. The crontab
`--install` path guards the full rendered block too.

**Consequences**: One reused function, one focused test (`test_schedule_secrets.py`) feeding a token
via env and asserting neither generator's output contains it. Generators are still written to
reference `.env`/`${{ secrets.* }}` — the guard is the backstop, not the primary mechanism.

### ADR-007 — Crontab managed-block: marker constants + byte-preserving round-trip

**Context**: RISK-002 (MEDIUM), AC-V2-002-009..012, BR-V2-002-002. `--install` must add/replace a
marker-delimited block idempotently; everything outside preserved byte-for-byte; install→install→
uninstall must be byte-identical to the original. Trickiest logic in the change (newline handling).

| Option | Pros | Cons |
|---|---|---|
| A. Split existing crontab on the marker pair, rebuild [before]+[block]+[after], preserve trailing newline exactly | deterministic; round-trip-safe if newline handling is precise | must handle: no existing crontab, block absent, block present, content with/without trailing newline |
| B. Regex-replace the block region | terse | regex over multi-line user content is fragile (greedy/DOTALL pitfalls); risks eating unrelated lines |

**Decision**: **A**. Markers pinned: `# >>> osspulse >>>` and `# <<< osspulse <<<` (one line each).
`upsert_block(current: str, block_body: str) -> str`:
1. If both markers present → replace the inclusive `[start..end]` region with the new block.
2. Else → append the block. If `current` is non-empty and does not end with `\n`, add one first;
   the managed block is `marker_start\n{cron_line}\n{marker_end}\n`.
`remove_block(current) -> str`: drop the inclusive marker region; if no markers → return `current`
unchanged (no-op, AC-V2-002-012). Round-trip rule: `remove_block(upsert_block(x)) == x` for any `x`
that had no osspulse block — guaranteed by the "add leading `\n` only when appending, strip the
exact region on remove" symmetry. A dedicated round-trip test asserts byte-identity.

**Consequences**: Pure string functions (no I/O) — fully unit-testable without touching a real
crontab. The `CrontabClient` (ADR-008) supplies `current` and writes the result. Precise
newline handling is the one place to be careful — covered by the round-trip + trailing-newline tests.

### ADR-008 — `crontab` behind a mockable `CrontabClient` wrapper (INT-V2-002-001)

**Context**: `--install`/`--uninstall` shell out to the system `crontab` command. Tests must never
touch the real user crontab (mockable seam). Missing `crontab` → `Error:` exit 1 (AC-V2-002-013).

| Option | Pros | Cons |
|---|---|---|
| A. `CrontabClient` class wrapping `subprocess` (`read()` = `crontab -l`; `write(text)` = `crontab -` via stdin), raising `ScheduleError` when the binary is absent (`shutil.which("crontab") is None` / `FileNotFoundError`) | single mock seam; the pure block functions (ADR-007) do the logic; matches ports/adapters style | one thin class |
| B. Call `subprocess` inline in the command handler | fewer files | not mockable without patching subprocess globally; muddles logic + I/O |

**Decision**: **A**. `schedule/crontab.py` defines `CrontabClient` with `read() -> str` (empty
string when no crontab / "no crontab for user") and `write(text) -> None`. Constructor (or `read`)
checks `shutil.which("crontab")`; absent → `ScheduleError("crontab command not found")`. Install =
`write(upsert_block(read(), line))`; uninstall = `write(remove_block(read()))` (skip write if
unchanged). Tests inject a fake client with an in-memory buffer.

**Consequences**: Zero real-crontab access in tests; the byte-identical round-trip test runs against
the fake buffer. `crontab -l` exit-code nuance (exit 1 + "no crontab for user" on empty) normalized
to `""` inside `read()`.

### ADR-009 — No `openapi.yaml` (CLI tool, no HTTP surface)

**Context**: R5 wants a separate `openapi.yaml` *if the change has an API*. This change adds a CLI
subcommand only; there is no HTTP endpoint (cites state-store-3 ADR-004, github-collector-2 ADR-007,
scheduler-cli-7 — all CLI-only, all skipped openapi.yaml).

| Option | Pros | Cons |
|---|---|---|
| A. No openapi.yaml; document N/A here | matches reality (no HTTP API) + prior-change precedent | R5 deviation — justified by this ADR |
| B. Author an openapi.yaml anyway | satisfies R5 literally | fabricates an HTTP contract that does not exist; misleading |

**Decision**: **A**. No `openapi.yaml`. The "interface contract" is the CLI: `osspulse schedule`
flags + `osspulse run` exit codes, specified in §API Design (CLI Contract) below. Deviation from R5
justified: there is no HTTP API (conventions.md "N/A — no HTTP API").

**Consequences**: cross-artifact-audit treats API-contract checks as N/A; the CLI contract table is
the authority the audit maps ACs against.

### ADR-010 — TTY/color + no-prompt hardening at the CLI boundary (cron-safe run)

**Context**: AC-V2-002-018..020: `run` must never prompt/need a TTY, emit deterministic exit codes,
and produce no ANSI color when stdout is not a TTY. Handoff §3: TTY/color detection belongs at the
CLI boundary, not in pipeline stages.

| Option | Pros | Cons |
|---|---|---|
| A. Detect `sys.stdout.isatty()` at CLI boundary; when False, set a no-color flag/env used by any colored output; never call interactive prompts anywhere in `run` | keeps detection at one boundary (handoff §3); pipeline stays pure; deterministic | must audit that no stage prompts (they don't today) |
| B. Add a `--no-color` flag operators must pass | explicit | breaks unattended-by-default (cron won't pass it); relies on operator memory |

**Decision**: **A**. `cli.run` computes `is_tty = sys.stdout.isatty()`; when not a TTY it disables
color (the pipeline/logging emit no ANSI already — this AC is largely a *verification/reaffirmation*
of scheduler-cli-7's cron-mail-friendly logging per handoff §3, plus tests asserting no ANSI escape
in captured non-TTY output and that no `typer.prompt`/`click.confirm` exists in the `run` path). The
exit-code contract (ADR-005 scheduler-cli-7) is reaffirmed unchanged.

**Consequences**: Mostly test-backed reaffirmation + a small no-color guard; no pipeline change. New
tests assert: no ANSI in non-TTY output (AC-V2-002-020); `run` completes with stdin/stdout not a TTY
(AC-V2-002-018); exit 0 on success incl. no-new-items and exit 1 only on the established fatals
(AC-V2-002-019).

## API Design (CLI Contract — no HTTP API, see ADR-009)

**New command: `osspulse schedule`**

| Flag | Type | Meaning |
|---|---|---|
| `--config PATH` | Path (default `config.toml`) | config file; resolved absolute into the generated line |
| `--cron "<expr>"` | str | explicit 5-field cron expression (mutually exclusive with `--preset`) — used verbatim (AC-V2-002-002) |
| `--preset {hourly\|daily\|weekly}` | enum | `0 * * * *` / `0 8 * * *` / `0 8 * * 1` (AC-V2-002-003) |
| `--install` | bool flag | install/replace the managed block in the user crontab |
| `--uninstall` | bool flag | remove the managed block (no-op if absent) |
| `--github-actions` | bool flag | emit a GitHub Actions workflow instead of a crontab line |
| `--output PATH` | Path | with `--github-actions`, write the workflow to PATH instead of stdout |

Default (no cadence flag) → daily `0 8 * * *` (AC-V2-002-008). Default (no action flag) → print the
crontab line to stdout, mutate nothing (AC-V2-002-001).

**Exit codes** (both commands): `0` = success or benign skip; `1` = fatal (`ScheduleError`:
invalid cron, mutually-exclusive flags, `crontab` missing, unwritable `--output`; plus the existing
`run` fatals). Errors: `Error: <message>` on stderr, no traceback (matches conventions.md).

**Modified command: `osspulse run`** — unchanged interface; internally wrapped in
`single_instance_lock(config.state_path)`; `LockHeldError` → WARN + exit 0.

## DB Schema

None. No database (V1/V2 JSON state store). The lock file (`state_path.parent/osspulse.lock`) is a
zero-byte advisory marker, **not** persisted state — never loaded, versioned, or written to. No
change to the state doc shape (`{version:1, seen:{...}}`, state-store-3).

## Error Mapping

| Condition | AC | Exception | CLI outcome |
|---|---|---|---|
| Invalid `--cron` expression | AC-V2-002-006 | `ScheduleError` | `Error: <msg>` stderr, exit 1, no write |
| `--cron` + `--preset` together | AC-V2-002-007 | `ScheduleError` | `Error: <msg>` stderr, exit 1, nothing generated |
| `crontab` command not on PATH | AC-V2-002-013 | `ScheduleError` | `Error: <msg>` stderr, exit 1 |
| `--output` parent not writable | AC-V2-002-016 | `ScheduleError` | `Error: <msg>` stderr, exit 1, no partial file |
| Secret would appear in output | AC-V2-002-005/-015 | `ScheduleError` | `Error: <msg>` stderr, exit 1 (backstop; generators avoid it by construction) |
| Lock already held (overlap) | AC-V2-002-022 | `LockHeldError` | WARN via logger, **exit 0** (benign skip) |
| Uninstall, no block present | AC-V2-002-012 | — | no-op, exit 0 |
| `run` fatal (Config/Auth/State/Delivery) | AC-V2-002-019 | existing | `Error: <msg>` exit 1 (scheduler-cli-7 ADR-005) |

No Python traceback for any handled case (conventions.md). Error-arm order in `cli.run`:
`LockHeldError` (exit 0) matched **before** fatal arms (ADR-005).

## Sequence Flows

**Flow 1 — `osspulse schedule` (print, default)**
`cli.schedule` → reject if `--cron`+`--preset` → resolve cadence (flag|preset|default `0 8 * * *`)
→ `validate_cron_expr` (fail-fast) → `resolve_binary()` + `Path(config).resolve()` →
`generate_line()` → `assert_no_secret(line, secrets)` → print to stdout, exit 0.

**Flow 2 — `--install`**
… resolve+validate as Flow 1 → `generate_line()` → `assert_no_secret` → `client = CrontabClient()`
(raises if `crontab` missing) → `new = upsert_block(client.read(), line)` → `client.write(new)` →
exit 0. Re-install replaces the block in place (idempotent, AC-V2-002-010); lines outside preserved
byte-for-byte (AC-V2-002-011).

**Flow 3 — `--uninstall`**
`client = CrontabClient()` → `new = remove_block(client.read())` → write only if changed → exit 0
(no-op when no block, AC-V2-002-012).

**Flow 4 — `--github-actions [--output]`**
resolve+validate cadence → `generate_workflow(cron_expr)` (includes UTC comment, `${{ secrets.* }}`
refs) → `assert_no_secret(yaml, secrets)` → if `--output`: write to path (parent unwritable →
`ScheduleError`, no partial file); else print → exit 0.

**Flow 5 — `osspulse run` with lock**
`cli.run` → `load_config` → `with single_instance_lock(cfg.state_path):` → `run_pipeline(cfg)` →
release on exit. If lock held → `LockHeldError` → WARN + exit 0. Crash while held → kernel releases
the flock; next run acquires cleanly (AC-V2-002-023).

## Edge Cases

Maps proposal §Edge Cases 1–15. Notably: (7) relative paths → ADR-002 emits absolute; (8) overlap →
ADR-004 `LOCK_NB` benign skip; (9) `kill -9` → ADR-004 kernel auto-release; (10) secret in YAML →
ADR-006 guard; (11) TZ divergence → workflow UTC comment (AC-V2-002-017); (13) unwritable `--output`
→ write to a temp in the parent then `os.replace`, so an unwritable parent fails before any partial
file appears (reuses delivery-6 atomic-write memory); (14) non-TTY → ADR-010 no color/prompt; (4)
re-install idempotent + (5) uninstall-absent no-op → ADR-007.

## Performance

Negligible. `schedule` is a one-shot generator (string building + at most one `crontab` read/write).
The lock adds one `open`+`flock` syscall pair per `run` (microseconds), non-blocking so it never
stalls. No new network, no new dependency, no hot path.

## Security

- **RISK-001 (HIGH, Information disclosure)** → ADR-006 shared `assert_no_secret` backstop on both
  generators + generators reference `.env`/`${{ secrets.* }}` by construction (AC-V2-002-005/-015).
- **RISK-002 (MEDIUM, Tampering)** → ADR-007 managed-block confinement + byte-identical round-trip
  (AC-V2-002-011); operate only on the invoking user's crontab, never `sudo` (proposal EoP mitigation).
- **RISK-003 (MEDIUM, DoS)** → ADR-004 single-instance lock + benign skip (AC-V2-002-021/-022).
- **RISK-004 (MEDIUM, stale-lock)** → ADR-004 `fcntl.flock` kernel auto-release, no staleness
  heuristic (AC-V2-002-023).
- Token/key discipline (scheduler-cli-7 BR-7-006): secret values only read to feed the guard; never
  logged, never written to any artifact. Lock file is `0o600`.

STRIDE gate: the four risks each have a concrete mitigation tied to an AC + test → **PASS** (no
BLOCK). No auth/payment/PII surface added, so no separate `stride-threat-model.md` required at lite
rigor beyond the proposal's risk block.

## Risk Assessment

| Area | Risk | Mitigation |
|---|---|---|
| Crontab round-trip | newline handling corrupts unrelated lines | ADR-007 pure functions + byte-identical round-trip test + trailing-newline test |
| Lock correctness | overlap/crash hard to test deterministically | ADR-004 real two-fd flock test (contention) + close-fd-then-reacquire test (crash) |
| Secret leakage | future edit inlines a secret | ADR-006 runtime backstop + no-substring test feeding a real env token |
| `python -m osspulse` binary path | `sys.argv[0]` is the module launcher, not a console-script | documented README gotcha; `which` covers the pipx/pip common case |
| TZ divergence | Actions UTC vs OS local off-by-hours | AC-V2-002-017 UTC comment in generated workflow + README §Scheduling |

## Implementation Guide

**Recommended order** (data/pure → I/O adapters → CLI wiring → tests; per R10 layering):
1. `schedule/errors.py` (`ScheduleError`) + `lock.py` (`LockHeldError`, `single_instance_lock`) — foundational.
2. `schedule/cron.py` — `PRESETS`, `validate_cron_expr`, `resolve_binary`, `generate_line` (pure).
3. `schedule/secrets.py` — `collect_secret_values`, `assert_no_secret` (pure).
4. `schedule/workflow.py` — `generate_workflow` (pure; UTC comment, `${{ secrets.* }}`).
5. `schedule/crontab.py` — `CrontabClient` (subprocess seam) + `upsert_block`/`remove_block` (pure).
6. `cli.py` — add `schedule` command wiring all of the above; wrap `run` in `single_instance_lock`;
   add `LockHeldError` (exit 0, first) + `ScheduleError` (exit 1) arms; TTY/no-color guard.
7. Tests per module + the CLI integration tests.

**Patterns to follow (with file paths):**
- Per-module single error class: `src/osspulse/schedule/errors.py` mirrors
  `src/osspulse/state/errors.py` / `delivery/errors.py` (delivery-6 memory).
- Atomic write for `--output`: reuse the `tempfile` in `target.parent` + `os.replace` pattern from
  `src/osspulse/state/json_store.py:save` (delivery-6 memory) so an unwritable parent fails with no
  partial file (AC-V2-002-016). Note: like delivery, do NOT `mkdir -p` the `--output` parent (fail-fast).
- CLI error boundary + exit contract: extend the existing `try/except` ladder in
  `src/osspulse/cli.py:run`; order `LockHeldError` before the exit-1 arms (ADR-005).
- Mockable OS seam: `CrontabClient` in `src/osspulse/schedule/crontab.py` mirrors the adapter style
  of `github/client.py` (inject a fake in tests).

**Gotchas:**
- `crontab -l` exits 1 with "no crontab for user" when empty — normalize to `""` in `read()`, don't
  treat it as an error (AC-V2-002-013 is specifically the *binary-missing* case).
- Round-trip byte-identity hinges on: add a leading `\n` only when appending to non-empty content
  that lacks a trailing newline; on remove, strip the exact inclusive marker region and nothing else.
- `LOCK_NB` is essential — without it a second run *blocks* instead of the required benign skip.
- Release the lock in a `finally` (context manager) even though the kernel would free it on exit —
  explicit `LOCK_UN` + `close` keeps a long-lived process (tests) correct.
- `sys.argv[0]` under `python -m osspulse` is the launcher path — document in README §Scheduling;
  `shutil.which("osspulse")` is the primary path for installed users.
- Reaffirm, don't rewrite, scheduler-cli-7 logging for AC-V2-002-018..020 — it is already
  cron-mail-friendly; add tests, not new logging behavior.
