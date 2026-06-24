# Design — 1-project-foundation

> Feature: OSS Pulse project foundation (skeleton + config loader + CLI stub).
> CLI tool, no HTTP API, no DB. Scope B per S1.

---

## 1. Sketch — Gap Analysis

**No critical gaps found.** Greenfield confirmed (no `src/`, no `pyproject.toml`,
no cross-spec dependencies).

Analyzed 33 ACs, 7 BRs, 3 INTs. Proposed: 0 HTTP endpoints (CLI tool), 0 DB tables
(JSON state is out of foundation scope), 6 source modules + 6 toolchain files, 2 key
flows.

Minor items (documented as assumptions, no S2 return needed):
- **openapi.yaml** does not apply to a CLI tool. Per R5 the file is created, but its
  content documents that there is no HTTP surface (see §4 and openapi.yaml rationale).
- **`WatchedRepo.full_name`** convenience property — resolved in ADR-003.
- **Validation order** in `load_config` — designed explicitly in §7.

---

## 2. Architecture Overview

**Style**: Linear pipeline + ports/adapters (hexagonal-lite), per `context/architecture.md`.

This feature builds the **skeleton + the S1 Config module only**. No business adapters
are implemented. The dependency graph for what foundation delivers:

```
cli.py (Typer, interface layer)
   │  calls
   ▼
config.py  ──raises──▶ ConfigError
   │  returns
   ▼
models.py (Config, WatchedRepo, RawItem, SummarizedItem, Digest)  ← pure data, no I/O

ports.py (Protocol stubs: GitHubClient, LLMClient, StateStore, SummaryCache, Delivery)
pipeline.py (stub: run_pipeline → NotImplementedError)
```

**Layer rules** (enforced):
- `models.py` — pure dataclasses, zero I/O imports.
- `ports.py` — `Protocol` definitions only; import from `models.py` allowed.
- `config.py` — reads filesystem + env; depends on `models.py`; raises `ConfigError`.
- `cli.py` — interface; depends on `config.py` + `pipeline.py`; owns the `ConfigError`
  → stderr boundary (BR-1-007).

**Cross-spec dependencies**: none (first feature). This feature *exports* the port
interfaces and domain models that every later spec (S2-Collector, S4-Summarizer, …)
will depend on. Those contracts are the durable output of this feature.

**Dependencies (runtime)**: `typer`, `python-dotenv`. `tomllib` is stdlib (3.11+).
`httpx`, `litellm`, `redis` are declared in `pyproject.toml` for future features but
NOT imported by foundation code.

---

## 3. Architecture Decision Records

### ADR-001: Config validation strategy — manual validation vs schema library

**Context**: `config.py` must validate a TOML structure against 12 distinct error
conditions (AC-1-016 → AC-1-027) and produce human-readable messages.

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A: Hand-written validation in `config.py` | Zero extra deps; full control over message wording (ACs require specific strings); trivial to test each branch | More code; must structure carefully to stay readable |
| B: Pydantic v2 | Declarative; less code; coercion built-in | Heavy dependency for foundation; default error messages don't match required AC strings (would need custom validators anyway); coercion could mask EC-05 (float→int) |

**Decision**: Option A. The ACs demand specific message substrings (e.g.
`"lookback_days must be ≥ 1"`) and explicit type rejection (EC-05: `7.5` must fail,
not coerce). Hand-written validation gives exact control and keeps foundation
dependency-light. Pydantic can be revisited if config grows complex.

**Consequences**: `config.py` contains a sequence of explicit validation functions.
Each maps to ≥1 AC, making coverage straightforward. No coercion surprises.

---

### ADR-002: Port interfaces — `typing.Protocol` vs `abc.ABC`

**Context**: `ports.py` defines 5 external-dependency contracts. They are stubs in
this feature (no implementation), but later specs implement them.

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A: `typing.Protocol` | Structural typing — adapters don't need to inherit; easy to write fakes for tests; no runtime coupling | No runtime enforcement unless `@runtime_checkable` |
| B: `abc.ABC` | Runtime enforcement of method implementation; familiar OOP | Adapters must explicitly inherit; tighter coupling; more boilerplate for fakes |

**Decision**: Option A (`Protocol`). Structural typing matches the ports/adapters
philosophy in `context/architecture.md` ("adapters depend on core models, not on each
other") and makes `FakeSummaryCache`-style test doubles trivial (no inheritance).

**Consequences**: Ports are duck-typed. Static type checkers verify conformance;
no runtime inheritance needed. Fakes in tests just implement the methods.

---

### ADR-003: `WatchedRepo` representation — split fields vs raw string

**Context**: A watchlist entry is `"owner/name"`. Downstream code (GitHub collector)
needs `owner` and `name` separately for API calls.

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A: `WatchedRepo(owner, name)` + `full_name` property | Parsed once at config time; downstream gets clean fields; validation localized | Slightly more code in parsing |
| B: Store raw `"owner/name"` string | Simplest storage | Every downstream consumer must re-parse + re-validate — violates DRY and fail-fast |

**Decision**: Option A. Parse and validate at config-load time (fail fast, BR-1-003),
expose `owner`/`name` as fields and `full_name` as a derived property. Downstream
never re-parses.

**Consequences**: `WatchedRepo` is a frozen dataclass with `owner: str`, `name: str`,
and `full_name` property returning `f"{owner}/{name}"`.

---

### ADR-004: Coverage gate scope — what to omit

**Context**: BR-1-006 requires stubs excluded from coverage. Gate is ≥ 80%
(`--cov-fail-under=80`). Need to decide exactly what is measured.

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A: Measure all of `src/osspulse/`, omit only `ports.py` + `pipeline.py` | Honest coverage of real logic; config.py held to a high bar | `cli.py` and `models.py` must also be tested to stay above 80% |
| B: Measure only `config.py` | Simplest to hit 80% | Hides untested cli.py wiring; weaker gate |

**Decision**: Option A. Omit `ports.py` and `pipeline.py` (pure stubs/interfaces).
Measure `config.py`, `cli.py`, `models.py`. This forces the CLI boundary (BR-1-007,
the riskiest code) to be tested, not just config.

**Consequences**: `[tool.coverage.run] omit` lists `src/osspulse/ports.py` and
`src/osspulse/pipeline.py`. Tests must cover cli.py and models.py too — acceptable
since both are small.

---

## 4. API Design

**No HTTP API.** This is a CLI tool. The "interface" surface is CLI commands:

| Command | Args / Options | Behaviour | ACs |
|---------|---------------|-----------|-----|
| `osspulse --help` | — | Print app help including `run` command; exit 0 | AC-1-028 |
| `osspulse run` | `--config PATH` (optional, default `config.toml`) | Load+validate config, then print "pipeline not yet implemented"; exit 0 on success | AC-1-030, AC-1-029 |
| `osspulse run` (bad config) | — | Print `Error: <msg>` to stderr; exit non-zero; no traceback | AC-1-031, AC-1-032 |
| `osspulse <unknown>` | — | Typer usage help to stderr; non-zero exit | AC-1-033 |

`openapi.yaml`: created per R5, but documents the absence of an HTTP surface (CLI
tool). It carries no paths — see the file's `info.description` and the rationale note.

**Public function contract** (`config.py`):
```
load_config(config_path: Path, env: Mapping[str, str] | None = None) -> Config
    raises ConfigError on any validation failure
```
`env` defaults to `os.environ`; injectable for tests (AC-1-021/022).

---

## 5. DB Schema

**No database.** State store is out of foundation scope (JSON file, future S3-State
feature). No tables, no migrations in this feature.

In-memory domain models (`models.py`):

```python
@dataclass(frozen=True)
class WatchedRepo:
    owner: str
    name: str
    @property
    def full_name(self) -> str: ...   # "owner/name"

@dataclass(frozen=True)
class Config:
    watched_repos: list[WatchedRepo]
    lookback_days: int = 7
    github_token: str = ""
    llm_provider: str | None = None
    llm_api_key: str | None = None

@dataclass(frozen=True)
class RawItem:        # stub for future collector
    repo: str
    item_type: str    # "issue" | "discussion" | "release"
    item_id: str
    title: str
    body: str
    url: str
    created_at: str

@dataclass(frozen=True)
class SummarizedItem:
    raw: RawItem
    summary: str

@dataclass(frozen=True)
class Digest:
    repo: str
    items: list[SummarizedItem]
```

---

## 6. Error Mapping

No HTTP status codes (CLI tool). Error contract is `ConfigError` → stderr + exit code.

| Condition | Exception | CLI behaviour | Exit code | AC |
|-----------|-----------|---------------|-----------|-----|
| Missing `[watchlist]` | `ConfigError("missing [watchlist] section")` | `Error: <msg>` → stderr | ≠0 | AC-1-016 |
| `repos = []` | `ConfigError("watchlist.repos must not be empty")` | stderr | ≠0 | AC-1-017 |
| Invalid repo format | `ConfigError("invalid repo '<x>': expected 'owner/name'")` | stderr | ≠0 | AC-1-018 |
| `lookback_days ≤ 0` | `ConfigError("lookback_days must be ≥ 1")` | stderr | ≠0 | AC-1-019 |
| `lookback_days` non-int | `ConfigError("lookback_days must be an integer")` | stderr | ≠0 | AC-1-020 |
| Corrupt TOML | `ConfigError("could not parse <path>: <reason>")` | stderr | ≠0 | AC-1-023 |
| Permission denied | `ConfigError("cannot read <path>: permission denied")` | stderr | ≠0 | AC-1-024 |
| Missing/empty `GITHUB_TOKEN` | `ConfigError("GITHUB_TOKEN is required")` | stderr | ≠0 | AC-1-021, AC-1-022 |
| Remote LLM, no key | `ConfigError("LLM provider '<p>' requires API key")` | stderr | ≠0 | AC-1-026 |
| `lookback_days > 365` | (no exception) | warning → stderr, continue | 0 | AC-1-025 |
| Duplicate repos | (no exception) | warning → stderr, dedupe | 0 | AC-1-013 |
| Unknown subcommand | Typer `UsageError` | usage → stderr | ≠0 | AC-1-033 |

**Boundary rule (BR-1-007)**: only `cli.py` converts `ConfigError` → stderr+exit.
`config.py` always raises; never prints, never calls `sys.exit`.

---

## 7. Sequence Flows

### Flow 1 — `load_config()` validation (fail-fast order)
```
load_config(config_path, env)
  1. env = env or os.environ; load_dotenv() to populate from .env if present
  2. read file:
       - not readable (PermissionError)  → ConfigError (AC-1-024)
       - read bytes, parse via tomllib:
           - TOMLDecodeError              → ConfigError (AC-1-023)
  3. validate [watchlist] section present → else ConfigError (AC-1-016)
  4. repos = watchlist.repos
       - missing or []                    → ConfigError (AC-1-017)
       - for each entry: regex match BR-1-003
           - no match                     → ConfigError naming entry (AC-1-018)
       - dedupe (order-preserving); if dupes → warn (AC-1-013)
  5. lookback_days (default 7 if absent — AC-1-012)
       - not int (bool/float/str)         → ConfigError (AC-1-020)
       - ≤ 0                              → ConfigError (AC-1-019)
       - > 365                            → warn, keep (AC-1-025)
  6. github_token = env["GITHUB_TOKEN"]
       - absent or "" (stripped)          → ConfigError (AC-1-021/022)
  7. llm: if [llm].provider set and not local (ollama):
       - api key env var absent           → ConfigError (AC-1-026)
       - ollama                           → ok, no key (AC-1-027)
  8. unknown keys ignored (AC-1-014)
  9. return Config(...)
```
Note: `bool` is a subclass of `int` in Python — explicitly reject `bool` for
`lookback_days` to avoid `True` passing as `1`.

### Flow 2 — CLI `run` boundary (BR-1-007)
```
osspulse run --config PATH
  try:
      cfg = load_config(PATH, os.environ)
  except ConfigError as e:
      typer.echo(f"Error: {e}", err=True)   # stderr
      raise typer.Exit(code=1)              # non-zero, no traceback
  typer.echo("osspulse: pipeline not yet implemented")  # stub (AC-1-030)
```

---

## 8. Edge Cases

All 15 ECs from requirements §5 are covered by ACs and the Flow 1 order above. Design
clarifications:
- **EC-05 / bool trap**: `lookback_days = true` in TOML parses to Python `True`.
  Because `isinstance(True, int)` is `True`, validation MUST check `type(x) is int`
  (or reject `bool` explicitly) — see Flow 1 step 5.
- **EC-08 empty token**: token is `.strip()`-checked; whitespace-only treated as empty.
- **EC-09 dedupe**: order-preserving (first occurrence wins), warning emitted once.
- **EC-15 unknown keys**: `tomllib` returns a dict; we read only known keys, never
  assert on extras.

---

## 9. Performance

Not performance-sensitive (config load runs once per invocation, files are tiny).
NFR: `mise install && uv sync` is the full setup; CI < 2 min. No caching, no async
in foundation. `python-dotenv` and `tomllib` reads are negligible.

---

## 10. Security

- **No secrets in repo (BR-1-001)**: `.gitignore` lists `.env` from first commit
  (AC-1-007). Only `.env.example` (placeholder values) and `config.example.toml`
  committed.
- **Token from env/.env only**: `config.py` reads `GITHUB_TOKEN` from the injected
  env mapping; never from the TOML file (so tokens can't be committed via config).
- **No token echo**: error messages reference `GITHUB_TOKEN` by name, never print its
  value. Warnings/logs MUST NOT include secret values.
- **Least privilege**: README documents `public_repo` read-only scope.
- **No network in foundation**: no outbound calls; nothing to exfiltrate.
- **Input treated as untrusted**: TOML parse wrapped; malformed input → `ConfigError`,
  never a raw traceback that could leak paths/stack (BR-1-007).

---

## 11. CMS UI

N/A — CLI tool, no UI, no Figma.

---

## 12. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Coverage gate fails due to stub files | MEDIUM | ADR-004: omit `ports.py`+`pipeline.py`; measure config.py/cli.py/models.py |
| `bool` passing as `int` for lookback_days | MEDIUM | Flow 1 step 5: `type() is int` check; explicit test (AC-1-020) |
| `ConfigError` traceback leaking to terminal | MEDIUM | BR-1-007 boundary in cli.py; test with `CliRunner` asserting stderr + no traceback |
| `omit` paths wrong → coverage miscount | LOW | Exact paths in pyproject.toml; verify in checkpoint |
| `.env` accidentally committed | HIGH→LOW | `.gitignore` from first commit (AC-1-007); checkpoint verifies |
| Port Protocol drift vs future adapters | LOW | Protocols are minimal + documented; future specs adapt |

---

## 13. Implementation Guide

### Recommended Order (dependency-respecting)
1. **Toolchain first**: `.mise.toml` → `pyproject.toml` (deps + ruff + pytest + coverage
   config) → `uv sync`. Nothing compiles without this.
2. **`models.py`** — pure dataclasses. No dependencies. (`WatchedRepo`, `Config`,
   `RawItem`, `SummarizedItem`, `Digest`.)
3. **`ports.py`** — 5 `Protocol` stubs. Depends on models. (Omitted from coverage.)
4. **`pipeline.py`** — single stub function `run_pipeline(config) -> None` raising
   `NotImplementedError`. (Omitted from coverage.)
5. **`config.py`** — `ConfigError` + `load_config()`. The core. Follow Flow 1 order
   exactly. Depends on models.
6. **`cli.py`** — Typer app + `run` command + ConfigError boundary (Flow 2).
7. **Tests** — `tests/test_config.py` (all AC-1-011→027), `tests/test_cli.py`
   (AC-1-028→033 with `CliRunner`), `tests/test_models.py` (WatchedRepo.full_name).
8. **CI** — `.github/workflows/ci.yml`.
9. **Templates + gitignore** — `.env.example`, `config.example.toml`, `.gitignore`.

### Patterns to Follow
- **Validation**: one small function per rule in `config.py` (e.g.
  `_validate_repos()`, `_validate_lookback()`, `_resolve_token()`), each maps to ACs
  — keeps coverage and readability high. File: `src/osspulse/config.py`.
- **CLI boundary**: single `try/except ConfigError` in the `run` command; use
  `typer.echo(..., err=True)` + `raise typer.Exit(1)`. File: `src/osspulse/cli.py`.
- **Ports as Protocol**: `class GitHubClient(Protocol): ...` with method signatures
  only (`...` body). File: `src/osspulse/ports.py`.
- **Tests**: inject `env` dict into `load_config` rather than monkeypatching
  `os.environ` where possible; use `typer.testing.CliRunner` for CLI tests, asserting
  `result.exit_code` and `result.stdout`/`result.stderr`. File: `tests/`.

### Gotchas
- `bool` is `int` subclass — reject explicitly for `lookback_days`.
- `tomllib.load` needs a **binary** file handle (`open(path, "rb")`).
- `load_dotenv()` does NOT override existing env vars by default — that's correct
  (real env wins over `.env`), matches AC-1-015.
- Coverage `omit` paths are relative to the coverage root; verify they match
  `src/osspulse/ports.py` and `src/osspulse/pipeline.py` exactly (ADR-004 / BR-1-006).
- `typer.Exit(code=1)` is the clean non-zero exit; do NOT call `sys.exit()` inside the
  command (Typer handles it) and do NOT let `ConfigError` propagate (would show
  traceback).
- Empty/whitespace token: `.strip()` before truthiness check (AC-1-022).
