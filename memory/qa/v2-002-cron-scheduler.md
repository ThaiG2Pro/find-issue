## 2026-07-03 — v2-002-cron-scheduler: LockHeldError must NOT be a ScheduleError subclass — exit-code isolation is load-bearing

When a change has two error classes with different exit codes (one exit-0, one exit-1), the separation of inheritance is LOAD-BEARING:
- If `LockHeldError` were a subclass of `ScheduleError`, the CLI's `except ScheduleError` arm would catch it BEFORE the `except LockHeldError` arm (Python resolves `except` clauses top-to-bottom, matching the first compatible base class).
- In this change: `LockHeldError` is a plain `Exception`; `ScheduleError` is also a plain `Exception`. The CLI matches `LockHeldError` FIRST (ordered first in the except ladder). This order is explicit and documented (ADR-005), but NOT guarded by a structural type constraint — only by `test_lock_held_error_is_not_schedule_error` and `test_run_lock_held_exits_0_not_1`.

**Lesson**: When reviewing a change that adds a "benign skip" exit-0 exception alongside a fatal exit-1 exception class, always verify:
1. The benign exception is NOT a subclass of the fatal class.
2. The benign except arm is FIRST in the CLI ladder.
3. A test explicitly asserts `exit_code == 0` for the benign case (not just "no exception").

Flag as [AI-DETECTABLE] if either #1 or #2 is violated at review time.

---

## 2026-07-03 — v2-002-cron-scheduler: crontab round-trip symmetry — double-newline is intentional sentinel, test names can mislead

`upsert_block` ALWAYS prepends `\n` when appending to non-empty content (even if content ends with `\n`), producing a double-`\n`. `remove_block` unconditionally strips this separator. The invariant is: `remove_block(upsert_block(x)) == x` for any x with no pre-existing block.

A test named `test_upsert_block_no_double_newline_when_existing_ends_with_newline` actually ASSERTS the separator IS present. The test name contradicts the assertion body — the developer followed the ADR correctly (intentional double-`\n`), but the test name describes the rejected alternative. This produced BUG-001 [SPEC-UNCLEAR] Low.

**Lesson**: For any "round-trip byte-identity" guarantee:
1. The parametrized round-trip test (`remove(upsert(x)) == x`) is the authoritative correctness check — not individual upsert/remove unit tests.
2. Test names for edge-case newline handling should name the ACTUAL behavior being asserted, not the behavior being avoided (e.g. `test_upsert_block_appends_separator_for_nonempty_content` not `test_upsert_block_no_double_newline`).
3. At review time: if the test name says "no X" but the assertion body verifies X IS present → flag as SPEC-UNCLEAR test name, check that the round-trip test covers the real contract.

---

## 2026-07-03 — v2-002-cron-scheduler: ADR "reaffirmation of existing behavior" produces documentation-only guards (technical debt pattern)

When a design decision (ADR-010) says "reaffirm, don't rewrite" for an existing cron-safe behavior, the developer may implement the reaffirmation as:
- A computed variable that is immediately marked `# noqa: F841` (assigned but unused)
- Tests that assert the variable exists in source (`assert "isatty" in src`)
- No actual wiring of the variable to any output path

This produces passing tests and a clean lint run, but the guard is purely documentary — it will not activate if colored output is added later (B-002).

**Lesson**: When an ADR says "reaffirmation via tests," check:
1. Is there a behavioral test that would FAIL if the guard were removed? (Yes: `test_run_no_ansi_in_output_when_not_tty` — passes because Typer is already non-colored by default, not because of `_is_tty`.)
2. Would the guard actually suppress color if the output were ever colored? (No — `_is_tty` is unused.)

If the answer to #2 is No, classify as [LOGIC-BUG] Low / technical debt, not as a passing AC. Document in handoff §2 Contentious Points. At lite rigor: accept if the current output is provably color-free (test confirms). At full rigor: require the guard to be wired to an actual suppression path.

---

## 2026-07-03 — v2-002-cron-scheduler: secret-leak backstop best practice — two-layer defense

For any change that generates artifacts containing secrets-adjacent content:
1. **By-construction layer**: generators never read `os.environ` directly; they only know paths/expressions, not values.
2. **Runtime backstop layer**: `assert_no_secret(text, collect_secret_values(os.environ))` called on the FINAL output string BEFORE any write or print.

Both layers must be present. Testing the backstop alone (layer 2) is insufficient — a generator that reads env but correctly references secrets store would pass the backstop test even if it had a code path that could inline the value. Testing layer 1 alone (static analysis) is insufficient — a future edit could introduce env reads.

**Smoke test to add to S6 checklist**: run with `GITHUB_TOKEN=ghp_testvalue` in env, verify the token does NOT appear in `osspulse schedule` stdout or `--github-actions` output. This confirms both layers are active in a real subprocess (not just monkeypatched CliRunner context).

---

## 2026-07-03 — v2-002-cron-scheduler (re-verify): "documentation-only guard" pattern is fixable by extracting a testable helper

B-002 and B-003 share the same root pattern: implementation detail that was *conceptually correct* but untestable in its original form:
- B-002: `_is_tty` computed but never acted upon (documentation-only guard)
- B-003: `dup2(devnull, sys.stdout.fileno())` inlined in an except clause with no guard (BytesIO in tests has no fileno)

Both were fixed by the same technique: **extract to a named helper + add guards for the test context**:
- B-002: `if not _is_tty: os.environ["NO_COLOR"] = "1"` — one-liner activation, easy to test via monkeypatch
- B-003: `_handle_broken_pipe()` with `hasattr(sys.stdout, "fileno")` guard + `except io.UnsupportedOperation: pass`

**Lesson**: When a handler or guard has 0% coverage and the test runner says "BytesIO has no fileno / can't trigger SIGPIPE," the fix is extraction + guard — NOT deferring to a live smoke test. The extracted helper has two branches (real fd / no fd) that are independently testable. Coverage goes from 0% to 100% on the helper's body.

**Checklist for reviewing guards and except-handlers:**
1. Can the branch be triggered by a CliRunner test? If no (SIGPIPE, real fd) → extract to a helper.
2. Does the helper need to be no-op in a test context? → `hasattr` guard or `io.UnsupportedOperation` catch.
3. After extraction: 3 tests minimum — (a) real-context branch works, (b) test-context guard fires (no-op), (c) edge-case exception silenced.

Previously this change had 0% on cli.py:85-87. After fix: covered. Overall coverage improved 96.22% → 96.47%.
