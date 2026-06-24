# Tasks — 1-project-foundation

> Implementation plan. Dependency order: toolchain → models → ports → pipeline stub →
> config → CLI → tests → CI. Two checkpoints (mid-build + final).
> CLI tool, no HTTP API, no DB.

---

## Task 1: Toolchain & project scaffolding

- [x] 1.1 Create `.mise.toml` pinning Python 3.13
  - File: `.mise.toml`
  - Pin `[tools] python = "3.13"`; verify `mise install` activates 3.13.x
  - _Requirements: AC-1-001_

- [x] 1.2 Create `pyproject.toml` (packaging, deps, tool config)
  - File: `pyproject.toml`
  - `[project]` name=osspulse, requires-python=">=3.13"; deps: `typer`, `python-dotenv`; declare (not import) `httpx`, `litellm`, `redis` for future use; dev deps: `pytest`, `pytest-cov`, `ruff`
  - `[project.scripts] osspulse = "osspulse.cli:app"`
  - `[tool.ruff]` lint+format config; `[tool.pytest.ini_options]`; `[tool.coverage.run] source=["osspulse"]`, `omit=["src/osspulse/ports.py","src/osspulse/pipeline.py"]`; `[tool.coverage.report] fail_under=80`
  - _Requirements: AC-1-002, AC-1-008, AC-1-010, BR-1-006, INT-1-003_

- [x] 1.3 Create repo hygiene files
  - File: `.gitignore`
  - Ignore `.env`, `.venv`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `dist/`
  - _Requirements: AC-1-007, BR-1-001_

- [x] 1.4 Create config + env templates
  - File: `.env.example`
  - File: `config.example.toml`
  - `.env.example`: `GITHUB_TOKEN=` placeholder + optional LLM key comment; `config.example.toml`: `[watchlist] repos = ["facebook/react"]` + `lookback_days = 7` + commented `[llm]` block
  - _Requirements: AC-1-007_

- [x] 1.5 Run `uv sync` and verify environment
  - File: `uv.lock` (generated, committed)
  - Confirm `.venv` created, deps installed, `uv.lock` present
  - _Requirements: AC-1-002_

---

## Task 2: Domain models

- [x] 2.1 Implement domain dataclasses
  - File: `src/osspulse/models.py`
  - `WatchedRepo(owner, name)` frozen dataclass + `full_name` property; `Config(watched_repos, lookback_days=7, github_token="", llm_provider=None, llm_api_key=None)`; `RawItem`, `SummarizedItem`, `Digest` per design.md §5
  - _Requirements: AC-1-011, AC-1-006_

- [x] 2.2 Create package `__init__.py` files
  - File: `src/osspulse/__init__.py`
  - File: `src/osspulse/github/__init__.py`, `src/osspulse/summarizer/__init__.py`, `src/osspulse/state/__init__.py`, `src/osspulse/cache/__init__.py`, `src/osspulse/render/__init__.py`, `src/osspulse/delivery/__init__.py`
  - Empty packages establishing the directory map from `context/architecture.md`
  - _Requirements: AC-1-006_

---

## Task 3: Port interfaces (stubs)

- [x] 3.1 Define 5 Protocol port interfaces
  - File: `src/osspulse/ports.py`
  - `GitHubClient`, `LLMClient`, `StateStore`, `SummaryCache`, `Delivery` as `typing.Protocol` with method signatures only (`...` bodies) per ADR-002
  - Excluded from coverage (BR-1-006)
  - _Requirements: AC-1-006, AC-1-008, BR-1-006_

---

## Task 4: Pipeline stub

- [x] 4.1 Create pipeline stub
  - File: `src/osspulse/pipeline.py`
  - `run_pipeline(config: Config) -> None` raising `NotImplementedError` (or returning a stub message); excluded from coverage (BR-1-006)
  - _Requirements: AC-1-006, AC-1-008, BR-1-006_

---

## ⛔ CHECKPOINT 1 — Skeleton review (mid-build)

**STOP. Human review required before proceeding.**
- [x] CP1.1 `mise install` → Python 3.13.x active (AC-1-001)
- [x] CP1.2 `uv sync` → `.venv` + `uv.lock` committed (AC-1-002)
- [x] CP1.3 `ruff check src/` and `ruff format --check src/` → exit 0 (AC-1-003, AC-1-004)
- [x] CP1.4 Directory map complete: all modules + sub-packages present (AC-1-006)
- [x] CP1.5 `.gitignore` includes `.env`; templates committed (AC-1-007)
- [x] CP1.6 Verify `[tool.coverage.run] omit` paths match `ports.py` + `pipeline.py` exactly (BR-1-006)
- _Requirements: AC-1-001, AC-1-002, AC-1-003, AC-1-004, AC-1-006, AC-1-007, BR-1-006_

---

## Task 5: Config loader (core)

- [x] 5.1 Define `ConfigError` exception
  - File: `src/osspulse/config.py`
  - `class ConfigError(Exception)` — raised on all validation failures
  - _Requirements: AC-1-016, BR-1-007_

- [x] 5.2 Implement file read + TOML parse with error wrapping
  - File: `src/osspulse/config.py`
  - Open `rb`, parse via `tomllib`; wrap `PermissionError` → ConfigError (AC-1-024); wrap `TOMLDecodeError` → ConfigError human-readable (AC-1-023)
  - _Requirements: AC-1-023, AC-1-024_

- [x] 5.3 Implement watchlist validation
  - File: `src/osspulse/config.py`
  - `_validate_repos()`: missing `[watchlist]` (AC-1-016); empty repos (AC-1-017); regex `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` per entry (AC-1-018, BR-1-003); dedupe + warn (AC-1-013, BR-1-005); parse into `WatchedRepo`
  - _Requirements: AC-1-016, AC-1-017, AC-1-018, AC-1-013, BR-1-003, BR-1-005_

- [x] 5.4 Implement lookback_days validation
  - File: `src/osspulse/config.py`
  - `_validate_lookback()`: default 7 if absent (AC-1-012); reject non-int incl. bool via `type() is int` (AC-1-020); `≤ 0` error (AC-1-019); `> 365` warn only (AC-1-025, BR-1-004)
  - _Requirements: AC-1-012, AC-1-019, AC-1-020, AC-1-025, BR-1-004_

- [x] 5.5 Implement token + LLM key resolution
  - File: `src/osspulse/config.py`
  - `load_dotenv()`; resolve `GITHUB_TOKEN` from env, `.strip()`, empty→error (AC-1-021, AC-1-022); LLM: remote provider requires key (AC-1-026), ollama no key (AC-1-027); ignore unknown keys (AC-1-014)
  - _Requirements: AC-1-021, AC-1-022, AC-1-026, AC-1-027, AC-1-014, AC-1-015, BR-1-001, BR-1-002, INT-1-002_

- [x] 5.6 Implement `load_config()` orchestration
  - File: `src/osspulse/config.py`
  - Compose 5.2–5.5 in fail-fast order per design.md §7 Flow 1; return `Config`
  - _Requirements: AC-1-011_

---

## Task 6: CLI entrypoint

- [x] 6.1 Implement Typer app + `run` command with ConfigError boundary
  - File: `src/osspulse/cli.py`
  - `app = typer.Typer()`; `run(--config PATH=config.toml)`; try `load_config` except `ConfigError` → `typer.echo(f"Error: {e}", err=True)` + `raise typer.Exit(1)`; on success print stub message (AC-1-030); no traceback (BR-1-007)
  - _Requirements: AC-1-028, AC-1-029, AC-1-030, AC-1-031, AC-1-032, AC-1-033, BR-1-007, INT-1-001_

---

## Task 7: Tests

- [x] 7.1 Test domain models
  - File: `tests/test_models.py`
  - `WatchedRepo.full_name` returns `"owner/name"`; dataclasses construct correctly
  - _Requirements: AC-1-011_

- [x] 7.2 Test config happy paths
  - File: `tests/test_config.py`
  - Valid config → correct `Config` (AC-1-011); default lookback (AC-1-012); dedupe (AC-1-013); unknown keys ignored (AC-1-014); token from `.env` (AC-1-015)
  - _Requirements: AC-1-011, AC-1-012, AC-1-013, AC-1-014, AC-1-015_

- [x] 7.3 Test config error paths
  - File: `tests/test_config.py`
  - Missing watchlist (016); empty repos (017); bad repo format (018); lookback ≤0 (019); lookback non-int incl. bool/float/str (020); missing token (021); empty token (022); corrupt TOML (023); permission denied (024); lookback>365 warns (025); remote LLM no key (026); ollama no key ok (027)
  - _Requirements: AC-1-016, AC-1-017, AC-1-018, AC-1-019, AC-1-020, AC-1-021, AC-1-022, AC-1-023, AC-1-024, AC-1-025, AC-1-026, AC-1-027_

- [x] 7.4 Test CLI with CliRunner
  - File: `tests/test_cli.py`
  - `--help` exit 0 + lists run (028); `run --help` (029); `run` valid → exit 0 + stub msg (030); bad config → exit≠0 + `Error:` on stderr + no traceback (031); missing token → exit≠0 + message (032); unknown subcommand → usage + exit≠0 (033)
  - _Requirements: AC-1-028, AC-1-029, AC-1-030, AC-1-031, AC-1-032, AC-1-033_

---

## Task 8: CI workflow

- [x] 8.1 Create GitHub Actions CI workflow
  - File: `.github/workflows/ci.yml`
  - Trigger push + pull_request; setup via mise/uv; jobs in order: `ruff check` → `ruff format --check` → `pytest --cov --cov-fail-under=80`; any failure fails workflow
  - _Requirements: AC-1-009, AC-1-010, AC-1-005_

---

## ⛔ CHECKPOINT 2 — Final review (test:cov + security scan)

**STOP. Human review required. This is the final gate.**
- [x] CP2.1 `uv run pytest --cov` → all pass, coverage ≥ 80% on measured files (AC-1-005, AC-1-010)
- [x] CP2.2 All 33 ACs verified mapped to passing tests or checkpoint checks
- [x] CP2.3 `ruff check` + `ruff format --check` → exit 0 (AC-1-003, AC-1-004)
- [ ] CP2.4 CLI manual smoke: `osspulse --help`, `osspulse run` with/without valid config (AC-1-028→032)
- [x] CP2.5 **Security scan**: confirm no secret committed; `.env` gitignored; no token value in code/logs/error messages (BR-1-001)
- [x] CP2.6 `ConfigError` never produces a raw traceback at CLI (BR-1-007)
- [x] CP2.7 Coverage `omit` correctly excludes `ports.py` + `pipeline.py` (BR-1-006)
- _Requirements: AC-1-005, AC-1-009, AC-1-010, AC-1-003, AC-1-004, BR-1-001, BR-1-006, BR-1-007_
