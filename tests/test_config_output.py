"""Unit tests for [output] config section validation (AC-6-010..013)."""

from pathlib import Path

import pytest

from osspulse.config import ConfigError, load_config

ENV = {"GITHUB_TOKEN": "ghp_test"}
_BASE = '[watchlist]\nrepos = ["a/b"]\n'


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(_BASE + content)
    return p


def test_no_output_section_defaults_to_file_and_digest_md(tmp_path):
    """Absent [output] defaults to destination='file', output_path='./digest.md' (AC-6-010)."""
    cfg = load_config(_write(tmp_path, ""), ENV)
    assert cfg.output_destination == "file"
    assert cfg.output_path == "./digest.md"


def test_explicit_file_destination_and_path_loaded(tmp_path):
    """Valid file destination + path are loaded correctly (AC-6-011)."""
    cfg = load_config(
        _write(tmp_path, '[output]\ndestination = "file"\noutput_path = "./out/today.md"\n'), ENV
    )
    assert cfg.output_destination == "file"
    assert cfg.output_path == "./out/today.md"


def test_stdout_destination_loaded(tmp_path):
    """destination='stdout' is accepted (AC-6-010)."""
    cfg = load_config(_write(tmp_path, '[output]\ndestination = "stdout"\n'), ENV)
    assert cfg.output_destination == "stdout"


def test_invalid_destination_raises_config_error(tmp_path):
    """Invalid destination value raises ConfigError before pipeline runs (AC-6-012)."""
    with pytest.raises(ConfigError, match="output.destination"):
        load_config(_write(tmp_path, '[output]\ndestination = "email"\n'), ENV)


def test_empty_output_path_with_file_raises_config_error(tmp_path):
    """Empty output_path with destination='file' raises ConfigError (AC-6-013)."""
    with pytest.raises(ConfigError, match="output.output_path"):
        load_config(_write(tmp_path, '[output]\ndestination = "file"\noutput_path = ""\n'), ENV)


def test_whitespace_output_path_with_file_raises_config_error(tmp_path):
    """Whitespace-only output_path raises ConfigError (AC-6-013)."""
    with pytest.raises(ConfigError, match="output.output_path"):
        load_config(_write(tmp_path, '[output]\ndestination = "file"\noutput_path = "   "\n'), ENV)


def test_stdout_destination_ignores_output_path(tmp_path):
    """When destination='stdout', output_path is not validated (AC-6-010, BR-6-006)."""
    cfg = load_config(_write(tmp_path, '[output]\ndestination = "stdout"\n'), ENV)
    assert cfg.output_destination == "stdout"
    # output_path carries the default, no error raised
    assert cfg.output_path == "./digest.md"
