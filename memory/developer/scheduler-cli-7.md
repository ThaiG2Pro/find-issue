## 2026-07-01 — scheduler-cli-7: stub→real transition breaks tests that mock at the wrong boundary

When a stub (`NotImplementedError`) is replaced by a real implementation, any test that invokes
the CLI command end-to-end without mocking the new implementation will start making real network
calls (e.g. GitHub API) and fail with `AuthError` or similar. Pattern: when `run_pipeline` became
real, `test_run_valid_config_exits_zero` broke because it called the CLI with a fake token and
hit the live `AuthError` path. Fix at transition time: mock `run_pipeline` at the module boundary
in all pre-existing CLI tests (`@patch("osspulse.cli.run_pipeline")`), and rely on the new
`test_pipeline.py` for the implementation's own behavioral coverage. The boundary shift is a
planned S4 task, not a surprise — add it to tasks.md when you know a stub will go real.
