# Implementation Plan: Delivery (S6) — delivery-6

## Overview
S6 Delivery — the terminal sink that writes the S5-rendered Markdown **string** to a file
(atomically) or stdout, selected by `[output]` config. Redesigns the `Delivery` port to
`deliver(content: str)` (D-1), adds two stdlib-only adapters + a `DeliveryError`, and adds
fail-fast `[output]` config validation. No HTTP API (ADR-005), no DB, no new dependency (RF-4).

Order follows the project layering: port/contract → error → adapters → config → exports → tests.
The S4→S6 CLI wiring (adapter selection + top-level `BrokenPipeError`/`DeliveryError` handlers)
is implemented here as wiring tasks (INT-6-003), per design Flow 3/4.

## Tasks

- [x] 1. Port & error contract (foundational)
  - [x] 1.1 Change the `Delivery` Protocol from `send(self, digest: Digest) -> None` to `deliver(self, content: str) -> None`; leave the `Digest`/`RawItem`/`SummarizedItem` import unless verified unused (ADR-001)
    - File: `src/osspulse/ports.py`
    - _Requirements: AC-6-001, AC-6-003_
  - [x] 1.2 Add `class DeliveryError(Exception)` with a docstring mirroring `StateError` (ADR-006)
    - File: `src/osspulse/delivery/errors.py`
    - _Requirements: AC-6-016, BR-6-009_

- [x] 2. File delivery adapter (atomic UTF-8 write)
  - [x] 2.1 Implement `FileDelivery(output_path)` with `deliver(content)`: `tempfile.mkstemp(dir=Path(output_path).parent)` → `os.fdopen(fd, "w", encoding="utf-8")` write+flush+`os.fsync` → `os.replace(tmp, target)` → `finally: os.unlink(tmp)` on failure. NO `mkdir`. Catch `OSError` → `DeliveryError(f"cannot write digest to {target}: {exc}")` naming the path (ADR-002, Flow 2)
    - File: `src/osspulse/delivery/file_delivery.py`
    - _Requirements: AC-6-004, AC-6-005, AC-6-006, AC-6-014, AC-6-015, AC-6-016, AC-6-017, AC-6-018, AC-6-019, AC-6-020, BR-6-003, BR-6-005, BR-6-009, BR-6-010, BR-6-011, BR-6-012_

- [x] 3. Stdout delivery adapter
  - [x] 3.1 Implement `StdoutDelivery(stream=None)` (default `sys.stdout`) with `deliver(content)`: write `content` + one `"\n"` + `flush`; write nothing else; does NOT catch `BrokenPipeError` (ADR-003, Flow 3)
    - File: `src/osspulse/delivery/stdout_delivery.py`
    - _Requirements: AC-6-007, AC-6-008, BR-6-004, BR-6-006_

- [x] 4. Checkpoint — Port & adapters review
  - 🔍 HUMAN REVIEW GATE — completed (S4 Session 1 verified)
  - Verify: `Delivery.deliver(content: str)` shape; atomic write uses `target.parent` temp (RF-1) + UTF-8 + no `mkdir`; stdout writes content+1 newline only and does not swallow `BrokenPipeError`; `DeliveryError` names the path; no import of `osspulse.render`/`models`/`github`/`summarizer`/`cache` in `delivery/`
  - _Requirements: AC-6-001, AC-6-002, AC-6-003, AC-6-004, AC-6-005, AC-6-007, AC-6-014_

- [x] 5. Config `[output]` section (fail-fast validation)
  - [x] 5.1 Add `output_destination: str = "file"` and `output_path: str = "./digest.md"` to the frozen `Config` dataclass (after `state_path`)
    - File: `src/osspulse/models.py`
    - _Requirements: AC-6-010, BR-6-007_
  - [x] 5.2 Add the `[output]` parse+validate step in `load_config` (after the `[state]` step): default `destination="file"`/`output_path="./digest.md"`; raise `ConfigError` on invalid `destination` and on empty `output_path` when `destination="file"`; pass both fields to `Config(...)` (ADR-004, Flow 1)
    - File: `src/osspulse/config.py`
    - _Requirements: AC-6-010, AC-6-011, AC-6-012, AC-6-013, BR-6-007, BR-6-008_

- [x] 6. Package exports
  - [x] 6.1 Export `FileDelivery`, `StdoutDelivery`, `DeliveryError` (replace the empty `__init__.py`)
    - File: `src/osspulse/delivery/__init__.py`
    - _Requirements: AC-6-001, AC-6-002_

- [x] 7. CLI/pipeline wiring (INT-6-003)
  - [x] 7.1 Construct the chosen adapter from config (`FileDelivery(cfg.output_path)` vs `StdoutDelivery()`) and call `.deliver(rendered_string)`; add top-level `except BrokenPipeError` (redirect stdout→devnull via `os.dup2`, clean exit, no stacktrace) and `except DeliveryError` (→ `Error: {e}` on stderr + `Exit(1)`) next to the existing `except ConfigError` (ADR-003/006, Flow 3/4)
    - File: `src/osspulse/cli.py`
    - _Requirements: AC-6-009, AC-6-016, INT-6-001, INT-6-002, INT-6-003_

- [x] 8. Unit tests — file delivery
  - [x] 8.1 Atomic write + UTF-8 round-trip (write to `tmp_path`, assert UTF-8 decode equals content incl. "Khác"); temp-then-replace observable (no partial target); idempotent overwrite (same content twice → byte-identical, not appended); different content fully replaces; "No new items" doc written verbatim
    - File: `tests/test_delivery_file.py`
    - _Requirements: AC-6-004, AC-6-005, AC-6-018, AC-6-019, AC-6-020_
  - [x] 8.2 Failure modes → `DeliveryError` (no stacktrace), existing target intact: missing parent dir (path named), permission denied, target is a directory, failed `os.replace` (monkeypatch) with temp cleaned up
    - File: `tests/test_delivery_file.py`
    - _Requirements: AC-6-006, AC-6-014, AC-6-015, AC-6-016, AC-6-017_

- [x] 9. Unit tests — stdout delivery
  - [x] 9.1 Writes content + exactly one trailing newline to the injected stream and nothing else (clean/pipeable); raises on a broken/closed stream (does not swallow `BrokenPipeError`)
    - File: `tests/test_delivery_stdout.py`
    - _Requirements: AC-6-007, AC-6-008, AC-6-009_

- [x] 10. Unit tests — config `[output]` validation
  - [x] 10.1 Absent `[output]` → defaults (`file`, `./digest.md`); valid file destination+path loaded; invalid `destination` (e.g. `"email"`) → `ConfigError`; empty `output_path` with `file` → `ConfigError`
    - File: `tests/test_config_output.py`
    - _Requirements: AC-6-010, AC-6-011, AC-6-012, AC-6-013_

- [x] 11. Unit tests — import isolation (STATIC)
  - [x] 11.1 Assert `delivery/*.py` import none of `osspulse.github`/`summarizer`/`cache`/`render` and reference no `Digest`/`SummarizedItem`/`RawItem` (static inspection; mirrors renderer AC-5-003)
    - File: `tests/test_delivery_isolation.py`
    - _Requirements: AC-6-002, AC-6-003_

- [x] 12. Checkpoint — Final coverage & security
  - 🔍 HUMAN REVIEW GATE — completed (S4 Session 2 + S5 QA verified)
  - Run the test suite → coverage ≥ 80% (R-COV-001); security self-check (no secrets/PII in `DeliveryError` messages or logs, R-SEC-001/002); confirm stdlib-only (no SMTP/HTTP, RF-4); confirm UTF-8 enforced everywhere (RF-3); confirm all 20 ACs (AC-6-001..020) covered by a test
  - _Requirements: AC-6-001 through AC-6-020_
