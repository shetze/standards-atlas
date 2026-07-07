"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.adapters.atlasdata.parser import parse_standard_file

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
        typer.Option("--verbose", "-v"),
    ] = False,
) -> None:
    """Inspect an Atlas data file."""

    standard = parse_standard_file(file)

    typer.echo(f"File                  : {file.name}")
    typer.echo(f"Standard              : {standard.metadata.name}")

    if standard.metadata.parent:
        typer.echo(f"Parent                : {standard.metadata.parent}")

    if standard.metadata.official_year:
        typer.echo(f"Official year         : {standard.metadata.official_year}")

    typer.echo(f"Digits                : {standard.metadata.digits}")
    typer.echo(f"Part digits           : {standard.metadata.part_digits}")
    typer.echo(f"Part shift            : {standard.metadata.part_shift}")

    typer.echo()
    typer.echo(f"Structure items       : {len(standard.structure_items)}")
    typer.echo(f"Initialization records: {len(standard.initialization_records)}")

    if verbose:
        typer.echo()
        typer.echo("First structure items:")
        typer.echo("----------------------")

        for item in standard.structure_items[:20]:
            typer.echo(
                f"{item.item_type.value:12} "
                f"{item.visible_reference}"
            )


if __name__ == "__main__":
    app()
