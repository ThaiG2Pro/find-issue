"""Cron-line generation for ``osspulse schedule`` (ADR-002, ADR-003, AC-V2-002-001..008).

Pure module — no I/O, no subprocess calls.  Every function is independently testable
without mocking anything.

Key design decisions:
- ``validate_cron_expr`` is dependency-free (ADR-003): 5-field range check, raises
  ``ScheduleError`` before any I/O (BR-V2-002-003 fail-fast).
- ``resolve_binary`` uses ``shutil.which("osspulse")`` → fallback
  ``os.path.abspath(sys.argv[0])`` (ADR-002, AC-V2-002-004/-024).
- ``generate_line`` emits absolute binary + config paths, referencing ``~/.osspulse/.env``
  for secrets — never inlining a value (BR-V2-002-001, AC-V2-002-005).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from osspulse.schedule.errors import ScheduleError

# ---------------------------------------------------------------------------
# Presets (AC-V2-002-003)
# ---------------------------------------------------------------------------

PRESETS: dict[str, str] = {
    "hourly": "0 * * * *",
    "daily": "0 8 * * *",
    "weekly": "0 8 * * 1",
}

# Default cadence when no flag is supplied (AC-V2-002-008)
DEFAULT_CRON_EXPR = PRESETS["daily"]

# ---------------------------------------------------------------------------
# Validation (ADR-003)
# ---------------------------------------------------------------------------

# (min, max) per cron field: minute, hour, dom, month, dow
_FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_FIELD_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


def _valid_field(value: str, lo: int, hi: int) -> bool:
    """Return True if *value* is a valid cron field token for the given range.

    Accepts: ``*``, ``*/n``, ``n``, ``n-m``, ``n,m,...``, ``n-m/s``.
    Does NOT accept ``@reboot``/named fields (documented limitation, ADR-003).
    """
    if value == "*":
        return True
    # Step: */n or n-m/s
    if "/" in value:
        parts = value.split("/", 1)
        if not parts[1].isdigit():
            return False
        step = int(parts[1])
        if step < 1:
            return False
        base = parts[0]
        if base == "*":
            return True
        # n-m/s
        if "-" in base:
            return _valid_range(base, lo, hi)
        return base.isdigit() and lo <= int(base) <= hi
    # Range: n-m
    if "-" in value:
        return _valid_range(value, lo, hi)
    # List: n,m,...
    if "," in value:
        return all(tok.isdigit() and lo <= int(tok) <= hi for tok in value.split(",") if tok)
    # Plain integer
    return value.isdigit() and lo <= int(value) <= hi


def _valid_range(value: str, lo: int, hi: int) -> bool:
    parts = value.split("-", 1)
    if len(parts) != 2:
        return False
    a, b = parts
    return a.isdigit() and b.isdigit() and lo <= int(a) <= hi and lo <= int(b) <= hi


def validate_cron_expr(expr: str) -> None:
    """Validate a 5-field cron expression; raise ``ScheduleError`` if invalid.

    Runs before any I/O so a bad expression never causes a partial write
    (BR-V2-002-003, ADR-003, AC-V2-002-006).

    Does NOT validate ``@reboot`` or named weekday/month fields — documented limitation.
    Presets (``0 8 * * *``, etc.) are always valid and bypass this in practice, but they
    also pass this check.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ScheduleError(
            f"invalid cron expression {expr!r}: expected 5 fields, got {len(fields)}"
        )
    for i, (field, (lo, hi), name) in enumerate(zip(fields, _FIELD_RANGES, _FIELD_NAMES)):
        if not _valid_field(field, lo, hi):
            raise ScheduleError(
                f"invalid cron expression {expr!r}: field {i + 1} ({name}) "
                f"value {field!r} is out of range {lo}-{hi}"
            )


# ---------------------------------------------------------------------------
# Binary resolution (ADR-002, AC-V2-002-004/-024)
# ---------------------------------------------------------------------------


def resolve_binary() -> str:
    """Return the absolute path to the ``osspulse`` executable.

    Resolution order:
    1. ``shutil.which("osspulse")`` — finds the installed console-script (pipx/pip).
    2. ``os.path.abspath(sys.argv[0])`` — fallback for ``python -m osspulse`` or a
       local invocation (the launcher path is absolute after abspath).

    No cron-daemon PATH verification is performed (AC-V2-002-024): emitting an absolute
    path makes PATH irrelevant under cron's minimal environment.

    Gotcha: under ``python -m osspulse``, ``sys.argv[0]`` is the module launcher path,
    not an ``osspulse`` console-script.  See README §Scheduling.
    """
    found = shutil.which("osspulse")
    if found:
        return found
    return os.path.abspath(sys.argv[0])


# ---------------------------------------------------------------------------
# Line generator (AC-V2-002-001/-002/-005)
# ---------------------------------------------------------------------------


def generate_line(cron_expr: str, binary: str, config_path: str | Path) -> str:
    """Generate the crontab line invoking ``osspulse run --config <abs>``.

    Both *binary* and *config_path* MUST be absolute paths (BR-V2-002-006):
    cron runs with a minimal ``cwd``/``PATH`` so relative paths silently break.

    The generated line references ``~/.osspulse/.env`` (loaded at runtime via
    python-dotenv) — no secret value is inlined (BR-V2-002-001, AC-V2-002-005).

    The ``assert_no_secret`` guard is applied by the caller (``cli.schedule``) after
    ``collect_secret_values``.  The generator itself never reads env secrets — it
    only knows the *path* to the env file.

    Args:
        cron_expr: validated 5-field cron expression.
        binary: absolute path to the ``osspulse`` binary.
        config_path: path to ``config.toml``; resolved to absolute by the caller.

    Returns:
        A single-line crontab entry (no trailing newline).
    """
    abs_config = Path(config_path).resolve()
    return f"{cron_expr} {binary} run --config {abs_config}"


def resolve_config_path(config_path: str | Path) -> Path:
    """Return the absolute resolved ``Path`` for *config_path*.

    Raises ``ScheduleError`` if the path cannot be resolved (e.g. the string is empty).
    """
    try:
        return Path(config_path).resolve()
    except Exception as exc:  # noqa: BLE001
        raise ScheduleError(f"cannot resolve config path {config_path!r}: {exc}") from exc
