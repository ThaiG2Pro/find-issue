import os
from pathlib import Path

import typer

from osspulse.config import ConfigError, load_config

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
        load_config(config, dict(os.environ))
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo("osspulse: pipeline not yet implemented")
