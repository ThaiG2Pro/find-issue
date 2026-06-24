# OSS Pulse — Project Foundation
## Requirements & Functional Specification

---

## S1 — Requirement Pack

### §1. Problem Statement

OSS Pulse là một CLI tool mới hoàn toàn (greenfield). Feature `project-foundation`
dựng nền móng kỹ thuật để mọi feature nghiệp vụ sau (GitHub Collector, Summarizer,
v.v.) có thể build trên đó mà không cần setup lại:

- Skeleton codebase đúng chuẩn (mise + uv + ruff + pytest) chạy được, test được, CI
  xanh.
- Port interfaces (Protocol stubs) cho tất cả external dependencies — không implement
  adapter thật, nhưng contract đã rõ.
- `config.py` implement thật: đọc `config.toml` + `.env`, validate watchlist và
  lookback_days, fail fast với message rõ khi thiếu/sai.
- CLI entrypoint `osspulse` với lệnh `run` stub (in thông báo "not yet implemented")
  — chứng minh wiring từ Typer → pipeline.

**Tiêu chí "feature xong"**: `osspulse --help` hiển thị docs; `uv run pytest` xanh
với coverage ≥ 80% trên config.py; GitHub Actions CI pass.

### §2. Scope

#### In Scope
- `pyproject.toml` — packaging, dependencies, ruff config, pytest config
- `.mise.toml` — Python 3.13 pin
- `src/osspulse/` skeleton theo đúng directory map trong `context/architecture.md`
- `src/osspulse/models.py` — domain dataclasses: `RawItem`, `SummarizedItem`,
  `Digest`, `Config`, `WatchedRepo`
- `src/osspulse/ports.py` — 5 Protocol stubs: `GitHubClient`, `LLMClient`,
  `StateStore`, `SummaryCache`, `Delivery`
- `src/osspulse/config.py` — implement thật: load, parse, validate config + env
- `src/osspulse/cli.py` — Typer app, lệnh `run` stub
- `tests/` — unit tests cho `config.py` (≥ 80% lines coverage)
- `.github/workflows/ci.yml` — lint + test + coverage gate
- `.env.example` — template secrets, không commit `.env`
- `config.example.toml` — template config
- `.gitignore` — gitignore `.env`, `__pycache__`, `.venv`, v.v.

#### Out of Scope
- Implement adapter thật (GitHub, LLM, Redis, file state)
- `pipeline.py` implement thật (chỉ stub)
- Bất kỳ business logic nào thuộc V1 feature khác (Collector, Summarizer, v.v.)
- Docker, docker-compose (V2)
- Redis adapter thật (chỉ `FakeSummaryCache` in-memory cho test)

### §3. Assumptions

#### [ASSUMED] Decisions — đã chốt với user

- `[ASSUMED]` Scope = B: skeleton + config.py implement thật. Không implement adapter
  GitHub/LLM/Redis. (Clarification Q1 → user chọn B)
- `[ASSUMED]` CI jobs = lint (ruff) + test + coverage gate ≥ 80%. Không có mypy/pyright
  ở foundation. (Clarification Q2 → user chọn B)
- `[ASSUMED]` Redis dev setup = interface + `FakeSummaryCache` in-memory cho test.
  Không có docker-compose hay mise redis plugin ở foundation. (Clarification Q3 →
  user chọn A)
- `[ASSUMED]` Unknown keys trong `config.toml` được bỏ qua (không báo lỗi). Mô hình
  strict parse sẽ làm config cũ không tương thích khi thêm field — bỏ qua là safe
  hơn cho tool CLI cá nhân.
- `[ASSUMED]` `lookback_days` tối đa 365 (1 năm). Vượt ngưỡng → warning, không fail
  cứng. Giá trị ≤ 0 → fail fast.
- `[ASSUMED]` Repo trùng lặp trong watchlist → deduplicate tự động, log warning.
- `[ASSUMED]` LLM key không bắt buộc khi validate config (có thể dùng Ollama local
  không cần key). Chỉ `GITHUB_TOKEN` là bắt buộc.

### §4. Constraints

#### Technical
- Python 3.13, managed by mise (`.mise.toml`)
- Package manager: uv, lockfile committed
- Lint/format: ruff (check + format)
- CLI: Typer
- No web framework, no DB server, no queue

#### Business
- Token không commit vào repo — đọc từ env / `.env` gitignored
- `GITHUB_TOKEN` scope: `public_repo` read-only (minimum privilege)

### §5. Edge Cases

| # | Category | Edge Case | Handling |
|---|---|---|---|
| EC-01 | Input boundary | `config.toml` thiếu section `[watchlist]` | Fail fast: `ConfigError: missing [watchlist] section` |
| EC-02 | Input boundary | `repos` là list rỗng `[]` | Fail fast: `ConfigError: watchlist.repos must not be empty` |
| EC-03 | Input boundary | Repo string sai format: `"react"`, `"face book/react"`, `""` | Fail fast: liệt kê từng entry sai với message rõ |
| EC-04 | Input boundary | `lookback_days = 0` hoặc âm | Fail fast: `ConfigError: lookback_days must be ≥ 1` |
| EC-05 | Input boundary | `lookback_days` là float (`7.5`) hoặc string (`"seven"`) | Fail fast: `ConfigError: lookback_days must be an integer` |
| EC-06 | Input boundary | `config.toml` bị corrupt / không parse được | Fail fast: re-raise với message human-readable, không raw traceback |
| EC-07 | State transition | `GITHUB_TOKEN` không có trong env lẫn `.env` | Fail fast: `ConfigError: GITHUB_TOKEN is required` |
| EC-08 | State transition | `GITHUB_TOKEN` là empty string `""` | Fail fast: treat empty string như không tồn tại |
| EC-09 | Data integrity | Repo trùng lặp trong watchlist | Deduplicate, log warning, tiếp tục |
| EC-10 | Data integrity | `lookback_days` > 365 | Log warning, tiếp tục (không fail cứng) |
| EC-11 | Permission | `config.toml` không đọc được (permission denied) | Fail fast với message rõ, không để `PermissionError` raw rò ra |
| EC-12 | Integration failure | LLM provider cấu hình nhưng LLM key không set | Fail fast: `ConfigError: LLM provider X requires API key` |
| EC-13 | UI/UX | `osspulse --help`, `osspulse run --help` | Typer tự generate — test kiểm tra exit code = 0 và stdout không rỗng |
| EC-14 | UI/UX | Bất kỳ `ConfigError` nào | In `Error: <message>` ra stderr, exit code ≠ 0, không raw traceback |
| EC-15 | Technical | `config.toml` có unknown keys | Bỏ qua silently (không strict parse) |

### §6. Open Questions
Không còn open questions — tất cả đã được clarify qua 3 câu hỏi.

### §7. Figma Design
Figma: N/A — CLI tool, không có UI.

---

## S2 — Functional Specification

### User Stories

#### US-1: Toolchain & Project Structure
**As a** developer **I want** a correctly structured project skeleton **So that** I can start implementing features without any setup friction.

#### US-2: Config Load & Validate
**As an** operator **I want** `osspulse` to validate my `config.toml` and environment on startup **So that** I get a clear error immediately if something is wrong, before any API call is made.

#### US-3: CLI Entrypoint
**As an** operator **I want** `osspulse run` to be available as a CLI command **So that** I have the entry point ready for future pipeline wiring.

---

### Acceptance Criteria

#### US-1: Toolchain & Project Structure

##### Happy Path

- AC-1-001 [CONFIRMED]: **Given** the repo is cloned **When** `mise install` is run **Then** Python 3.13.x is activated as the project runtime (version confirmed by `python --version`).

- AC-1-002 [CONFIRMED]: **Given** the repo is cloned **When** `uv sync` is run **Then** a `.venv` is created with all declared dependencies installed and `uv.lock` is present and committed.

- AC-1-003 [CONFIRMED]: **Given** the virtualenv is active **When** `ruff check src/ tests/` is run on the skeleton **Then** exit code is 0 (no lint errors).

- AC-1-004 [CONFIRMED]: **Given** the virtualenv is active **When** `ruff format --check src/ tests/` is run **Then** exit code is 0 (all files already formatted).

- AC-1-005 [CONFIRMED]: **Given** the virtualenv is active **When** `uv run pytest` is run **Then** all tests pass and overall line coverage of `src/osspulse/config.py` is ≥ 80%.

- AC-1-006 [CONFIRMED]: **Given** the directory `src/osspulse/` **When** inspected **Then** all required modules exist: `__init__.py`, `cli.py`, `config.py`, `models.py`, `pipeline.py`, `ports.py`, and sub-packages `github/`, `summarizer/`, `state/`, `cache/`, `render/`, `delivery/` each with an `__init__.py`.

- AC-1-007 [CONFIRMED]: **Given** the repo root **When** inspected **Then** `.env` is listed in `.gitignore` and no `.env` file (containing real secrets) is committed; `.env.example` and `config.example.toml` are committed as templates.

##### Error Path

- AC-1-008 [ASSUMED]: **Given** `ports.py` and `pipeline.py` are stub files (no logic) **When** pytest coverage is measured **Then** those files are excluded from the coverage report via `pyproject.toml` `[tool.coverage.run] omit` — preventing stubs from dragging coverage below 80%.

- AC-1-009 [CONFIRMED]: **Given** a CI push to any branch **When** the GitHub Actions workflow runs **Then** jobs execute in order: (1) `ruff check`, (2) `ruff format --check`, (3) `pytest --cov` with coverage gate ≥ 80%; any failure fails the workflow.

- AC-1-010 [ASSUMED]: **Given** the CI workflow **When** coverage is below 80% **Then** the `pytest` step exits non-zero and the workflow is marked failed (enforced via `--cov-fail-under=80`).

---

#### US-2: Config Load & Validate

##### Happy Path

- AC-1-011 [CONFIRMED]: **Given** a valid `config.toml` with `[watchlist] repos = ["facebook/react"] lookback_days = 7` and `GITHUB_TOKEN` set in env **When** `load_config(path, env)` is called **Then** it returns a `Config` object with `watched_repos = [WatchedRepo(owner="facebook", name="react")]`, `lookback_days = 7`, and `github_token` populated.

- AC-1-012 [ASSUMED]: **Given** a `config.toml` with `lookback_days` not set **When** `load_config()` is called **Then** `lookback_days` defaults to `7`.

- AC-1-013 [ASSUMED]: **Given** a `config.toml` with duplicate repos `["facebook/react", "facebook/react"]` **When** `load_config()` is called **Then** the returned `Config.watched_repos` has exactly 1 entry (deduplicated) and a warning is logged to stderr.

- AC-1-014 [ASSUMED]: **Given** a `config.toml` with unknown keys (e.g. `[watchlist] foo = "bar"`) **When** `load_config()` is called **Then** the unknown keys are silently ignored and no error is raised.

- AC-1-015 [ASSUMED]: **Given** a `.env` file containing `GITHUB_TOKEN=ghp_xxx` **When** `load_config()` is called **Then** the token is read from `.env` (via `python-dotenv`) when it is not already in the environment.

##### Error Path

- AC-1-016 [CONFIRMED]: **Given** `config.toml` is missing the `[watchlist]` section **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"missing [watchlist] section"`.

- AC-1-017 [CONFIRMED]: **Given** `[watchlist] repos = []` **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"repos must not be empty"`.

- AC-1-018 [CONFIRMED]: **Given** `repos` contains an invalid entry (e.g. `"react"`, `"face book/react"`, or `""`) **When** `load_config()` is called **Then** it raises `ConfigError` naming the invalid entry and stating the expected format `"owner/name"`.

- AC-1-019 [CONFIRMED]: **Given** `lookback_days = 0` or `lookback_days = -1` **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"lookback_days must be ≥ 1"`.

- AC-1-020 [CONFIRMED]: **Given** `lookback_days = 7.5` (float) or `lookback_days = "seven"` (string) **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"lookback_days must be an integer"`.

- AC-1-021 [CONFIRMED]: **Given** `GITHUB_TOKEN` is absent from both env and `.env` **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"GITHUB_TOKEN is required"`.

- AC-1-022 [CONFIRMED]: **Given** `GITHUB_TOKEN` is present but is an empty string `""` **When** `load_config()` is called **Then** it raises `ConfigError` with message containing `"GITHUB_TOKEN is required"` (empty string treated as absent).

- AC-1-023 [CONFIRMED]: **Given** `config.toml` is corrupt / not valid TOML **When** `load_config()` is called **Then** it raises `ConfigError` with a human-readable message (not a raw `TOMLDecodeError` traceback).

- AC-1-024 [CONFIRMED]: **Given** `config.toml` exists but is not readable (permission denied) **When** `load_config()` is called **Then** it raises `ConfigError` with a human-readable message (not a raw `PermissionError`).

- AC-1-025 [ASSUMED]: **Given** `lookback_days = 400` (> 365) **When** `load_config()` is called **Then** it returns a valid `Config` (does not raise) and emits a warning to stderr containing `"lookback_days"` and `"365"`.

- AC-1-026 [ASSUMED]: **Given** `[llm] provider = "openai"` is configured but no `OPENAI_API_KEY` in env **When** `load_config()` is called **Then** it raises `ConfigError` with message containing the provider name and `"requires API key"`.

- AC-1-027 [ASSUMED]: **Given** `[llm] provider = "ollama"` is configured (local, no key needed) **When** `load_config()` is called **Then** no `ConfigError` is raised for missing API key.

---

#### US-3: CLI Entrypoint

##### Happy Path

- AC-1-028 [CONFIRMED]: **Given** `osspulse` is installed **When** `osspulse --help` is run **Then** exit code is 0 and stdout contains the app name and a description of available commands including `run`.

- AC-1-029 [CONFIRMED]: **Given** `osspulse run --help` is run **Then** exit code is 0 and stdout documents the `run` command's options.

- AC-1-030 [CONFIRMED]: **Given** a valid `config.toml` and `GITHUB_TOKEN` in env **When** `osspulse run` is executed **Then** exit code is 0 and stdout contains a message indicating the pipeline is not yet implemented (stub behaviour).

##### Error Path

- AC-1-031 [CONFIRMED]: **Given** `config.toml` is missing or invalid **When** `osspulse run` is executed **Then** exit code is non-zero, stderr contains `"Error: "` followed by the `ConfigError` message, and no Python traceback is printed to the terminal.

- AC-1-032 [CONFIRMED]: **Given** `GITHUB_TOKEN` is absent **When** `osspulse run` is executed **Then** exit code is non-zero and stderr contains `"Error: GITHUB_TOKEN is required"` — no traceback.

- AC-1-033 [ASSUMED]: **Given** `osspulse` is invoked with an unknown sub-command (e.g. `osspulse foo`) **When** executed **Then** Typer prints usage help to stderr and exits with non-zero code.

---

### Business Rules

- BR-1-001 [CONFIRMED]: `GITHUB_TOKEN` MUST be read exclusively from environment variables or a gitignored `.env` file. It MUST NOT be hardcoded or appear in any committed file.

- BR-1-002 [CONFIRMED]: `GITHUB_TOKEN` is the only credential that is always required. LLM API keys are required only when a remote LLM provider (non-local) is configured.

- BR-1-003 [CONFIRMED]: A repo entry in the watchlist MUST match the pattern `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$`. Any entry that does not match is a hard validation error.

- BR-1-004 [CONFIRMED]: `lookback_days` MUST be a positive integer (≥ 1). Values ≤ 0 or non-integer types are hard errors. Values > 365 are soft warnings only.

- BR-1-005 [ASSUMED]: Duplicate repos in the watchlist are silently deduplicated (order-preserving, first occurrence wins). A warning is emitted to stderr.

- BR-1-006 [CONFIRMED]: `ports.py` and `pipeline.py` at foundation stage MUST be excluded from coverage measurement. They contain only interface definitions and stubs — no executable logic to test.

- BR-1-007 [CONFIRMED]: All `ConfigError` exceptions MUST be caught at the CLI boundary (in `cli.py`), printed as `Error: <message>` to stderr, and result in a non-zero exit code. Raw tracebacks MUST NOT reach the terminal.

---

### Integration Points

- INT-1-001 [CONFIRMED]: `cli.py` → `config.py` — CLI calls `load_config()` before invoking any pipeline logic; a `ConfigError` here terminates the run immediately.
- INT-1-002 [CONFIRMED]: `config.py` → `.env` file — loaded via `python-dotenv` (`load_dotenv()`) before reading env vars; `.env` is gitignored.
- INT-1-003 [CONFIRMED]: GitHub Actions CI → `pyproject.toml` — CI reads ruff and pytest configuration from `pyproject.toml`; no separate config files for tooling.

---

### Non-functional Requirements

- **Developer experience**: `mise install && uv sync` is the complete setup. No other steps required.
- **CI speed**: The CI workflow (lint + test + coverage) MUST complete in < 2 minutes on a cold runner for the skeleton (no external API calls, no large dependencies beyond the declared set).
- **Security**: No token or secret appears in any committed file. `.env` is gitignored from the first commit.

### Figma Design
Figma: N/A — CLI tool, no UI.

---

## _Structured Extract

### AC List
- AC-1-001 [CONFIRMED]: `mise install` activates Python 3.13.x
- AC-1-002 [CONFIRMED]: `uv sync` creates `.venv` + `uv.lock` committed
- AC-1-003 [CONFIRMED]: `ruff check` exits 0 on skeleton
- AC-1-004 [CONFIRMED]: `ruff format --check` exits 0 on skeleton
- AC-1-005 [CONFIRMED]: `uv run pytest` passes, config.py coverage ≥ 80%
- AC-1-006 [CONFIRMED]: All required modules and sub-packages exist under `src/osspulse/`
- AC-1-007 [CONFIRMED]: `.env` in `.gitignore`; `.env.example` and `config.example.toml` committed
- AC-1-008 [ASSUMED]: `ports.py` and `pipeline.py` excluded from coverage via `pyproject.toml`
- AC-1-009 [CONFIRMED]: CI jobs run in order: ruff check → ruff format → pytest+cov; any failure = workflow fail
- AC-1-010 [ASSUMED]: CI fails when coverage < 80% (`--cov-fail-under=80`)
- AC-1-011 [CONFIRMED]: Valid config + token → returns `Config` object with correct fields
- AC-1-012 [ASSUMED]: `lookback_days` omitted → defaults to 7
- AC-1-013 [ASSUMED]: Duplicate repos → deduplicated + warning to stderr
- AC-1-014 [ASSUMED]: Unknown config keys → silently ignored
- AC-1-015 [ASSUMED]: Token read from `.env` via `python-dotenv` when not in env
- AC-1-016 [CONFIRMED]: Missing `[watchlist]` section → `ConfigError`
- AC-1-017 [CONFIRMED]: `repos = []` → `ConfigError`
- AC-1-018 [CONFIRMED]: Invalid repo format → `ConfigError` naming the entry
- AC-1-019 [CONFIRMED]: `lookback_days ≤ 0` → `ConfigError`
- AC-1-020 [CONFIRMED]: `lookback_days` float or string → `ConfigError`
- AC-1-021 [CONFIRMED]: `GITHUB_TOKEN` absent → `ConfigError`
- AC-1-022 [CONFIRMED]: `GITHUB_TOKEN = ""` → `ConfigError`
- AC-1-023 [CONFIRMED]: Corrupt TOML → `ConfigError` (human-readable)
- AC-1-024 [CONFIRMED]: Permission denied on config file → `ConfigError` (human-readable)
- AC-1-025 [ASSUMED]: `lookback_days > 365` → warning (no error)
- AC-1-026 [ASSUMED]: Remote LLM provider set + no API key → `ConfigError`
- AC-1-027 [ASSUMED]: Ollama provider set + no API key → no error
- AC-1-028 [CONFIRMED]: `osspulse --help` → exit 0 + lists `run`
- AC-1-029 [CONFIRMED]: `osspulse run --help` → exit 0 + documents options
- AC-1-030 [CONFIRMED]: `osspulse run` (valid config) → exit 0 + stub message
- AC-1-031 [CONFIRMED]: Invalid config → exit non-zero + `Error: <msg>` to stderr, no traceback
- AC-1-032 [CONFIRMED]: Missing token → exit non-zero + `Error: GITHUB_TOKEN is required`
- AC-1-033 [ASSUMED]: Unknown subcommand → Typer usage help + non-zero exit

### Business Rules
- BR-1-001 [CONFIRMED]: Token MUST come from env / gitignored `.env` only
- BR-1-002 [CONFIRMED]: Only `GITHUB_TOKEN` always required; LLM key conditional on provider
- BR-1-003 [CONFIRMED]: Repo must match `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$`
- BR-1-004 [CONFIRMED]: `lookback_days` must be int ≥ 1; > 365 = warning only
- BR-1-005 [ASSUMED]: Duplicate repos deduplicated (first occurrence, order-preserving) + warning
- BR-1-006 [CONFIRMED]: `ports.py` and `pipeline.py` stubs excluded from coverage
- BR-1-007 [CONFIRMED]: All `ConfigError` caught at CLI boundary → stderr + non-zero exit

### Integration Points
- INT-1-001 [CONFIRMED]: `cli.py` → `config.py` (`load_config()`)
- INT-1-002 [CONFIRMED]: `config.py` → `.env` (python-dotenv)
- INT-1-003 [CONFIRMED]: GitHub Actions CI → `pyproject.toml` (single source for tool config)

### Risk Flags
- RISK-001: Coverage gate with stub files — mitigated by BR-1-006 (explicit omit in pyproject.toml)
- RISK-002: Token leakage via committed `.env` — mitigated by BR-1-001 + AC-1-007 (gitignore from first commit)

### Metadata
```
ticket_id: 1
feature_slug: project-foundation
phase: S2
domain: infrastructure
has_figma: false
actors: [developer, operator]
ac_count: 33
ac_confirmed: 22
ac_assumed: 11
ac_missing: 0
ac_unclear: 0
br_count: 7
int_count: 3
```
