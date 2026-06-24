from pathlib import Path

from typer.testing import CliRunner

from osspulse.cli import app

runner = CliRunner()


def write_valid_config(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    p.write_text('[watchlist]\nrepos = ["owner/repo"]\n')
    return p


# ---------------------------------------------------------------------------
# Help commands
# ---------------------------------------------------------------------------


def test_help_exit_zero_lists_run():
    """--help exits 0 and lists 'run' command (AC-1-028)."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout


def test_run_help():
    """run --help exits 0 (AC-1-029)."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_run_valid_config_exits_zero(tmp_path, monkeypatch):
    """Valid config → exit 0 + stub message (AC-1-030)."""
    p = write_valid_config(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    result = runner.invoke(app, ["run", "--config", str(p)])
    assert result.exit_code == 0
    assert "pipeline not yet implemented" in result.stdout


# ---------------------------------------------------------------------------
# Error boundary — ConfigError → stderr + non-zero + no traceback
# ---------------------------------------------------------------------------


def test_run_bad_config_exits_nonzero_stderr_no_traceback(tmp_path, monkeypatch):
    """Bad config → exit≠0 + 'Error:' on stderr + no traceback (AC-1-031, BR-1-007)."""
    p = tmp_path / "config.toml"
    p.write_text("invalid [[\n")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    result = runner.invoke(app, ["run", "--config", str(p)])
    assert result.exit_code != 0
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_run_missing_config_file_exits_nonzero(tmp_path, monkeypatch):
    """Missing config file → Error: to stderr + no traceback (AC-1-031, BR-1-007)."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    result = runner.invoke(app, ["run", "--config", str(tmp_path / "nonexistent.toml")])
    assert result.exit_code != 0
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_run_missing_token_exits_nonzero(tmp_path, monkeypatch):
    """Missing token → exit≠0 + 'Error:' on stderr (AC-1-032)."""
    p = write_valid_config(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = runner.invoke(app, ["run", "--config", str(p)])
    assert result.exit_code != 0
    assert "Error:" in result.stderr


# ---------------------------------------------------------------------------
# Unknown subcommand
# ---------------------------------------------------------------------------


def test_unknown_subcommand_exits_nonzero():
    """Unknown subcommand → usage on stderr + non-zero exit (AC-1-033)."""
    result = runner.invoke(app, ["notacommand"])
    assert result.exit_code != 0
