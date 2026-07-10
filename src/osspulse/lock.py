"""Single-instance advisory lock for ``osspulse run`` (ADR-004, AC-V2-002-021..023).

Uses ``fcntl.flock(LOCK_EX | LOCK_NB)`` on a zero-byte lock file co-located with the
state file (``state_path.parent / "osspulse.lock"``).  The OS kernel auto-releases the
advisory lock when the file descriptor is closed — including on process death (kill -9) —
so there is no stale-lock heuristic (AC-V2-002-023).

``LOCK_NB`` makes a held lock raise ``BlockingIOError`` immediately rather than blocking,
enabling the benign-skip behaviour (AC-V2-002-022).

Unix-only (fcntl).  Windows/WSL users should use GitHub Actions scheduling instead
(proposal §Non-Goals).
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class LockHeldError(Exception):
    """Raised when the single-instance lock is already held by another run.

    The CLI maps this to WARN + exit 0 (benign skip, AC-V2-002-022) — it is matched
    BEFORE the fatal exit-1 arms (ADR-005).  It is NOT a subclass of ``ScheduleError``
    because that would pull it into the exit-1 error boundary.
    """


@contextmanager
def single_instance_lock(state_path: str | Path) -> Generator[None]:
    """Context manager that acquires an exclusive advisory lock around a pipeline run.

    Lock file path is derived as ``Path(state_path).parent / "osspulse.lock"``
    (no new ``Config`` field — scheduler-cli-7 ADR-002).

    Raises:
        LockHeldError: when the lock is already held (another run is active).
            The caller (``cli.run``) maps this to WARN + exit 0.

    On success, yields and releases the lock (``LOCK_UN`` + ``close``) in the
    ``finally`` block — safe even if an exception propagates through the pipeline.
    The kernel also frees the lock when the fd is closed, covering crash scenarios.
    """
    lock_path = Path(state_path).parent / "osspulse.lock"
    # Ensure the parent directory exists — the state store creates it too, but the lock
    # is acquired BEFORE run_pipeline, so the dir may not exist yet on first run.
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise LockHeldError("another osspulse run is already active; skipping this overlapping run")

    try:
        yield
    finally:
        # Explicit release — keeps a long-running process (e.g. test suite) correct,
        # even though the kernel would also free the lock on fd close.
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
