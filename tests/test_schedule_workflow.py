"""Tests for schedule/workflow.py: generate_workflow.

AC-V2-002-014 (Actions workflow), AC-V2-002-015 (no secret), AC-V2-002-017 (UTC comment).
"""

from __future__ import annotations

import pytest

from osspulse.schedule.errors import ScheduleError
from osspulse.schedule.workflow import generate_workflow

# ---------------------------------------------------------------------------
# AC-V2-002-014 — valid Actions workflow emitted
# ---------------------------------------------------------------------------


def test_generate_workflow_returns_string() -> None:
    """generate_workflow returns a non-empty string (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_workflow_contains_schedule_key() -> None:
    """Workflow YAML contains 'on:' and 'schedule:' (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert "on:" in result
    assert "schedule:" in result


def test_generate_workflow_contains_cron_expr() -> None:
    """Workflow YAML contains the provided cron expression (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert "0 8 * * *" in result


def test_generate_workflow_contains_cron_expr_verbatim() -> None:
    """Custom cron expression appears verbatim in the workflow (AC-V2-002-014)."""
    expr = "*/15 * * * *"
    result = generate_workflow(expr)
    assert expr in result


def test_generate_workflow_contains_osspulse_run() -> None:
    """Workflow YAML includes osspulse run step (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert "osspulse run" in result


def test_generate_workflow_has_trailing_newline() -> None:
    """Generated workflow ends with a newline (YAML file convention) (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# AC-V2-002-015 — secretless: ${{ secrets.* }} refs, no inline values
# ---------------------------------------------------------------------------


def test_generate_workflow_refs_github_token_as_secret() -> None:
    """Workflow references GITHUB_TOKEN via ${{ secrets.GITHUB_TOKEN }} (AC-V2-002-015)."""
    result = generate_workflow("0 8 * * *")
    assert "secrets.GITHUB_TOKEN" in result


def test_generate_workflow_refs_llm_key_as_secret() -> None:
    """Workflow references LLM key via ${{ secrets.LLM_API_KEY }} (AC-V2-002-015)."""
    result = generate_workflow("0 8 * * *")
    assert "secrets.LLM_API_KEY" in result


def test_generate_workflow_no_real_token_value(monkeypatch) -> None:
    """Workflow YAML never contains a real GITHUB_TOKEN value (AC-V2-002-015, RISK-001)."""
    import os

    from osspulse.schedule.secrets import assert_no_secret, collect_secret_values

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_actualtokenvalue")
    result = generate_workflow("0 8 * * *")
    secrets = collect_secret_values(os.environ)
    assert_no_secret(result, secrets)  # must not raise


# ---------------------------------------------------------------------------
# AC-V2-002-017 — UTC timezone comment present
# ---------------------------------------------------------------------------


def test_generate_workflow_contains_utc_comment() -> None:
    """Workflow YAML contains a comment mentioning UTC timezone (AC-V2-002-017)."""
    result = generate_workflow("0 8 * * *")
    assert "UTC" in result


def test_generate_workflow_utc_comment_near_cron() -> None:
    """UTC comment appears in the schedule section, not just in file header (AC-V2-002-017)."""
    result = generate_workflow("0 8 * * *")
    # Find the cron expression and check UTC appears in the same region
    cron_idx = result.find("0 8 * * *")
    utc_idx = result.find("UTC")
    # UTC comment should be within reasonable proximity to the schedule block
    assert abs(cron_idx - utc_idx) < 300, "UTC comment should be near the schedule block"


# ---------------------------------------------------------------------------
# Validation: double-quote in expression breaks YAML
# ---------------------------------------------------------------------------


def test_generate_workflow_rejects_double_quote_in_expr() -> None:
    """Cron expression with double-quote → ScheduleError (defensive YAML guard)."""
    with pytest.raises(ScheduleError):
        generate_workflow('0 8 * * * "extra"')


# ---------------------------------------------------------------------------
# Workflow structure completeness
# ---------------------------------------------------------------------------


def test_generate_workflow_has_jobs_section() -> None:
    """Workflow YAML has a 'jobs:' section (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert "jobs:" in result


def test_generate_workflow_has_workflow_dispatch() -> None:
    """Workflow supports workflow_dispatch for manual triggers (AC-V2-002-014)."""
    result = generate_workflow("0 8 * * *")
    assert "workflow_dispatch" in result
