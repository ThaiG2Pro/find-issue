"""Typer CLI entrypoint for OSS Pulse (S7 — scheduler-cli-7).

V2-002 additions:
  - ``schedule`` subcommand (AC-V2-002-001..017)
  - ``run`` wrapped in ``single_instance_lock`` (AC-V2-002-021..023)
  - cron-safe hardening on ``run``: no-color on non-TTY, no prompts (AC-V2-002-018..020)
  - ``LockHeldError`` handler ordered FIRST — WARN + exit 0 (ADR-005, AC-V2-002-022)
"""

from __future__ import annotations

import io
import logging
import os
import sys
import tempfile
from enum import StrEnum
from pathlib import Path

import typer

from osspulse.config import ConfigError, load_config
from osspulse.delivery.errors import DeliveryError
from osspulse.github.errors import AuthError
from osspulse.lock import LockHeldError, single_instance_lock
from osspulse.pipeline import run_pipeline
from osspulse.schedule.cron import (
    DEFAULT_CRON_EXPR,
    PRESETS,
    generate_line,
    resolve_binary,
    validate_cron_expr,
)
from osspulse.schedule.crontab import CrontabClient, remove_block, upsert_block
from osspulse.schedule.errors import ScheduleError
from osspulse.schedule.secrets import assert_no_secret, collect_secret_values
from osspulse.schedule.workflow import generate_workflow
from osspulse.state.errors import StateError

app = typer.Typer(help="OSS Pulse — monitor open source projects.")

logger = logging.getLogger("osspulse.cli")


class Preset(StrEnum):
    """Named cadence presets (AC-V2-002-003)."""

    hourly = "hourly"
    daily = "daily"
    weekly = "weekly"


@app.callback()
def _main() -> None:
    """OSS Pulse — monitor open source projects."""


# ---------------------------------------------------------------------------
# `osspulse run` — cron-safe, single-instance-locked (AC-V2-002-018..023)
# ---------------------------------------------------------------------------


def _handle_broken_pipe() -> None:
    """Redirect stdout → /dev/null to suppress interpreter flush errors after BrokenPipeError.

    Guards with hasattr + io.UnsupportedOperation so this works in both live (real fd)
    and test (BytesIO / no fileno) contexts (B-003 fix — scheduler-cli-7 memory).
    """
    if not hasattr(sys.stdout, "fileno"):
        return
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except io.UnsupportedOperation:
        pass  # BytesIO / non-file stdout in tests — nothing to redirect


@app.command()
def run(
    config: Path = typer.Option(Path("config.toml"), "--config", help="Path to config file."),
) -> None:
    """Load config and run the pipeline."""
    # AC-V2-002-020: no ANSI color when stdout is not a TTY (ADR-010).
    # Set NO_COLOR before the pipeline so any future color-aware output respects it.
    _is_tty = sys.stdout.isatty()
    if not _is_tty:
        os.environ["NO_COLOR"] = "1"

    # LockHeldError MUST be the first handler — it exits 0, not 1 (ADR-005).
    try:
        cfg = load_config(config, dict(os.environ))
        # AC-V2-002-021: acquire the single-instance lock before invoking run_pipeline.
        with single_instance_lock(cfg.state_path):
            run_pipeline(cfg)
    except LockHeldError:
        # AC-V2-002-022: benign overlap skip — WARN + exit 0 (not an error).
        logger.warning("osspulse run skipped: another run is already active (lock held)")
        raise typer.Exit(code=0)
    except BrokenPipeError:
        # ADR-003 (delivery-6), AC-7-013: redirect stdout→devnull so interpreter's
        # final flush doesn't re-raise after deliver() returns.
        _handle_broken_pipe()
        raise typer.Exit(code=0)
    except AuthError as e:
        # AC-7-005, BR-7-002: fatal — shared token invalid; message from our error class only
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except StateError as e:
        # AC-7-012, BR-7-004: state write failure is fatal
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except DeliveryError as e:
        # AC-7-020, BR-7-004
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except ConfigError as e:
        # AC-7-012, BR-7-004
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# `osspulse schedule` — generate / install / uninstall cron artifacts
# (AC-V2-002-001..017)
# ---------------------------------------------------------------------------


@app.command()
def schedule(
    config: Path = typer.Option(
        Path("config.toml"),
        "--config",
        help="Path to config file; resolved absolute in the generated line.",
    ),
    cron: str | None = typer.Option(
        None,
        "--cron",
        help="Explicit 5-field cron expression (mutually exclusive with --preset).",
    ),
    preset: Preset | None = typer.Option(
        None,
        "--preset",
        help="Named cadence preset: hourly, daily, or weekly.",
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="Install (or replace) the managed block in the user crontab.",
        is_flag=True,
    ),
    uninstall: bool = typer.Option(
        False,
        "--uninstall",
        help="Remove the managed block from the user crontab.",
        is_flag=True,
    ),
    github_actions: bool = typer.Option(
        False,
        "--github-actions",
        help="Emit a GitHub Actions workflow YAML instead of a crontab line.",
        is_flag=True,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="With --github-actions: write the workflow to this path instead of stdout.",
    ),
) -> None:
    """Generate and optionally install an osspulse cron schedule.

    Default (no flags): print a daily crontab line to stdout, mutate nothing.
    """
    try:
        _schedule_impl(
            config=config,
            cron=cron,
            preset=preset,
            install=install,
            uninstall=uninstall,
            github_actions=github_actions,
            output=output,
        )
    except ScheduleError as e:
        # AC-V2-002-006/-013/-016: fatal schedule errors → Error: stderr, exit 1, no traceback.
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def _schedule_impl(
    *,
    config: Path,
    cron: str | None,
    preset: Preset | None,
    install: bool,
    uninstall: bool,
    github_actions: bool,
    output: Path | None,
) -> None:
    """Core logic for the schedule command (separated for testability).

    Raises ``ScheduleError`` on any fatal condition; the caller maps it to exit 1.
    """
    secrets = collect_secret_values(os.environ)

    # --- Uninstall path (no cadence resolution needed) ---
    if uninstall:
        client = CrontabClient()
        current = client.read()
        new = remove_block(current)
        if new != current:  # only write if something changed (AC-V2-002-012)
            client.write(new)
        return

    # --- Resolve cadence (AC-V2-002-007/-008) ---
    if cron is not None and preset is not None:
        # AC-V2-002-007: --cron + --preset are mutually exclusive
        raise ScheduleError("--cron and --preset are mutually exclusive; use one or the other")

    if cron is not None:
        cron_expr = cron
    elif preset is not None:
        cron_expr = PRESETS[preset.value]
    else:
        cron_expr = DEFAULT_CRON_EXPR  # AC-V2-002-008: daily 08:00

    # --- Validate before any I/O (ADR-003, BR-V2-002-003) ---
    validate_cron_expr(cron_expr)

    # --- GitHub Actions workflow path ---
    if github_actions:
        yaml_text = generate_workflow(cron_expr)
        assert_no_secret(yaml_text, secrets)  # ADR-006 RISK-001 backstop
        if output is not None:
            _write_output_atomic(output, yaml_text)
        else:
            typer.echo(yaml_text, nl=False)
        return

    # --- Crontab line path ---
    binary = resolve_binary()
    line = generate_line(cron_expr, binary, config)
    assert_no_secret(line, secrets)  # ADR-006 RISK-001 backstop

    if install:
        client = CrontabClient()
        current = client.read()
        new = upsert_block(current, line)
        assert_no_secret(new, secrets)  # guard the full block too
        client.write(new)
    else:
        # Default: print only, no mutation (AC-V2-002-001)
        typer.echo(line)


def _write_output_atomic(output: Path, text: str) -> None:
    """Write *text* to *output* atomically using tempfile-in-parent + os.replace.

    Reuses the state-store-3 atomic-write pattern (delivery-6 memory):
    temp file in the SAME directory as target so os.replace is same-filesystem.
    Does NOT mkdir -p the parent — fail-fast if parent doesn't exist (AC-V2-002-016).

    Raises ScheduleError if the parent directory is not writable or os.replace fails.
    """
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=output.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, output)
        tmp_name = None  # renamed successfully; don't unlink
    except OSError as exc:
        raise ScheduleError(f"cannot write to {output}: {exc}") from exc
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass  # best-effort cleanup
