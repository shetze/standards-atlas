"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(
    name="standards-atlas",
    help="Semantic traceability platform for technical standards.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show the Standards Atlas version and exit.",
        ),
    ] = False,
) -> None:
    """Standards Atlas command-line entry point."""
    if version:
        from standards_atlas import __version__

        typer.echo(f"standards-atlas {__version__}")
        raise typer.Exit()


@app.command()
def info() -> None:
    """Show basic project information."""
    typer.echo("Standards Atlas")
    typer.echo("Semantic traceability platform for technical standards.")


@app.command()
def validate() -> None:
    """Validate the current Standards Atlas workspace.

    This command is intentionally minimal in PR 1.
    Full validation will be added after the domain model exists.
    """
    typer.echo("Validation is not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def trace() -> None:
    """Inspect traceability information.

    This command is a placeholder for the future Traceability API.
    """
    typer.echo("Traceability inspection is not implemented yet.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
