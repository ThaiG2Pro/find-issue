# Progress — v2-cache-etag (ticket V2-007)

CR: add GitHub HTTP ETag conditional-request caching to the REST collector paths (rate-limit saving).
rigor=lite · scope=standard · test_scope=module · testcase_export=none.

## S1 — Req Intake ✅ DONE (analyst, 2026-07-10)
- `proposal.md` — Why / What / Capabilities / Impact / Non-Goals / Assumptions / 17 Edge Cases / Early Risk Flags / BRs / INTs / Structured Extract
- Initial spec deltas scaffolded: `specs/conditional-cache/`, `specs/github-collector/`, `specs/scheduler-cli/`
- STRIDE gate: SKIPPED (no new secret/PII/auth surface; reaffirmed token discipline as RISK-003)

## S2 — Func Spec ✅ DONE (analyst, 2026-07-10)
- 28 ACs (all CONFIRMED), 12 BRs (BR-V2-007-001..012), 5 INTs (INT-V2-007-001..005)
- `specs/conditional-cache/spec.md` — new capability: port + JsonFileETagStore + best-effort + atomic + null cache
- `specs/github-collector/spec.md` — ADDED: injected cache, first-page conditional, 304=empty, 200=record+paginate, GraphQL untouched
- `specs/scheduler-cli/spec.md` — MODIFIED per-repo isolation (build/inject/commit ordering) + ADDED config-gating + near-zero-budget reqs
- `tasks.md` — 4 impl groups + 3 checkpoints (2 mid, 1 final), layered port→collector→config/pipeline→tests
- CPP: `_glossary.md`, `_decisions.jsonl` (9), `_handoff.md` (5 sections), `_state.json` (enriched)
- `openspec validate --changes v2-cache-etag` → PASS
- spec-auditor: PENDING (run before presenting SPEC LOCK)

## S3 — Design ✅ DONE (architect, 2026-07-10)
- `design.md` — Sketch (no gaps) + 5 ADRs + Architecture / Data Schema / Error Mapping / 3 Sequence Flows / Edge Cases / Performance / Security / Risk Assessment / Implementation Guide
  - ADR-001 best-effort store (INVERT json_store corruption); ADR-002 in-memory set + durable commit + null cache; ADR-003 first-page-only 304=empty-delta (_classify 304→OK); ADR-004 crash-safe unguarded commit-after-mark_seen; ADR-005 set() only on present ETag
- No `openapi.yaml` — CLI tool, no HTTP API (R5 N/A)
- `tasks.md` — reaffirmed from S2: 15 tasks + 3 checkpoints (2 mid @2.2/4.2, 1 final @6.4), layered port→adapter→collector→config/pipeline→tests; every subtask has File + AC-IDs
- CPP: `_glossary.md` (+5 architect terms), `_decisions.jsonl` (+5 ADRs), `_handoff.md` overwritten (S3→S4, 5 sections), `_state.json` (phase_history+S3, gates.S3=passed, memory_writeback.architect=appended, next_action→approve s3)
- memory writeback: `memory/architect/v2-cache-etag.md` + `_index.md` (3 cross-spec lessons)
- `openspec validate` → PASS · cross-artifact-audit → 0 CRITICAL (28/28 ACs covered)

## S4 — Build ✅ DONE (developer, 2026-07-10)
- **New files**: `src/osspulse/cache/etag_store.py` (`JsonFileETagStore`), `tests/cache/test_etag_store.py`, `tests/github/test_conditional_requests.py`
- **Modified**: `src/osspulse/ports.py` (+ `ConditionalCache` Protocol + `_NullConditionalCache`), `src/osspulse/github/client.py` (conditional cache injection, `_request_with_retry` extra_headers, `_classify(304)→OK`, fetch_items/fetch_releases first-page conditional), `src/osspulse/pipeline.py` (`_build_etag_cache`, `commit()` unguarded after `_collect_all`), `src/osspulse/config.py` (`_validate_etag_cache`), `src/osspulse/models.py` (Config + 2 etag_cache fields), `tests/test_config.py` (+6 etag_cache tests), `tests/test_pipeline.py` (+10 ETag tests)
- **Tests**: 609 green (60 new), coverage 97% on touched modules (92–99%), ruff clean, secret-scan pass
- **RISK-001 tripwire**: `test_commit_not_called_on_auth_error_mid_loop` + `test_commit_called_exactly_once_after_collect_loop` — both pass
- **Deviation**: `_NullConditionalCache` in `ports.py` not `etag_store.py` (AC-2-015 boundary enforcement; design-compliant)
- CPP: `_handoff.md` overwritten (S4→S5), `_decisions.jsonl` (+3 S4 entries), `_glossary.md` (+2 S4 terms), `_state.json` updated, `dev-test-report.md` created
- `openspec change validate "v2-cache-etag"` → PASS (tasks all [x])

## S5 — QA ✅ DONE (qa, 2026-07-10)
- **qa-report.md** — S5 gate artifact: 0 bugs, 28/28 ACs independently verified, 609/609 tests pass
- **qa/spec_tc_gap_report.md** — 0 BOTH_MISS / 0 TC_MISS / 0 SHALLOW_TC / 0 DEV_MISS
- **Verified**: RISK-001 tripwire ✅, GraphQL untouched ✅, best-effort semantics ✅, token discipline ✅, two-flag gate ✅
- **Coverage** (touched modules): cache/etag_store 92%, github/client 99%, pipeline 93%, config 98% → 97% total
- **Decision**: GO — 0 Critical/High/Medium/Low bugs; all ACs covered; ruff clean
- CPP: `_handoff.md` overwritten (S5→S6), `_decisions.jsonl` (+5 QA entries), `_state.json` (gates.S5=passed, phase_history+S5)

## Next Action
🔍 S5 GO/NO-GO GATE required. `/agent swap` → sdlc → "approve s5" → orchestrator routes to developer `/s6 V2-007 v2-cache-etag`.
