"""Tests for single_instance_lock + LockHeldError (AC-V2-002-021, -022, -023).

Uses real file descriptors in a tmp directory so the kernel flock semantics are
exercised without mocking (ADR-004 specifies real-fd testing for lock correctness).
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from osspulse.lock import LockHeldError, single_instance_lock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_path(tmp_path: Path) -> Path:
    """Return a synthetic state_path whose .parent the lock uses."""
    return tmp_path / "state.json"


# ---------------------------------------------------------------------------
# AC-V2-002-021 — lock acquired before pipeline, released after
# ---------------------------------------------------------------------------


def test_lock_acquired_and_released(tmp_path: Path) -> None:
    """Lock is held inside context, released after exit (AC-V2-002-021)."""
    sp = _state_path(tmp_path)
    executed = []

    with single_instance_lock(sp):
        executed.append("inside")

    assert executed == ["inside"]
    # After context exit, we should be able to re-acquire (released correctly).
    with single_instance_lock(sp):
        executed.append("re-acquired")

    assert executed == ["inside", "re-acquired"]


def test_lock_creates_parent_directory(tmp_path: Path) -> None:
    """Lock creates state_path.parent if it doesn't exist yet (AC-V2-002-021)."""
    sp = tmp_path / "subdir" / "state.json"
    assert not sp.parent.exists()

    with single_instance_lock(sp):
        assert sp.parent.exists()
        assert (sp.parent / "osspulse.lock").exists()


def test_lock_file_mode_600(tmp_path: Path) -> None:
    """Lock file is created with mode 0o600 (ADR-004)."""
    sp = _state_path(tmp_path)
    with single_instance_lock(sp):
        lock_path = sp.parent / "osspulse.lock"
        mode = oct(os.stat(lock_path).st_mode & 0o777)
        assert mode == oct(0o600)


# ---------------------------------------------------------------------------
# AC-V2-002-022 — benign skip: second acquire raises LockHeldError
# ---------------------------------------------------------------------------


def test_second_lock_raises_lock_held_error(tmp_path: Path) -> None:
    """Second flock(LOCK_NB) raises LockHeldError — never blocks (AC-V2-002-022)."""
    sp = _state_path(tmp_path)
    lock_path = sp.parent / "osspulse.lock"
    sp.parent.mkdir(parents=True, exist_ok=True)

    # Simulate a concurrently-held lock by acquiring an exclusive lock manually.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Now single_instance_lock must detect the held lock and raise LockHeldError.
        with pytest.raises(LockHeldError):
            with single_instance_lock(sp):
                pass  # should not reach here
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_lock_held_error_is_not_schedule_error(tmp_path: Path) -> None:
    """LockHeldError must NOT be a subclass of ScheduleError (ADR-005 exit-code contract)."""
    from osspulse.schedule.errors import ScheduleError

    assert not issubclass(LockHeldError, ScheduleError)


def test_lock_held_error_message(tmp_path: Path) -> None:
    """LockHeldError carries a human-readable message (ADR-005)."""
    sp = _state_path(tmp_path)
    lock_path = sp.parent / "osspulse.lock"
    sp.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(LockHeldError, match="overlapping run"):
            with single_instance_lock(sp):
                pass
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# AC-V2-002-023 — crash auto-release (kernel releases fd on close)
# ---------------------------------------------------------------------------


def test_lock_released_after_fd_closed(tmp_path: Path) -> None:
    """Closing the fd releases the kernel lock — simulates crash auto-release (AC-V2-002-023)."""
    sp = _state_path(tmp_path)
    lock_path = sp.parent / "osspulse.lock"
    sp.parent.mkdir(parents=True, exist_ok=True)

    # Acquire a lock, then close the fd (simulating process death releasing the fd).
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # "crash": close fd without explicit LOCK_UN — kernel auto-releases
    os.close(fd)

    # Now single_instance_lock should succeed (lock was freed by fd close).
    entered = []
    with single_instance_lock(sp):
        entered.append(True)

    assert entered == [True]


# ---------------------------------------------------------------------------
# Pipeline not invoked on LockHeldError
# ---------------------------------------------------------------------------


def test_pipeline_not_invoked_when_lock_held(tmp_path: Path) -> None:
    """When lock is held, the body of the context is never executed (AC-V2-002-022)."""
    sp = _state_path(tmp_path)
    lock_path = sp.parent / "osspulse.lock"
    sp.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pipeline_calls = []
        with pytest.raises(LockHeldError):
            with single_instance_lock(sp):
                pipeline_calls.append("called")
        assert pipeline_calls == [], "pipeline body must not run when lock is held"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
