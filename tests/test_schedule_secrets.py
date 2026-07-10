"""Tests for schedule/secrets.py: collect_secret_values + assert_no_secret.

AC-V2-002-005, AC-V2-002-015 (no secret substring in any generator output).
RISK-001 HIGH mitigation tests.
"""

from __future__ import annotations

import pytest

from osspulse.schedule.errors import ScheduleError
from osspulse.schedule.secrets import assert_no_secret, collect_secret_values

# ---------------------------------------------------------------------------
# collect_secret_values (AC-V2-002-005)
# ---------------------------------------------------------------------------


def test_collect_empty_env_returns_empty_list() -> None:
    """Empty env → no secret values collected (AC-V2-002-005)."""
    result = collect_secret_values({})
    assert result == []


def test_collect_github_token(monkeypatch) -> None:
    """GITHUB_TOKEN present → included in the result (AC-V2-002-005)."""
    env = {"GITHUB_TOKEN": "ghp_myrealtoken123"}
    result = collect_secret_values(env)
    assert "ghp_myrealtoken123" in result


def test_collect_llm_api_key(monkeypatch) -> None:
    """LLM_API_KEY present → included in the result (AC-V2-002-015)."""
    env = {"LLM_API_KEY": "sk-supersecretkey"}
    result = collect_secret_values(env)
    assert "sk-supersecretkey" in result


def test_collect_openai_api_key(monkeypatch) -> None:
    """OPENAI_API_KEY present → included (AC-V2-002-015)."""
    env = {"OPENAI_API_KEY": "sk-openai-testkey"}
    result = collect_secret_values(env)
    assert "sk-openai-testkey" in result


def test_collect_empty_string_not_included() -> None:
    """Empty string env vars are skipped — substring of empty matches everything (AC-V2-002-005)."""
    env = {"GITHUB_TOKEN": "", "LLM_API_KEY": ""}
    result = collect_secret_values(env)
    assert result == []


def test_collect_whitespace_only_not_included() -> None:
    """Whitespace-only env vars are stripped and skipped (AC-V2-002-005)."""
    env = {"GITHUB_TOKEN": "   "}
    result = collect_secret_values(env)
    assert result == []


def test_collect_multiple_keys(monkeypatch) -> None:
    """Multiple secret env vars → all included (AC-V2-002-005/-015)."""
    env = {"GITHUB_TOKEN": "ghp_abc", "LLM_API_KEY": "sk-xyz", "ANTHROPIC_API_KEY": "ant-key"}
    result = collect_secret_values(env)
    assert "ghp_abc" in result
    assert "sk-xyz" in result
    assert "ant-key" in result


# ---------------------------------------------------------------------------
# assert_no_secret (AC-V2-002-005, AC-V2-002-015)
# ---------------------------------------------------------------------------


def test_assert_no_secret_passes_clean_text() -> None:
    """Text with no secret substrings → no exception (AC-V2-002-005)."""
    assert_no_secret("0 8 * * * /usr/bin/osspulse run --config /home/u/config.toml", [])


def test_assert_no_secret_passes_empty_values() -> None:
    """Empty values list → no exception (safe no-op) (AC-V2-002-005)."""
    assert_no_secret("some generated text", [])


def test_assert_no_secret_raises_on_token_in_crontab_line() -> None:
    """Secret substring in crontab line → ScheduleError (AC-V2-002-005, RISK-001)."""
    secret = "ghp_realtokenvalue"
    text = f"0 8 * * * /usr/bin/osspulse run --token {secret}"
    with pytest.raises(ScheduleError, match="secret"):
        assert_no_secret(text, [secret])


def test_assert_no_secret_raises_on_token_in_workflow_yaml() -> None:
    """Secret substring in workflow YAML → ScheduleError (AC-V2-002-015, RISK-001)."""
    secret = "sk-openai-actualkey"
    yaml_text = f"OPENAI_API_KEY: {secret}\n"
    with pytest.raises(ScheduleError, match="secret"):
        assert_no_secret(yaml_text, [secret])


def test_assert_no_secret_no_exception_on_empty_secret_in_values() -> None:
    """Empty string in values list is skipped (would match any text vacuously) (AC-V2-002-005)."""
    # An empty string is a substring of everything; the guard must NOT raise for it.
    assert_no_secret("any text here", [""])


def test_assert_no_secret_multiple_values_one_leaks() -> None:
    """Any one leaking secret is sufficient to raise ScheduleError (AC-V2-002-005)."""
    text = "0 8 * * * /usr/bin/osspulse run --config /cfg.toml  # token=ghp_leaked"
    with pytest.raises(ScheduleError):
        assert_no_secret(text, ["clean_value", "ghp_leaked"])


# ---------------------------------------------------------------------------
# Integration: feed real env token, assert neither generator output contains it
# RISK-001 HIGH — the hardest surface is the Actions YAML (AC-V2-002-015)
# ---------------------------------------------------------------------------


def test_generate_line_does_not_leak_env_token(monkeypatch) -> None:
    """Crontab line must not contain GITHUB_TOKEN from env (AC-V2-002-005, RISK-001)."""
    import os

    from osspulse.schedule.cron import generate_line
    from osspulse.schedule.secrets import collect_secret_values

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_realtesttoken99")
    line = generate_line("0 8 * * *", "/usr/bin/osspulse", "/home/user/config.toml")
    secrets = collect_secret_values(os.environ)
    assert_no_secret(line, secrets)  # must not raise


def test_generate_workflow_does_not_leak_env_token(monkeypatch) -> None:
    """Workflow YAML must not contain GITHUB_TOKEN from env (AC-V2-002-015, RISK-001)."""
    import os

    from osspulse.schedule.secrets import collect_secret_values
    from osspulse.schedule.workflow import generate_workflow

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_realtesttoken99")
    yaml_text = generate_workflow("0 8 * * *")
    secrets = collect_secret_values(os.environ)
    assert_no_secret(yaml_text, secrets)  # must not raise


def test_generate_workflow_does_not_leak_llm_key(monkeypatch) -> None:
    """Workflow YAML must not contain LLM_API_KEY from env (AC-V2-002-015, RISK-001)."""
    import os

    from osspulse.schedule.secrets import collect_secret_values
    from osspulse.schedule.workflow import generate_workflow

    monkeypatch.setenv("LLM_API_KEY", "sk-very-secret-llm-key")
    yaml_text = generate_workflow("0 8 * * *")
    secrets = collect_secret_values(os.environ)
    assert_no_secret(yaml_text, secrets)  # must not raise
