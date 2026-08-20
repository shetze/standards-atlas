"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.application.workspace import WorkspaceLayout
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    app,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show the Standards Atlas version and exit."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Standards Atlas command-line entry point."""
    if version:
        typer.echo(f"standards-atlas {__version__}")
        raise typer.Exit()


@app.command()
def info() -> None:
    """Show basic project information."""
    typer.echo("Standards Atlas")
    typer.echo("Semantic traceability platform for technical standards.")


@app.command()
def clean(
    cache: Annotated[
        bool, typer.Option("--cache", help="Also remove disposable cache artifacts.")
    ] = False,
    data: Annotated[
        bool,
        typer.Option(
            "--data",
            help="Also remove persistent machine-facing data (requires --force).",
        ),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Confirm destructive removal of persistent data.")
    ] = False,
) -> None:
    """Clean machine-owned storage without touching human-facing local artifacts."""
    if data and not force:
        raise typer.BadParameter("--data requires --force")
    layout = WorkspaceLayout(Path.cwd())
    layout.clear_work()
    typer.echo(f"Removed work artifacts    : {layout.work}")
    if cache:
        layout.clear_cache()
        typer.echo(f"Removed cache artifacts   : {layout.cache}")
    if data:
        layout.clear_data()
        typer.echo(f"Removed persistent data   : {layout.data}")


@app.command()
def validate() -> None:
    """Validate the current Standards Atlas workspace."""
    typer.echo("Validation is not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def trace() -> None:
    """Inspect traceability information."""
    typer.echo("Traceability inspection is not implemented yet.")
    raise typer.Exit(code=0)
