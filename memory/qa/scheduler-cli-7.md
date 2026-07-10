## 2026-07-01 — scheduler-cli-7: CliRunner cannot simulate BrokenPipeError — use live pipe smoke test

`click.testing.CliRunner` injects a `BytesIO` mock for stdout. `BytesIO` has no `fileno()`, so
there is no underlying file descriptor to close — `SIGPIPE` cannot be triggered from within the
test runner. Any attempt to exercise a `BrokenPipeError` handler via CliRunner will either fail
with `UnsupportedOperation: fileno` or simply never raise the error (3 incremental patching
approaches confirmed this in scheduler-cli-7). The only reliable verification for this AC class
is a live pipe smoke test: `uv run osspulse run | head -1` must exit 0 without a Python
traceback. Document this as an [EDGE-CASE] limitation in the QA report and add it to the S6
operator checklist.
## 2026-07-01 — scheduler-cli-7: two hollow TC patterns to catch at review time

Two recurring patterns produce passing tests that don't actually verify the AC:
- **H1-b pattern (log assertion hollow)**: test asserts `exit_code == 0` but never checks
  `caplog.text` contains the expected log line. Fix: always pair a "log line emitted" AC with a
  `caplog` assertion (`assert "expected substring" in caplog.text`), not just an exit-code check.
- **H1-c pattern (deliver-called-but-not-what)**: test asserts `mock_deliver.called` or
  `mock_deliver.call_count == 1` but never inspects the argument. Fix: assert
  `mock_deliver.call_args[0][0]` (the digest/items passed) matches the expected survivors, not
  just that the call happened.
Both are AI-detectable at code-review time — flag them as SHALLOW_TC and require the AC to be
independently verified by code review before accepting Low severity.
