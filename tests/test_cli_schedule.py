"""CLI-level tests for `osspulse schedule` command.

AC-V2-002-001..017/-024: schedule generation, presets, validation, install/uninstall,
github-actions, output, secret guard, error exits.

Uses Typer CliRunner; CrontabClient is replaced with an in-memory fake so no real
crontab is touched (ADR-008).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from osspulse.cli import app
from osspulse.schedule.errors import ScheduleError

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fake CrontabClient for in-memory testing
# ---------------------------------------------------------------------------


class _FakeCrontabClient:
    """In-memory CrontabClient for tests — never touches the real user crontab."""

    def __init__(self, initial: str = "") -> None:
        self.content = initial
        self.write_calls: list[str] = []

    def read(self) -> str:
        return self.content

    def write(self, text: str) -> None:
        self.content = text
        self.write_calls.append(text)


def _patch_client(fake: _FakeCrontabClient):
    """Return a context manager that replaces CrontabClient with *fake*."""
    return patch("osspulse.cli.CrontabClient", return_value=fake)


# ---------------------------------------------------------------------------
# Default: print daily crontab line (AC-V2-002-001/-008)
# ---------------------------------------------------------------------------


def test_schedule_default_prints_daily_line(tmp_path: Path) -> None:
    """Default (no flags) prints a daily crontab line to stdout, exit 0 (AC-V2-002-008)."""
    result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0
    assert "0 8 * * *" in result.stdout


def test_schedule_default_contains_osspulse_run(tmp_path: Path) -> None:
    """Default output contains 'osspulse run' (AC-V2-002-001)."""
    result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0
    assert "run" in result.stdout


def test_schedule_default_no_write(tmp_path: Path) -> None:
    """Default prints only — crontab not modified (AC-V2-002-001)."""
    fake = _FakeCrontabClient()
    with _patch_client(fake):
        result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0
    assert fake.write_calls == []


# ---------------------------------------------------------------------------
# --cron: verbatim expression (AC-V2-002-002)
# ---------------------------------------------------------------------------


def test_schedule_cron_flag_verbatim(tmp_path: Path) -> None:
    """--cron uses the given expression verbatim (AC-V2-002-002)."""
    result = runner.invoke(app, ["schedule", "--cron", "*/15 * * * *"])
    assert result.exit_code == 0
    assert "*/15 * * * *" in result.stdout


# ---------------------------------------------------------------------------
# --preset (AC-V2-002-003)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset,expected_expr",
    [
        ("hourly", "0 * * * *"),
        ("daily", "0 8 * * *"),
        ("weekly", "0 8 * * 1"),
    ],
)
def test_schedule_preset_mapping(preset: str, expected_expr: str, tmp_path: Path) -> None:
    """--preset maps to the correct cron expression (AC-V2-002-003)."""
    result = runner.invoke(app, ["schedule", "--preset", preset])
    assert result.exit_code == 0
    assert expected_expr in result.stdout


# ---------------------------------------------------------------------------
# Absolute paths in generated line (AC-V2-002-004, BR-V2-002-006)
# ---------------------------------------------------------------------------


def test_schedule_output_contains_absolute_binary_path(tmp_path: Path) -> None:
    """Generated line contains an absolute binary path (AC-V2-002-004)."""
    with patch("osspulse.cli.resolve_binary", return_value="/home/user/.local/bin/osspulse"):
        result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0
    assert "/home/user/.local/bin/osspulse" in result.stdout


def test_schedule_output_contains_absolute_config_path(tmp_path: Path) -> None:
    """Generated line contains an absolute config path (BR-V2-002-006)."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    result = runner.invoke(app, ["schedule", "--config", str(cfg)])
    assert result.exit_code == 0
    assert str(cfg.resolve()) in result.stdout


# ---------------------------------------------------------------------------
# Secret guard: no token in output (AC-V2-002-005, RISK-001)
# ---------------------------------------------------------------------------


def test_schedule_no_secret_in_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """GITHUB_TOKEN must not appear in crontab output (AC-V2-002-005, RISK-001)."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_totallyrealtoken")
    result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0
    assert "ghp_totallyrealtoken" not in result.stdout


# ---------------------------------------------------------------------------
# Error cases (AC-V2-002-006/-007)
# ---------------------------------------------------------------------------


def test_schedule_invalid_cron_exits_1(tmp_path: Path) -> None:
    """Invalid --cron → Error: stderr, exit 1, no write (AC-V2-002-006)."""
    fake = _FakeCrontabClient()
    with _patch_client(fake):
        result = runner.invoke(app, ["schedule", "--cron", "99 * * * *"])
    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert fake.write_calls == []


def test_schedule_mutual_exclusion_cron_and_preset(tmp_path: Path) -> None:
    """--cron + --preset together → Error: stderr, exit 1 (AC-V2-002-007)."""
    result = runner.invoke(app, ["schedule", "--cron", "0 8 * * *", "--preset", "daily"])
    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# --install (AC-V2-002-009/-010/-011)
# ---------------------------------------------------------------------------


def test_schedule_install_writes_to_crontab(tmp_path: Path) -> None:
    """--install writes the managed block (AC-V2-002-009)."""
    fake = _FakeCrontabClient()
    with _patch_client(fake):
        result = runner.invoke(app, ["schedule", "--install"])
    assert result.exit_code == 0
    assert len(fake.write_calls) == 1
    assert "# >>> osspulse >>>" in fake.content
    assert "# <<< osspulse <<<" in fake.content


def test_schedule_install_idempotent(tmp_path: Path) -> None:
    """Re-installing replaces the block, no duplicate (AC-V2-002-010)."""
    fake = _FakeCrontabClient()
    with _patch_client(fake):
        runner.invoke(app, ["schedule", "--install"])
        runner.invoke(app, ["schedule", "--install"])
    assert fake.content.count("# >>> osspulse >>>") == 1


def test_schedule_install_preserves_unrelated_lines(tmp_path: Path) -> None:
    """--install preserves lines outside the managed block (AC-V2-002-011)."""
    existing = "# My other jobs\n0 1 * * * /usr/bin/backup\n"
    fake = _FakeCrontabClient(initial=existing)
    with _patch_client(fake):
        runner.invoke(app, ["schedule", "--install"])
    assert "My other jobs" in fake.content
    assert "/usr/bin/backup" in fake.content


# ---------------------------------------------------------------------------
# --uninstall (AC-V2-002-011/-012)
# ---------------------------------------------------------------------------


def test_schedule_uninstall_removes_block(tmp_path: Path) -> None:
    """--uninstall removes the managed block (AC-V2-002-011)."""
    fake = _FakeCrontabClient()
    # First install
    with _patch_client(fake):
        runner.invoke(app, ["schedule", "--install"])
    assert "# >>> osspulse >>>" in fake.content

    # Then uninstall
    with _patch_client(fake):
        result = runner.invoke(app, ["schedule", "--uninstall"])
    assert result.exit_code == 0
    assert "# >>> osspulse >>>" not in fake.content


def test_schedule_uninstall_no_block_is_noop(tmp_path: Path) -> None:
    """--uninstall with no block present is a no-op, exit 0 (AC-V2-002-012)."""
    fake = _FakeCrontabClient(initial="# other stuff\n")
    with _patch_client(fake):
        result = runner.invoke(app, ["schedule", "--uninstall"])
    assert result.exit_code == 0
    assert fake.write_calls == []  # no write performed


# ---------------------------------------------------------------------------
# crontab command missing (AC-V2-002-013)
# ---------------------------------------------------------------------------


def test_schedule_install_missing_crontab_binary_exits_1(tmp_path: Path) -> None:
    """--install with crontab binary missing → Error: stderr, exit 1 (AC-V2-002-013)."""
    with patch(
        "osspulse.cli.CrontabClient",
        side_effect=ScheduleError("crontab command not found"),
    ):
        result = runner.invoke(app, ["schedule", "--install"])
    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# --github-actions (AC-V2-002-014/-015/-017)
# ---------------------------------------------------------------------------


def test_schedule_github_actions_prints_yaml(tmp_path: Path) -> None:
    """--github-actions prints a GitHub Actions workflow YAML (AC-V2-002-014)."""
    result = runner.invoke(app, ["schedule", "--github-actions"])
    assert result.exit_code == 0
    assert "on:" in result.stdout
    assert "schedule:" in result.stdout
    assert "0 8 * * *" in result.stdout


def test_schedule_github_actions_contains_utc_comment(tmp_path: Path) -> None:
    """--github-actions output includes UTC timezone comment (AC-V2-002-017)."""
    result = runner.invoke(app, ["schedule", "--github-actions"])
    assert result.exit_code == 0
    assert "UTC" in result.stdout


def test_schedule_github_actions_contains_secrets_refs(tmp_path: Path) -> None:
    """--github-actions references secrets store, no inline values (AC-V2-002-015)."""
    result = runner.invoke(app, ["schedule", "--github-actions"])
    assert result.exit_code == 0
    assert "secrets.GITHUB_TOKEN" in result.stdout
    assert "secrets.LLM_API_KEY" in result.stdout


def test_schedule_github_actions_no_secret_in_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """--github-actions output must not contain GITHUB_TOKEN value (AC-V2-002-015)."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_actionstesttoken")
    result = runner.invoke(app, ["schedule", "--github-actions"])
    assert result.exit_code == 0
    assert "ghp_actionstesttoken" not in result.stdout


# ---------------------------------------------------------------------------
# --output (AC-V2-002-016)
# ---------------------------------------------------------------------------


def test_schedule_github_actions_output_writes_file(tmp_path: Path) -> None:
    """--github-actions --output writes the workflow to a file (AC-V2-002-016)."""
    out = tmp_path / "osspulse.yml"
    result = runner.invoke(app, ["schedule", "--github-actions", "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "on:" in content
    assert "UTC" in content


def test_schedule_github_actions_output_unwritable_parent_exits_1(tmp_path: Path) -> None:
    """--output with unwritable parent → Error: exit 1, no partial file (AC-V2-002-016)."""
    nonexistent_parent = tmp_path / "doesnotexist" / "osspulse.yml"
    result = runner.invoke(
        app, ["schedule", "--github-actions", "--output", str(nonexistent_parent)]
    )
    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert not nonexistent_parent.exists()  # no partial file


def test_schedule_github_actions_output_no_partial_on_error(tmp_path: Path) -> None:
    """On write error, no partial file is left behind (AC-V2-002-016)."""
    # Make write fail by making the file a directory with no write perm on parent
    bad_parent = tmp_path / "noperm"
    bad_parent.mkdir()
    bad_parent.chmod(0o555)
    bad_out = bad_parent / "osspulse.yml"
    try:
        result = runner.invoke(app, ["schedule", "--github-actions", "--output", str(bad_out)])
        assert result.exit_code == 1
        assert not bad_out.exists()
    finally:
        bad_parent.chmod(0o755)  # restore so tmp_path cleanup works
