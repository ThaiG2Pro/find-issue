# Lessons Learned — AI-Augmented SDLC

> Append a block after each retro. Newest first.

---

## digest-renderer-5 · 2026-06-29

**Type:** feature (full S1→S6) · S5 Digest Renderer — pure `SummarizedItem[] → Markdown` transform (`osspulse.render`)
**Health Score:** 92/100 · 0 gate violations · **0 loop-backs** · QA GO on first pass

### Gate Compliance: 5/5 passed (0 violations)
| Gate | Output | Result |
|------|--------|--------|
| S1→S2 | proposal + 20 ACs, 15 edge cases, 3 clarifications resolved | ✅ |
| 🔒 S2 SPEC LOCK | spec-auditor PASS + openspec validate + no TBD; convergence stable 3/3 (recorded retroactively — see friction) | ✅ |
| 🔍 S3 DESIGN REVIEW | cross-artifact-audit 0 CRITICAL (1 MEDIUM fixed), 5 ADRs, 13 tasks, 20/20 ACs covered; convergence 3/3 | ✅ |
| S4→S5 | 220/220 tests, **100%** coverage on `osspulse.render` (49/49 stmts), ruff clean, 0 deviations | ✅ |
| S5→S6 | QA GO, 0 bugs all severities, 20/20 ACs independently re-verified | ✅ |

### AI Performance
| Metric | Target | Actual |
|--------|--------|--------|
| AI-detectable bugs caught by AI (QA) | ≥90% | n/a — 0 bugs surfaced; QA independently re-verified determinism / import-isolation / RF-2 |
| Logic bugs missed | 0 | 0 (QA adversarial seeds + 10k stress found none) |
| Spec adherence (unauthorized deviations) | 100% | 100% — all 5 ADRs followed; ADR-005 (no openapi) is documented, not unauthorized |
| Coverage on new code | ≥80% | **100%** ✅ |
| Guards fired (pipeline-guard/cpp-guard) | ✅ | ✅ — guard CAUGHT 2 inherited `_state.json` defects (below) |

### What worked
- **Determinism (RF-1) nailed end-to-end** — dict-of-dict grouping, zero `set` usage, byte-equal double-render verified under adversarial seeds + a 10k-item stress run. Pure-transform design made the module mockless and 100%-coverable.
- **Expensive upstream gates held again** — no S5→S3 (20×) or S5→S2 (25×) loop-backs; spec locked once and held through build + QA. Full-rigor convergence (stable_rounds=3) on S2+S3 paid off for the 3rd consecutive change.
- **QA re-verified the highest-risk items independently** (determinism, import-isolation, RF-2) rather than trusting the dev report — counts matched, 220/220.
- Only rework was two **test-assertion technique** fixes inside S4 (em-dash false-positive scoping; `#id` token extraction) — caught and fixed *within* S4, never a gate loop-back.

### Process friction — `_state.json` integrity (THIRD consecutive recurrence)
- `pipeline-guard` again caught inherited state defects from a prior turn: non-canonical `gates` format + a missing `rigor=full` convergence record. The orchestrator repaired state (retroactive convergence verification is legitimate against a frozen/locked spec) and the gate then passed. **This is the same class as state-store-3 #1/#2 and summarizer-llm-4 #1 — `_state.json` format/convergence drift has now bitten THREE changes in a row.** The guard is the real backstop; the writer is the root cause.
- **EC-004 (10k-item stress) had no dedicated test at S4** — QA had to add a spot-check to cover the largest-N path before it could sign GO. Scale cases for aggregating transforms are slipping past the dev self-test.

### Action items (carry forward)
1. **Normalize-on-load / `doctor` fixer for `_state.json`** — auto-upgrade `gates` to the canonical `"passed"` string form and back-fill `convergence` for already-approved convergence gates at `rigor=full`, at session start, instead of surfacing as an exit-1 at the next gate. **This is the promotion of state-store-3 #1 (schema-validated writer) — three changes now justify building it.** *[Tooling / Orchestration core]*
2. **Add a "scale/stress spot-check for aggregating/looping transforms" line to the developer S4 self-test checklist** — so EC-style large-N cases (EC-004) are covered before QA has to backfill them. *[Developer steering]*
3. **Follow-on change: wire `MarkdownDigestRenderer` into the CLI pipeline** (S6 Delivery / S7) — the renderer ships production-ready but UNWIRED; `osspulse run` does not yet surface it. (Same dormant-feature pattern as summarizer-llm-4's `summarize_items`.) *[Analyst → next pipeline]*

### Fragile areas to watch
- **Two dormant, production-ready modules now unwired**: `summarize_items` (S4) and `MarkdownDigestRenderer` (S5). Both are tested + complete but not called from `pipeline.py`. The next high-value change is the CLI wiring that activates them — track so they don't rot.
- **`_state.json` remains the highest-risk integrity surface** — many writers, no schema guard; a single format drift halts the pipeline at the next gate (action item #1).
- **ADR-005 (no openapi)** is a deliberate deviation for a no-HTTP CLI — re-evaluate only if a future change adds an API surface.

---

## summarizer-llm-4 · 2026-06-25

**Type:** feature (full S1→S6) · S4 Summarizer (LLM) — LiteLLM + Redis cache-aside
**Health Score:** 90/100 · 0 gate violations · **0 loop-backs** · QA GO on first pass

### Gate Compliance: 5/5 passed (0 violations)
| Gate | Output | Result |
|------|--------|--------|
| S1→S2 | proposal + 22 ACs (15 CONFIRMED/7 ASSUMED) | ✅ |
| 🔒 S2 SPEC LOCK | spec-auditor PASS + openspec validate + 22/22 CONFIRMED, RF-1 acknowledged | ✅ |
| 🔍 S3 DESIGN REVIEW | cross-artifact-audit 0 CRITICAL, 8 ADRs, 17 tasks | ✅ |
| S4→S5 | 164/164 tests, 99.38% coverage, ruff clean | ✅ |
| S5→S6 | QA GO, 0 Critical/High (3 LOW non-blockers) | ✅ |

### AI Performance
| Metric | Target | Actual |
|--------|--------|--------|
| AI-detectable bugs caught by AI (QA) | ≥90% | 1/1 (100%) — BUG-001 shallow assertion caught by QA review |
| Logic bugs missed | 0 | 0 |
| Spec adherence (unauthorized deviations) | 100% | 100% — 1 deviation (DEV-001) but documented + accepted, not unauthorized |
| Coverage on new code | ≥80% | 99.38% ✅ |
| Guards fired (pipeline-guard/cpp-guard) | ✅ | ✅ — pipeline-guard CAUGHT the premature phase advance (below) |

### What worked
- **Expensive upstream gates held again** — no S5→S3 (20×) or S5→S2 (25×) loop-backs; QA returned GO on first pass. The full-rigor convergence on S2+S3 (stable_rounds=3) paid off.
- **RF-1 (HIGH data-egress) handled cleanly end-to-end**: acknowledged at SPEC LOCK → ADR-008 (title+body only) at S3 → asserted by QA at S5 (grep + structural test, 0 other network calls) → README privacy disclosure shipped at S6. Risk tracked across all phases via active_concerns, exactly as designed.
- **DEV-001 deviation done right**: dev caught that `litellm.exceptions.*` subclass `openai.APIError` at runtime, used the correct base, documented it, and QA wrote guard tests that raise REAL litellm exceptions — so a future litellm hierarchy change fails loudly.
- Independent QA re-ran the whole suite (didn't trust dev report); counts matched.

### Process friction — TWO recurring/new failure modes
1. **QA subagent pre-stamped the S5 gate** (`gates.S5 = PASS`) and advanced `current_phase` → S6 itself, before the orchestrator ran the gate. `pipeline-guard --gate S5` then refused with "OUT OF ORDER: you are at S6, not S5." Orchestrator rolled state back to S5, ran the gate properly, and approved only after user sign-off. **This is exactly state-store-3 Action Item #3 recurring** ("restrict `_state.json` gate writes to the orchestrator") — role agents are STILL stamping gates. The guard caught it, but the subagent prompt/contract is the root cause.
2. **Developer subagent connection dropped mid-S6** after 23 tool uses — `.env.example` + `README.md` were written but `release.md` and `openspec archive` were not. Recovered by inspecting the filesystem for completed work and spawning a fresh developer scoped to ONLY the remaining steps (no SendMessage available to the orchestrator to resume in-context). Idempotent, resumable phase design made this safe.

### Action items (carry forward)
1. **Enforce "orchestrator-only gate writes" in the role subagent prompts** — analyst/architect/dev/qa templates must say: append to `phase_history`/`next_action` only; NEVER write `gates.*` or change `current_phase`. (Repeat of state-store-3 #3 — promote from lesson to hard prompt rule + consider a cpp-guard check that flags a role-authored gate stamp.) *[Orchestration core / role prompts]*
2. **Resumability runbook for interrupted phases** — document the "inspect filesystem → spawn fresh agent scoped to remaining work" recovery, since the orchestrator cannot SendMessage-resume a dropped subagent. *[Orchestration core]*
3. **BUG-001 follow-up** — tighten `tests/test_summarizer_client.py` AC-4-022 assertion (drop the `or completion.call_args[0]` branch). Non-blocking; bundle into the next summarizer touch. *[Developer]*

### Fragile areas to watch
- **litellm exception hierarchy** (DEV-001): the 4 error-boundary tests are the guard; monitor litellm release notes for hierarchy changes.
- **ADR-006 sentence normalization**: regex + masked-abbrev list is non-exhaustive; cosmetic risk only, soft ≤2-sentence contract.
- **EC-014**: corrupt/foreign Redis cache entries are served as-is (documented V1 best-effort limit).
- **Not yet wired**: `summarize_items` is production-ready but NOT called from `pipeline.py` — intentionally deferred to a future pipeline-wiring change. The feature is dormant until then.

---

## state-store-3 · 2026-06-24

**Type:** feature (full S1→S6)
**Health Score:** 82/100 · 0 gate violations · 1 loop-back (S5→S4, ~15×, code bug)

### What worked
- Spec & design gates held under QA — **no S5→S3 (20×) or S5→S2 (25×) loop-backs**. The single loop-back was the cheapest tier (code bug), so the expensive upstream gates paid off.
- Independent QA re-ran everything (didn't trust the dev report) and caught a real **High** bug (BUG-001).
- `pipeline-guard` + `cpp-guard` genuinely enforced order/artifacts/CPP baton/convergence/cross-spec as exit codes — not prompt-trust. Caught every drift below.
- 98.94% line / 98.21% branch coverage; 18/18 ACs traced to asserting tests.

### Root cause — BUG-001 (High, AC-3-009, AI-detectable, missed by building AI)
- `load()` did `data.get("version")` without an `isinstance(data, dict)` guard → valid-but-non-dict-root JSON (`null`/`[]`/`42`/`"str"`) raised `AttributeError` instead of `StateError`. Dev self-review claimed to check the corrupt-vs-empty boundary but only tested *unparseable* JSON, not *parseable-but-wrong-type*. Fixed with one guard + 5 regression tests.

### Process friction — `_state.json` integrity (the real cost this run)
- Gates were written by a prior session/agents in the **wrong format** (verbose objects keyed by gate-name) vs the `{ "S<n>":"passed" }` phase-id strings `pipeline-guard` requires → spurious FENCE-JUMP; orchestrator had to re-key.
- `convergence` was keyed by gate-name (`SPEC_LOCK`) instead of phase-id (`S2`) that `cpp-guard.checkTrailing` reads — would have blocked S4.
- Cross-spec context block + convergence record were missing (S3 side-effects) — backfilled.
- **QA emitted structurally invalid JSON** (extra `}`) into `_state.json` → guard reported "unreadable"; orchestrator hand-repaired.
- Multiple roles (dev, qa) pre-stamped gate status — that's the orchestrator's job.

### Action items (carry forward)
1. **Schema-validated `_state.json` writer helper** — validate against the guard contract (gates as `{ "S<n>":"passed" }`, valid JSON) before save. Kills both the format-drift and the malformed-JSON failures. *[Tooling]*
2. **Edge-case checklist: non-dict-root deserialization** — for any `json.loads` boundary, test wrong-type roots (alongside the existing `isinstance(version, bool)` int-trap note). *[Analyst/Dev steering]*
3. **Restrict `_state.json` gate/convergence writes to the orchestrator** — role agents append to `phase_history`/`next_action` only, never stamp gates. *[Orchestration core]*

### Fragile areas to watch
- `_state.json` is edited by many actors with no schema guard — highest-risk integrity surface; a single bad brace halts the whole pipeline.
- Out-of-scope debt flagged by QA (NOT from this change): thin `.env.example`, no root `README.md`, `cli.py`/`github/client.py` use stdlib logging not JSON-structured logging — track as separate tickets.
- `[state].state_path`-only config (no top-level fallback) — design mentioned "or top-level"; ruled AC-compliant but a future config refactor may reopen it.

---

## github-collector-2 + 2b · 2026-06-24

**Type:** feature (full S1→S6) + bugfix follow-up (fast-track S4→S6)
**Health Score:** 91/100 · 0 gate violations · 0 loop-backs

### What worked
- S2 NO-GO caught and resolved *within S2* (before S3 started) — correct gate behavior, cost 1×.
- 99.25% coverage at first S4 attempt; 27/27 ACs confirmed at SPEC LOCK (0 ASSUMED).
- 3 Low bugs from S5 triaged via fast-track 2b — no reopening of main feature; correct escalation path.
- `cross-artifact-audit` 0 CRITICAL at S3; `spec-auditor` PASS C1-C6 at S2.

### Root causes of the 3 Low bugs (all AI-detectable, all test-quality)
- **BUG-1**: Production guard for non-string `created_at` was implied by AC-2-010 but not tested for the integer case. Guard was added; integer-path unit test was NOT added (acknowledged debt).
- **BUG-2**: `test_auth_failures_fail_fast` covered 401 token-absence assertion but not 403 — parametrized test was incomplete. Production code was correct.
- **BUG-3**: `httpx.Client` does not expose `verify` post-construction → shallow test that could not kill a `verify=False` mutation. Fixed via `patch.object(__init__, capturing_init)`.

### Action items (carry forward)
1. **S1 intake checklist — "config-driven tunables"**: for any data-fetching feature, explicitly ask: are `page_size` / `max_items` / timeouts config-driven? Prevents the S2 NO-GO class for this pattern.
2. **Testing-patterns skill or coding-standards**: document the `patch.object(__init__, capturing_init)` pattern for libraries that don't expose constructor args post-build (httpx `verify`, similar cases).
3. **Install `pip-audit`** in dev/QA environment: `pip check` does not catch known CVEs. Two consecutive changes (2 + 2b) flagged this absence.

### Fragile areas to watch (carry into next github-collector change)
- BUG-3 fix relies on httpx passing `verify` as a kwarg. If a future httpx version passes it positionally, `kwargs.get("verify")` returns `None` → assertion fails. Keep an eye on httpx changelogs.
- Shared `REPO_PATTERN` still accepts `..` segments — only collector-level guard in place. Architect decision deferred; flag if a new change touches `_validate_repo`.
- Integer-path test for `_parse_created` was not written — coverage blind spot on that branch.
