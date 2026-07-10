"""Tests for cron.py: PRESETS, validate_cron_expr, resolve_binary, generate_line.

AC-V2-002-003 (presets), AC-V2-002-006 (validation), AC-V2-002-004/-024 (binary resolution),
AC-V2-002-001/-002/-005 (generate_line).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from osspulse.schedule.cron import (
    DEFAULT_CRON_EXPR,
    PRESETS,
    generate_line,
    resolve_binary,
    validate_cron_expr,
)
from osspulse.schedule.errors import ScheduleError

# ---------------------------------------------------------------------------
# PRESETS (AC-V2-002-003)
# ---------------------------------------------------------------------------


def test_presets_contain_hourly_daily_weekly() -> None:
    """PRESETS map contains hourly, daily, weekly (AC-V2-002-003)."""
    assert PRESETS["hourly"] == "0 * * * *"
    assert PRESETS["daily"] == "0 8 * * *"
    assert PRESETS["weekly"] == "0 8 * * 1"


def test_default_is_daily() -> None:
    """Default cron expression is daily 08:00 (AC-V2-002-008)."""
    assert DEFAULT_CRON_EXPR == "0 8 * * *"


def test_all_presets_are_valid() -> None:
    """All preset expressions pass validate_cron_expr (AC-V2-002-003)."""
    for name, expr in PRESETS.items():
        validate_cron_expr(expr)  # must not raise


# ---------------------------------------------------------------------------
# validate_cron_expr — happy path (AC-V2-002-006)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "0 * * * *",
        "0 8 * * *",
        "0 8 * * 1",
        "*/15 * * * *",
        "0 0 1 1 *",
        "30 12 15 6 5",
        "0-30 * * * *",
        "0,30 * * * *",
        "0 8-17 * * 1-5",
    ],
)
def test_validate_valid_expressions(expr: str) -> None:
    """Valid 5-field expressions pass validation without raising (AC-V2-002-006)."""
    validate_cron_expr(expr)  # no exception


# ---------------------------------------------------------------------------
# validate_cron_expr — failure cases (AC-V2-002-006)
# ---------------------------------------------------------------------------


def test_validate_rejects_too_few_fields() -> None:
    """Fewer than 5 fields → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="5 fields"):
        validate_cron_expr("0 8 * *")


def test_validate_rejects_too_many_fields() -> None:
    """More than 5 fields → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="5 fields"):
        validate_cron_expr("0 8 * * * *")


def test_validate_rejects_out_of_range_minute() -> None:
    """Minute field out of range (60) → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="minute"):
        validate_cron_expr("60 8 * * *")


def test_validate_rejects_out_of_range_hour() -> None:
    """Hour field 24 → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="hour"):
        validate_cron_expr("0 24 * * *")


def test_validate_rejects_out_of_range_month() -> None:
    """Month field 13 → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="month"):
        validate_cron_expr("0 8 * 13 *")


def test_validate_rejects_out_of_range_dom() -> None:
    """Day-of-month 0 → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError, match="day-of-month"):
        validate_cron_expr("0 8 0 * *")


def test_validate_rejects_garbage() -> None:
    """Garbage expression → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError):
        validate_cron_expr("not_a_cron_expr")


def test_validate_rejects_empty_string() -> None:
    """Empty string → ScheduleError (AC-V2-002-006)."""
    with pytest.raises(ScheduleError):
        validate_cron_expr("")


def test_validate_error_has_no_traceback_info() -> None:
    """ScheduleError is a plain exception (no magic in init) (AC-V2-002-006)."""
    with pytest.raises(ScheduleError) as exc_info:
        validate_cron_expr("99 * * * *")
    # The message should be human-readable and contain the bad expression.
    assert "99" in str(exc_info.value)


# ---------------------------------------------------------------------------
# resolve_binary (ADR-002, AC-V2-002-004/-024)
# ---------------------------------------------------------------------------


def test_resolve_binary_returns_which_when_found() -> None:
    """When shutil.which finds osspulse, resolve_binary returns that path (AC-V2-002-004)."""
    with patch("shutil.which", return_value="/home/user/.local/bin/osspulse") as mock_which:
        result = resolve_binary()
    mock_which.assert_called_once_with("osspulse")
    assert result == "/home/user/.local/bin/osspulse"


def test_resolve_binary_falls_back_to_argv0_when_which_returns_none() -> None:
    """When shutil.which returns None, resolve_binary falls back to abspath(sys.argv[0]).

    AC-V2-002-004, AC-V2-002-024.
    """
    with patch("shutil.which", return_value=None):
        with patch.object(sys, "argv", ["/some/relative/path"]):
            result = resolve_binary()
    import os

    expected = os.path.abspath("/some/relative/path")
    assert result == expected


def test_resolve_binary_returns_absolute_path() -> None:
    """resolve_binary always returns an absolute path (BR-V2-002-006)."""
    import os

    with patch("shutil.which", return_value=None):
        result = resolve_binary()
    assert os.path.isabs(result)


# ---------------------------------------------------------------------------
# generate_line (AC-V2-002-001/-002/-005)
# ---------------------------------------------------------------------------


def test_generate_line_contains_cron_expr() -> None:
    """Generated line starts with the cron expression (AC-V2-002-001/-002)."""
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    assert line.startswith("0 8 * * *")


def test_generate_line_contains_absolute_binary() -> None:
    """Generated line contains the binary path (AC-V2-002-004)."""
    line = generate_line("0 8 * * *", "/usr/local/bin/osspulse", "/home/user/config.toml")
    assert "/usr/local/bin/osspulse" in line


def test_generate_line_contains_run_subcommand() -> None:
    """Generated line invokes `osspulse run` (AC-V2-002-001)."""
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    assert " run " in line or line.endswith(" run")


def test_generate_line_uses_absolute_config_path(tmp_path: Path) -> None:
    """Config path is resolved to absolute in the generated line (BR-V2-002-006)."""
    config = tmp_path / "config.toml"
    config.write_text("")
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", str(config))
    assert str(config.resolve()) in line


def test_generate_line_no_secret_inlined() -> None:
    """Generated line does not contain any secret value (AC-V2-002-005)."""
    import os

    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_supersecrettoken"}):
        line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    assert "ghp_supersecrettoken" not in line


def test_generate_line_references_config_flag() -> None:
    """Generated line includes --config flag (AC-V2-002-001)."""
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    assert "--config" in line


def test_generate_line_single_line() -> None:
    """Generated crontab entry is a single line (no embedded newlines) (AC-V2-002-001)."""
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    assert "\n" not in line
