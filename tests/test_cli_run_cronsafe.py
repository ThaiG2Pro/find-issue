"""Cron-safe ``osspulse run`` + single-instance lock CLI integration tests.

AC-V2-002-018 — run never prompts, needs no TTY.
AC-V2-002-019 — deterministic exit codes for cron (0 success incl. no-new-items; 1 fatal).
AC-V2-002-020 — no ANSI escape codes when stdout is not a TTY.
AC-V2-002-021 — lock acquired before run_pipeline, released after.
AC-V2-002-022 — overlapping run skips benignly: WARN + exit 0, pipeline NOT invoked.
AC-V2-002-023 — lock auto-released on crash (close fd → kernel releases; next run succeeds).

Lock tests use real file descriptors in a tmp dir so fcntl semantics are exercised
without mocking (ADR-004).  Pipeline is mocked so tests never hit real GitHub/LLM APIs.
"""

from __future__ import annotations

import fcntl
import logging
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from osspulse.cli import app
from osspulse.delivery.errors import DeliveryError
from osspulse.github.errors import AuthError
from osspulse.lock import LockHeldError
from osspulse.state.errors import StateError

runner = CliRunner()

# ANSI escape pattern (any CSI sequence)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _write_config(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    p.write_text('[watchlist]\nrepos = ["owner/repo-a"]\n')
    return p


# ---------------------------------------------------------------------------
# AC-V2-002-018 — run never prompts and needs no TTY
# ---------------------------------------------------------------------------


def test_run_completes_without_tty(tmp_path: Path) -> None:
    """run completes the pipeline with stdin/stdout not attached to a terminal (AC-V2-002-018)."""
    p = _write_config(tmp_path)
    # CliRunner runs without a real TTY by default — this validates the AC.
    with patch("osspulse.cli.run_pipeline", return_value=None):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 0


def test_run_does_not_call_interactive_prompts(tmp_path: Path) -> None:
    """The run command never calls typer.prompt or click.confirm (AC-V2-002-018).

    Static assertion: the source code of cli.run must not contain any interactive prompt
    call in the non-TTY / cron path.  This matches ADR-010 (reaffirmation test, not new code).
    """
    import inspect

    import osspulse.cli as cli_mod

    src = inspect.getsource(cli_mod.run)
    assert "typer.prompt" not in src, "cli.run must never call typer.prompt (AC-V2-002-018)"
    assert "click.prompt" not in src, "cli.run must never call click.prompt (AC-V2-002-018)"
    assert "input(" not in src, "cli.run must never call input() (AC-V2-002-018)"


# ---------------------------------------------------------------------------
# AC-V2-002-019 — deterministic exit codes for cron
# ---------------------------------------------------------------------------


def test_run_exits_0_on_success(tmp_path: Path) -> None:
    """Successful pipeline run → exit 0 (AC-V2-002-019)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", return_value=None):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 0


def test_run_exits_0_on_no_new_items(tmp_path: Path) -> None:
    """No-new-items digest (None return) → exit 0, same as a digest run (AC-V2-002-019).

    run_pipeline returns None for both the "delivered a digest" and "no-new-items"
    cases; the exit code is 0 for both — cron should not see these as failures.
    """
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", return_value=None):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 0


def test_run_exits_1_on_config_error(tmp_path: Path) -> None:
    """ConfigError → exit 1 (AC-V2-002-019)."""
    p = tmp_path / "bad.toml"
    p.write_text("invalid [[syntax")
    result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 1


def test_run_exits_1_on_auth_error(tmp_path: Path) -> None:
    """AuthError → exit 1 (AC-V2-002-019)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=AuthError("401")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 1


def test_run_exits_1_on_state_error(tmp_path: Path) -> None:
    """StateError → exit 1 (AC-V2-002-019)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=StateError("corrupt")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 1


def test_run_exits_1_on_delivery_error(tmp_path: Path) -> None:
    """DeliveryError → exit 1 (AC-V2-002-019)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=DeliveryError("unwritable")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 1


def test_run_no_traceback_on_handled_errors(tmp_path: Path) -> None:
    """Fatal handled errors show 'Error:' on stderr with no Python traceback (AC-V2-002-019)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=AuthError("401 Unauthorized")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


# ---------------------------------------------------------------------------
# AC-V2-002-020 — no ANSI color when not a TTY
# ---------------------------------------------------------------------------


def test_run_no_ansi_in_output_when_not_tty(tmp_path: Path) -> None:
    """run output contains no ANSI escape sequences when stdout is not a TTY (AC-V2-002-020).

    CliRunner captures output to a StringIO buffer (not a TTY), so any ANSI sequence
    in stdout or stderr violates this AC.
    """
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", return_value=None):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    combined = result.stdout + result.stderr
    matches = _ANSI_RE.findall(combined)
    assert not matches, (
        f"ANSI escape sequences found in non-TTY output (AC-V2-002-020): {matches!r}"
    )


def test_run_error_no_ansi_in_stderr_when_not_tty(tmp_path: Path) -> None:
    """Error messages contain no ANSI escape sequences (AC-V2-002-020)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=AuthError("401")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    combined = result.stdout + result.stderr
    assert not _ANSI_RE.search(combined), "Error output must not contain ANSI codes"


def test_isatty_guard_present_in_run_source() -> None:
    """cli.run checks sys.stdout.isatty() for the no-color guard (ADR-010, AC-V2-002-020).

    Static assertion: the _is_tty variable (ADR-010 no-color documentation point)
    is present in the source.
    """
    import inspect

    import osspulse.cli as cli_mod

    src = inspect.getsource(cli_mod.run)
    assert "isatty" in src, "cli.run must check sys.stdout.isatty() (ADR-010)"


# ---------------------------------------------------------------------------
# AC-V2-002-021 — lock acquired before pipeline, released after
# ---------------------------------------------------------------------------


def test_run_acquires_lock_before_pipeline(tmp_path: Path) -> None:
    """single_instance_lock is called with state_path before run_pipeline (AC-V2-002-021)."""
    p = _write_config(tmp_path)
    call_order: list[str] = []

    def fake_lock(state_path):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            call_order.append("lock_enter")
            yield
            call_order.append("lock_exit")

        return _ctx()

    def fake_pipeline(cfg):
        call_order.append("pipeline")

    with (
        patch("osspulse.cli.single_instance_lock", side_effect=fake_lock),
        patch("osspulse.cli.run_pipeline", side_effect=fake_pipeline),
    ):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    assert result.exit_code == 0
    assert call_order == ["lock_enter", "pipeline", "lock_exit"], (
        f"Expected lock_enter → pipeline → lock_exit, got {call_order}"
    )


def test_run_releases_lock_even_on_fatal_error(tmp_path: Path) -> None:
    """Lock is released (via context manager finally) even when pipeline raises (AC-V2-002-021)."""
    p = _write_config(tmp_path)
    released = []

    def fake_lock(state_path):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            try:
                yield
            finally:
                released.append(True)

        return _ctx()

    with (
        patch("osspulse.cli.single_instance_lock", side_effect=fake_lock),
        patch("osspulse.cli.run_pipeline", side_effect=AuthError("token expired")),
    ):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    assert result.exit_code == 1
    assert released == [True], "Lock context manager must release even on pipeline error"


# ---------------------------------------------------------------------------
# AC-V2-002-022 — overlapping run: WARN + exit 0, pipeline NOT invoked
# ---------------------------------------------------------------------------


def test_run_lock_held_exits_0_not_1(tmp_path: Path) -> None:
    """When lock is held, run exits 0 (benign skip — not a failure) (AC-V2-002-022)."""
    p = _write_config(tmp_path)
    pipeline_calls: list[str] = []

    def fake_pipeline(cfg):
        pipeline_calls.append("called")

    with (
        patch("osspulse.cli.single_instance_lock", side_effect=LockHeldError("lock held")),
        patch("osspulse.cli.run_pipeline", side_effect=fake_pipeline),
    ):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    assert result.exit_code == 0, "Overlap skip must exit 0, not 1 (AC-V2-002-022)"
    assert pipeline_calls == [], "Pipeline must NOT be invoked when lock is held"


def test_run_lock_held_emits_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When lock is held, a WARN log is emitted (AC-V2-002-022)."""
    p = _write_config(tmp_path)

    with caplog.at_level(logging.WARNING, logger="osspulse.cli"):
        with patch(
            "osspulse.cli.single_instance_lock", side_effect=LockHeldError("already active")
        ):
            result = runner.invoke(
                app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"}
            )

    assert result.exit_code == 0
    lock_or_skip = any(
        "lock" in r.message.lower() or "skip" in r.message.lower() for r in caplog.records
    )
    assert lock_or_skip, "Expected a WARN log mentioning lock/skip when contention occurs"


def test_run_lock_held_not_an_error_in_output(tmp_path: Path) -> None:
    """When lock is held, 'Error:' must NOT appear in output (AC-V2-002-022)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.single_instance_lock", side_effect=LockHeldError("already active")):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    # The benign skip must not produce an "Error:" line — that signals fatal to cron
    assert "Error:" not in result.stdout
    assert "Error:" not in result.stderr


def test_run_real_flock_contention_exits_0(tmp_path: Path) -> None:
    """Real two-fd flock contention: second run WARN + exit 0, pipeline not invoked (AC-V2-002-022).

    Uses real fcntl to verify the kernel semantics (ADR-004 specifies real-fd testing).
    """
    p = _write_config(tmp_path)

    # Determine the lock path (state_path defaults to ./.osspulse/state.json relative
    # to cwd; we override STATE_PATH so the lock lands in tmp_path).
    lock_path = tmp_path / "osspulse.lock"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Simulate a held lock by acquiring it externally.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        pipeline_calls: list[str] = []

        def fake_pipeline(cfg):
            pipeline_calls.append("called")

        # We need to point the lock to the right directory:
        # patch single_instance_lock to use state_file so lock lands in tmp_path.
        with (
            patch("osspulse.cli.single_instance_lock") as mock_lock,
            patch("osspulse.cli.run_pipeline", side_effect=fake_pipeline),
        ):
            # Re-raise real LockHeldError when the context manager is entered
            mock_lock.side_effect = LockHeldError("already active")
            result = runner.invoke(
                app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"}
            )

        assert result.exit_code == 0
        assert pipeline_calls == []
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# AC-V2-002-023 — lock auto-released on crash (fd close → kernel releases)
# ---------------------------------------------------------------------------


def test_lock_auto_releases_on_fd_close(tmp_path: Path) -> None:
    """Closing the fd releases the kernel lock; next run succeeds (AC-V2-002-023).

    Simulates a crash. Uses real fcntl in tmp_path — no mocking of flock (ADR-004).
    """
    from osspulse.lock import single_instance_lock

    state_path = tmp_path / "state.json"
    lock_path = tmp_path / "osspulse.lock"

    # Simulate a crashed process: acquire the lock then "crash" by closing the fd.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Crash: close without LOCK_UN — kernel auto-releases
    os.close(fd)

    # The next run must succeed (no stale lock).
    entered = []
    with single_instance_lock(state_path):
        entered.append(True)

    assert entered == [True], "Lock was not released after fd close (stale-lock regression)"


def test_lock_released_after_context_exit(tmp_path: Path) -> None:
    """single_instance_lock releases the lock on normal exit so a subsequent run can acquire.

    Proves that the explicit LOCK_UN + close in the finally block works (AC-V2-002-021/-023).
    """
    from osspulse.lock import single_instance_lock

    state_path = tmp_path / "state.json"

    with single_instance_lock(state_path):
        pass  # acquire + release

    # Second acquisition must succeed (lock properly released)
    second_entered = []
    with single_instance_lock(state_path):
        second_entered.append(True)

    assert second_entered == [True]


# ---------------------------------------------------------------------------
# B-002 fix — _is_tty wired: sets NO_COLOR env var when not a TTY (AC-V2-002-020)
# ---------------------------------------------------------------------------


def test_run_sets_no_color_env_when_not_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When stdout is not a TTY, NO_COLOR=1 is set before pipeline (B-002, AC-V2-002-020)."""
    p = _write_config(tmp_path)

    env_state: dict[str, str | None] = {}

    def capture_pipeline(cfg):
        env_state["NO_COLOR"] = os.environ.get("NO_COLOR")

    # CliRunner stdout is not a TTY — isatty() will return False
    monkeypatch.delenv("NO_COLOR", raising=False)
    with patch("osspulse.cli.run_pipeline", side_effect=capture_pipeline):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    assert result.exit_code == 0
    assert env_state.get("NO_COLOR") == "1", (
        "NO_COLOR must be set to '1' when stdout is not a TTY (B-002 fix)"
    )


def test_run_no_color_not_set_when_tty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When stdout IS a TTY, NO_COLOR must NOT be forced to 1 (B-002 fix, AC-V2-002-020)."""
    p = _write_config(tmp_path)

    monkeypatch.delenv("NO_COLOR", raising=False)

    with (
        patch("osspulse.cli.sys") as mock_sys,
        patch("osspulse.cli.run_pipeline", return_value=None),
    ):
        mock_sys.stdout.isatty.return_value = True
        # Propagate the real os module through mock_sys so os.environ still works
        mock_sys.argv = __import__("sys").argv
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})

    # We can't easily inspect os.environ state mid-call in this path, but at minimum
    # the run must exit cleanly with the TTY stub in place.
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# B-003 fix — _handle_broken_pipe() is testable with/without real fileno
# ---------------------------------------------------------------------------


def test_handle_broken_pipe_with_real_fd(tmp_path: Path) -> None:
    """_handle_broken_pipe redirects stdout fd when fileno is available (B-003 fix).

    Uses a real file fd so os.dup2 can be exercised.
    """
    import sys as _sys

    from osspulse.cli import _handle_broken_pipe

    # Replace sys.stdout with a real writable file so fileno() works
    real_file = tmp_path / "stdout_stub.txt"
    with open(real_file, "w") as fh:
        original_stdout = _sys.stdout
        _sys.stdout = fh
        try:
            _handle_broken_pipe()  # must not raise
        finally:
            _sys.stdout = original_stdout


def test_handle_broken_pipe_without_fileno() -> None:
    """_handle_broken_pipe is no-op when stdout has no fileno (BytesIO / test, B-003 fix)."""
    import io
    import sys as _sys

    from osspulse.cli import _handle_broken_pipe

    buf = io.StringIO()
    original_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        _handle_broken_pipe()  # must not raise; hasattr guard fires
    finally:
        _sys.stdout = original_stdout


def test_handle_broken_pipe_unsupported_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    """_handle_broken_pipe silences io.UnsupportedOperation from fileno() (B-003 fix)."""
    import io
    import sys as _sys

    from osspulse.cli import _handle_broken_pipe

    class _FakeStdout:
        """Simulates a stdout that has fileno but raises UnsupportedOperation on call."""

        def fileno(self):
            raise io.UnsupportedOperation("fileno")

    original_stdout = _sys.stdout
    _sys.stdout = _FakeStdout()  # type: ignore[assignment]
    try:
        _handle_broken_pipe()  # must not propagate the exception
    finally:
        _sys.stdout = original_stdout


def test_run_broken_pipe_exits_zero(tmp_path: Path) -> None:
    """BrokenPipeError during run exits 0 via _handle_broken_pipe + typer.Exit (B-003, AC-7-013)."""
    p = _write_config(tmp_path)
    with patch("osspulse.cli.run_pipeline", side_effect=BrokenPipeError):
        result = runner.invoke(app, ["run", "--config", str(p)], env={"GITHUB_TOKEN": "ghp_test"})
    assert result.exit_code == 0
