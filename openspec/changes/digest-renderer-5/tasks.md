# Tasks — digest-renderer-5

> Dependency order: port (foundational) → constants + line builder → render function + adapter → exports → tests.
> Renderer is a PURE transform (no I/O); all tests are mockless. 2 checkpoints (mid-build + final).

## 1. Port (foundational contract)

- [ ] 1.1 Add `SummarizedItem` to the models import and define `DigestRenderer(Protocol)` with a single method `render(self, items: list[SummarizedItem], *, lookback_days: int) -> str`. Keep `Digest`/`RawItem` imports; do NOT change any existing Protocol.
  - File: `src/osspulse/ports.py`
  - _Requirements: AC-5-001, AC-5-010, INT-5-001_ (ADR-002)

## 2. Renderer constants + line builder (domain logic)

- [ ] 2.1 Add module constants `GROUP_ORDER = ["issue", "discussion", "release"]` and `GROUP_LABELS = {"issue": "Issue mới", "discussion": "Discussion", "release": "Release", "__other__": "Khác"}`. Import ONLY `osspulse.models` + stdlib — NO import of `osspulse.github`/`state`/`summarizer`/`cache`.
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-003, AC-5-006, AC-5-014_ (BR-5-004, BR-5-008, ADR-003/004)

- [ ] 2.2 Implement `_build_item_line(item: SummarizedItem) -> str`: start with `- #{item_id}`; append `"{title}"` only if `title` non-empty (AC-5-015); append `— {summary}` only if `summary.strip()` non-empty (AC-5-017); append `[link]({url})` only if `url` non-empty (AC-5-016); join present segments with single spaces; never raise (AC-5-018). Render field text as-is (no Markdown escaping — A-A4).
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-012, AC-5-015, AC-5-016, AC-5-017, AC-5-018_ (BR-5-007, BR-5-009)

## 3. Render function + adapter (domain + port impl)

- [ ] 3.1 Implement the pure `render(items: list[SummarizedItem], *, lookback_days: int) -> str` free function: group into `dict[repo] -> dict[group_key] -> list` preserving append/input order (unknown types → `"__other__"` bucket); emit `# OSS Pulse Digest`; for each repo in `sorted(grouped, key=str.lower)` emit `## {repo} — {lookback_days} ngày qua`; for each group key in `GROUP_ORDER + ["__other__"]` emit `### {label} ({count})` + item lines only when non-empty. NO `set` anywhere.
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-001, AC-5-004, AC-5-005, AC-5-006, AC-5-007, AC-5-010, AC-5-011, AC-5-013, AC-5-019, AC-5-020_ (BR-5-003, BR-5-004, BR-5-006, BR-5-010, ADR-003/004)

- [ ] 3.2 Handle empty input inside `render()`: when `items == []`, return a non-empty doc `# OSS Pulse Digest` + `No new items in the last {lookback_days} days` with no `##` section; never return `""`/whitespace-only.
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-008, AC-5-009_ (BR-5-005)

- [ ] 3.3 Add `class MarkdownDigestRenderer` implementing `DigestRenderer` structurally; its `render(self, items, *, lookback_days)` delegates to the free `render(...)`. No I/O methods on the class.
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-001, AC-5-002_ (ADR-001/002)

## 4. Package exports (interface seam)

- [ ] 4.1 Replace the empty `__init__.py` with public exports `render` and `MarkdownDigestRenderer` (`__all__`); mirror the `summarizer/__init__.py` export style.
  - File: `src/osspulse/render/__init__.py`
  - _Requirements: AC-5-001, INT-5-001_ (ADR-001)

## 5. CHECKPOINT — mid-build review

- [ ] 5.1 CHECKPOINT (human review gate — STOP): confirm renderer compiles, port + adapter + free function in place, no upstream imports. Run `ruff check src/osspulse/render src/osspulse/ports.py` and `ruff format --check`. Smoke-run `render([], lookback_days=7)` and one non-empty case in a REPL/scratch to eyeball the Markdown shape. Do NOT proceed to test authoring until the line/section format is confirmed against AC-5-012/013/014.
  - File: `src/osspulse/render/renderer.py`
  - _Requirements: AC-5-001, AC-5-012, AC-5-013, AC-5-014_

## 6. Tests (after the code they test)

- [ ] 6.1 Happy-path + format tests: non-empty list renders to non-empty `str` with `##` per repo and `- #id` per item (AC-5-001); canonical line byte-match `- #123 "Fix bug" — Handle null pointer. [link](https://gh/123)` (AC-5-012); repo header `## alpha/a — 7 ngày qua` (AC-5-013); group header `### Issue mới (3)` (AC-5-014).
  - File: `tests/test_render_format.py`
  - _Requirements: AC-5-001, AC-5-012, AC-5-013, AC-5-014_

- [ ] 6.2 Determinism tests: double render → byte-equal (AC-5-004, EC-006); shuffled-repo input → identical output, `## alpha/a` before `## zeta/b` (AC-5-005, EC-007); group order Issues→Discussions→Releases→Khác (AC-5-006, EC-014); within-group input order preserved `#123` before `#120` (AC-5-007, EC-008).
  - File: `tests/test_render_determinism.py`
  - _Requirements: AC-5-004, AC-5-005, AC-5-006, AC-5-007_

- [ ] 6.3 Empty-input + empty-section tests: `render([], lookback_days=7)` non-empty "No new items in the last 7 days", no `##` (AC-5-008); `result.strip()` non-empty, not `""` (AC-5-009); repo with no items → no section (AC-5-010, EC-015); item-type with no items → no `###` header (AC-5-011).
  - File: `tests/test_render_empty.py`
  - _Requirements: AC-5-008, AC-5-009, AC-5-010, AC-5-011_

- [ ] 6.4 Defensive-field + bucketing tests: empty title omits quoted title (AC-5-015); empty url omits `[link]` (AC-5-016); empty/whitespace summary omits `— summary` (AC-5-017); all-empty-except-id renders `- #1` without raising (AC-5-018, EC-002); unknown `item_type` under `### Khác (1)` (AC-5-019, EC-011); N input items → exactly N lines, duplicates both rendered (AC-5-020, EC-009); markdown-special/non-ASCII rendered as-is, no crash (EC-005).
  - File: `tests/test_render_defensive.py`
  - _Requirements: AC-5-015, AC-5-016, AC-5-017, AC-5-018, AC-5-019, AC-5-020_

- [ ] 6.5 STATIC import-isolation test: parse `src/osspulse/render/renderer.py` (and `__init__.py`) via `ast` / `importlib` module inspection and assert NO import of `osspulse.github`, `osspulse.state`, `osspulse.summarizer`, `osspulse.cache` (AC-5-003, EC-012). Mirror summarizer AC-4-021 static test.
  - File: `tests/test_render_import_isolation.py`
  - _Requirements: AC-5-002, AC-5-003_

## 7. CHECKPOINT — final gate

- [ ] 7.1 CHECKPOINT (human review gate — STOP): run full suite with coverage `pytest --cov=src/osspulse/render --cov-report=term-missing` (≥80% lines per stack.md; target ≥99% on the new pure module), `ruff check` + `ruff format --check` clean, and a security scan (`pip-audit` if available) — note no new dependency was added. Confirm all 20 ACs (AC-5-001..020) have an asserting test and the static import test passes. STOP and wait for user sign-off before S4→S5 handoff.
  - File: `tests/test_render_import_isolation.py`
  - _Requirements: AC-5-001, AC-5-002, AC-5-003, AC-5-004, AC-5-005, AC-5-006, AC-5-007, AC-5-008, AC-5-009, AC-5-010, AC-5-011, AC-5-012, AC-5-013, AC-5-014, AC-5-015, AC-5-016, AC-5-017, AC-5-018, AC-5-019, AC-5-020_
