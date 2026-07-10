"""Shared secret-guard backstop for schedule generators (ADR-006, AC-V2-002-005/-015).

RISK-001 mitigation: a single ``assert_no_secret(text, values)`` function called by
BOTH ``cron.generate_line`` and ``workflow.generate_workflow`` before returning their
output.  Ensures no non-empty secret value is a substring of a generated artifact.

This is defense-in-depth — the generators are written to reference ``~/.osspulse/.env``
and ``${{ secrets.* }}`` by construction, never inline values.  The guard catches a
future accidental regression.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from osspulse.schedule.errors import ScheduleError

# Environment variable names that hold secret values.
# Both GITHUB_TOKEN and the resolved LLM key are guarded (AC-V2-002-005/-015).
_SECRET_ENV_VARS = ("GITHUB_TOKEN",)

# LLM API-key env-var names that may appear in configs.
_LLM_KEY_ENV_VARS = (
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
)


def collect_secret_values(env: Mapping[str, str] | None = None) -> list[str]:
    """Collect non-empty secret values from *env* (defaults to ``os.environ``).

    Returns a list of plaintext secret strings that must not appear in any
    generated artifact.  Empty or absent values are skipped (an empty string
    substring check would match everything and be vacuously useless).

    Args:
        env: environment mapping to read from; defaults to ``os.environ``.

    Returns:
        List of non-empty secret strings (may be empty if no secrets are set).
    """
    if env is None:
        env = os.environ
    values: list[str] = []
    for var in _SECRET_ENV_VARS:
        val = env.get(var, "").strip()
        if val:
            values.append(val)
    for var in _LLM_KEY_ENV_VARS:
        val = env.get(var, "").strip()
        if val:
            values.append(val)
    return values


def assert_no_secret(text: str, values: list[str]) -> None:
    """Raise ``ScheduleError`` if any non-empty secret value is a substring of *text*.

    This is the RISK-001 HIGH backstop (ADR-006): called at the end of BOTH generators
    before the output is returned or written.  An empty *values* list is a safe no-op
    (no secrets configured → no check needed).

    Args:
        text: the generated crontab line or workflow YAML string.
        values: non-empty secret strings from ``collect_secret_values``.

    Raises:
        ScheduleError: if any secret is found as a substring of *text*.
    """
    for secret in values:
        if secret and secret in text:
            raise ScheduleError(
                "generated artifact contains a secret value — refusing to write; "
                "check that generators reference env/.env or secrets store only"
            )
