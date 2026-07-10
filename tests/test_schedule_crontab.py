"""Tests for schedule/crontab.py: upsert_block, remove_block, CrontabClient.

AC-V2-002-009 (markers), AC-V2-002-010 (idempotent replace), AC-V2-002-011 (byte preservation),
AC-V2-002-012 (uninstall no-op), AC-V2-002-013 (crontab missing → ScheduleError).
"""

from __future__ import annotations

import pytest

from osspulse.schedule.crontab import (
    BLOCK_END,
    BLOCK_START,
    CrontabClient,
    remove_block,
    upsert_block,
)
from osspulse.schedule.errors import ScheduleError

EXAMPLE_LINE = "0 8 * * * /usr/bin/osspulse run --config /home/u/config.toml"
EXAMPLE_LINE2 = "0 9 * * * /usr/bin/osspulse run --config /home/u/config.toml"


# ---------------------------------------------------------------------------
# upsert_block — install (AC-V2-002-009/-010)
# ---------------------------------------------------------------------------


def test_upsert_block_on_empty_crontab() -> None:
    """Installing on empty crontab adds the managed block (AC-V2-002-009)."""
    result = upsert_block("", EXAMPLE_LINE)
    assert BLOCK_START in result
    assert BLOCK_END in result
    assert EXAMPLE_LINE in result


def test_upsert_block_markers_present() -> None:
    """Both start and end markers appear in the output (AC-V2-002-009)."""
    result = upsert_block("", EXAMPLE_LINE)
    assert result.count(BLOCK_START) == 1
    assert result.count(BLOCK_END) == 1


def test_upsert_block_on_nonempty_crontab_preserves_existing_lines() -> None:
    """Installing on non-empty crontab preserves existing lines (AC-V2-002-011)."""
    existing = "# Other job\n0 0 * * * /usr/bin/other-job\n"
    result = upsert_block(existing, EXAMPLE_LINE)
    assert "# Other job" in result
    assert "other-job" in result
    assert EXAMPLE_LINE in result


def test_upsert_block_reinstall_replaces_in_place() -> None:
    """Re-installing replaces the existing block, no duplicate (AC-V2-002-010)."""
    first = upsert_block("", EXAMPLE_LINE)
    second = upsert_block(first, EXAMPLE_LINE2)
    assert second.count(BLOCK_START) == 1
    assert second.count(BLOCK_END) == 1
    assert EXAMPLE_LINE2 in second
    assert EXAMPLE_LINE not in second  # replaced, not duplicated


def test_upsert_block_reinstall_idempotent() -> None:
    """Installing the same line twice is idempotent (AC-V2-002-010)."""
    first = upsert_block("", EXAMPLE_LINE)
    second = upsert_block(first, EXAMPLE_LINE)
    assert first == second


def test_upsert_block_appends_with_leading_newline_when_needed() -> None:
    """Separator \n added between existing content and block for non-empty originals (ADR-007)."""
    existing = "# no trailing newline"  # no trailing \n
    result = upsert_block(existing, EXAMPLE_LINE)
    # The separator newline ensures the block starts on its own line
    assert result.startswith("# no trailing newline\n")


def test_upsert_block_adds_newline_separator_when_existing_ends_with_newline() -> None:
    """Separator \\n is always prepended for non-empty content.

    double-\\n before BLOCK_START is the round-trip sentinel (ADR-007).
    The encoding contract: upsert ALWAYS prepends \\n when original is non-empty,
    so remove_block can unconditionally strip it (ADR-007).
    """
    existing = "# comment\n"
    result = upsert_block(existing, EXAMPLE_LINE)
    # The separator \n is prepended, meaning the result has \n\n before BLOCK_START.
    assert f"\n{BLOCK_START}" in result


def test_upsert_block_returns_string_ending_with_newline() -> None:
    """Block ends with a trailing newline (tidy crontab convention) (AC-V2-002-009)."""
    result = upsert_block("", EXAMPLE_LINE)
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# remove_block (AC-V2-002-011/-012)
# ---------------------------------------------------------------------------


def test_remove_block_absent_is_noop() -> None:
    """remove_block on crontab with no osspulse block returns unchanged (AC-V2-002-012)."""
    content = "# unrelated line\n0 0 * * * /usr/bin/other\n"
    assert remove_block(content) == content


def test_remove_block_empty_is_noop() -> None:
    """remove_block on empty string returns empty string (AC-V2-002-012)."""
    assert remove_block("") == ""


def test_remove_block_removes_installed_block() -> None:
    """remove_block strips the installed block (AC-V2-002-011)."""
    with_block = upsert_block("", EXAMPLE_LINE)
    result = remove_block(with_block)
    assert BLOCK_START not in result
    assert BLOCK_END not in result
    assert EXAMPLE_LINE not in result


def test_remove_block_preserves_unrelated_lines() -> None:
    """Lines outside the managed block survive remove_block (AC-V2-002-011)."""
    existing = "# keep me\n0 0 * * * /usr/bin/other-job\n"
    with_block = upsert_block(existing, EXAMPLE_LINE)
    result = remove_block(with_block)
    assert "# keep me" in result
    assert "/usr/bin/other-job" in result


# ---------------------------------------------------------------------------
# Round-trip guarantee: remove_block(upsert_block(x)) == x (ADR-007, RISK-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "original",
    [
        "",
        "\n",
        "# a comment\n",
        "0 0 * * * /bin/job\n",
        "# two\n0 1 * * * /bin/job1\n0 2 * * * /bin/job2\n",
        "no trailing newline",
        "# mixed\n0 3 * * * /bin/cmd",
        "line1\nline2\nline3\n",
    ],
)
def test_round_trip_byte_identical(original: str) -> None:
    """remove_block(upsert_block(x)) == x for any x with no pre-existing block (ADR-007)."""
    installed = upsert_block(original, EXAMPLE_LINE)
    restored = remove_block(installed)
    assert restored == original, (
        f"Round-trip failed!\n"
        f"  original:  {original!r}\n"
        f"  installed: {installed!r}\n"
        f"  restored:  {restored!r}"
    )


def test_round_trip_double_reinstall() -> None:
    """install → reinstall → uninstall round-trip is byte-identical (ADR-007)."""
    original = "# pre-existing\n0 0 * * * /bin/job\n"
    installed = upsert_block(original, EXAMPLE_LINE)
    reinstalled = upsert_block(installed, EXAMPLE_LINE2)
    restored = remove_block(reinstalled)
    assert restored == original, (
        f"Double-install round-trip failed!\n  original:  {original!r}\n  restored:  {restored!r}"
    )


# ---------------------------------------------------------------------------
# Trailing-newline edge cases (design §Gotchas)
# ---------------------------------------------------------------------------


def test_upsert_preserves_trailing_newlines_after_block() -> None:
    """Lines after the block are preserved with their newlines (AC-V2-002-011)."""
    # Simulate a crontab that already has an osspulse block at the top
    # followed by unrelated content — ensure reinstall preserves the suffix.
    original = "# before\n"
    first = upsert_block(original, EXAMPLE_LINE)
    # Add unrelated content after the block
    with_suffix = first + "# after\n0 5 * * * /bin/other\n"
    reinstalled = upsert_block(with_suffix, EXAMPLE_LINE2)
    assert "# after" in reinstalled
    assert "/bin/other" in reinstalled
    assert EXAMPLE_LINE2 in reinstalled
    assert EXAMPLE_LINE not in reinstalled


# ---------------------------------------------------------------------------
# CrontabClient — missing binary (AC-V2-002-013)
# ---------------------------------------------------------------------------


def test_crontab_client_raises_schedule_error_when_binary_missing(monkeypatch) -> None:
    """CrontabClient raises ScheduleError when crontab is not on PATH (AC-V2-002-013)."""
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    with pytest.raises(ScheduleError, match="crontab command not found"):
        CrontabClient()


def test_crontab_client_init_succeeds_when_binary_present(monkeypatch) -> None:
    """CrontabClient init succeeds when crontab binary is found (AC-V2-002-013)."""
    monkeypatch.setattr(
        "shutil.which",
        lambda cmd: "/usr/bin/crontab" if cmd == "crontab" else None,
    )
    client = CrontabClient()
    assert client is not None
