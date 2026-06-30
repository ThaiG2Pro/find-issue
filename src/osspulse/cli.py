import os
import sys
from pathlib import Path

import typer

from osspulse.config import ConfigError, load_config
from osspulse.delivery.errors import DeliveryError
from osspulse.github.errors import AuthError
from osspulse.pipeline import run_pipeline
from osspulse.state.errors import StateError

app = typer.Typer(help="OSS Pulse — monitor open source projects.")


@app.callback()
def _main() -> None:
    """OSS Pulse — monitor open source projects."""


@app.command()
def run(
    config: Path = typer.Option(Path("config.toml"), "--config", help="Path to config file."),
) -> None:
    """Load config and run the pipeline."""
    try:
        cfg = load_config(config, dict(os.environ))
        run_pipeline(cfg)
    except BrokenPipeError:
        # ADR-003 (delivery-6), AC-7-013: redirect stdout→devnull so interpreter's
        # final flush doesn't re-raise after deliver() returns.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
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
