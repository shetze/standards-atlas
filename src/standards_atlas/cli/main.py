"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.cli.printers import print_document_summary
from standards_atlas.adapters.atlasdata import AtlasDataReader

app = typer.Typer(
    name="standards-atlas",
    help="Semantic traceability platform for technical standards.",
    no_args_is_help=True,
)

inspect_app = typer.Typer(
    help="Inspect Standards Atlas artifacts for debugging and development.",
    no_args_is_help=True,
)

app.add_typer(inspect_app, name="inspect")


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show the Standards Atlas version and exit."),
    ] = False,
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


@inspect_app.command("data")
def inspect_data(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Atlas data file to inspect.",
        ),
    ],
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Show parsed clause details."),
    ] = False,
) -> None:
    """Inspect a legacy Atlas data file through the canonical domain model."""
    reader = AtlasDataReader()
    document = reader.read_document(file)
    print_document_summary(document, source_file=file, verbose=verbose)


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


if __name__ == "__main__":
    app()
