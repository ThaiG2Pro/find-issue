import os
import sys
from pathlib import Path

import typer

from osspulse.config import ConfigError, load_config
from osspulse.delivery import DeliveryError, FileDelivery, StdoutDelivery

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
        # INT-6-003: select adapter from config
        if cfg.output_destination == "stdout":
            delivery = StdoutDelivery()
        else:
            delivery = FileDelivery(cfg.output_path)
        # TODO: replace stub with real pipeline output (render result)
        delivery.deliver("osspulse: pipeline not yet implemented")
    except BrokenPipeError:
        # ADR-003, AC-6-009: redirect stdout→devnull so interpreter's final flush doesn't re-raise
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        raise typer.Exit(code=0)
    except DeliveryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
