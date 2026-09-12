"""Read-only taxonomy predecision diagnostics; never activates a cascade policy."""

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.taxonomy_diagnostics import (
    diagnose_taxonomy_decisions,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("taxonomy-decisions")
def diagnose_taxonomy_decisions_command(
    output: Annotated[Path, typer.Option("--output", help="New, separate diagnostic directory.")],
    run: Annotated[
        Path | None,
        typer.Option(
            "--run",
            exists=True,
            readable=True,
            help="Qualification ZIP or directory with immutable selection.",
        ),
    ] = None,
    dataset: Annotated[
        Path | None,
        typer.Option(
            "--dataset",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Standalone corpus dataset; mutually exclusive with --run.",
        ),
    ] = None,
) -> None:
    """Inspect source-grounded rules without LLM calls, routing changes or publication."""
    try:
        json_path, markdown_path = diagnose_taxonomy_decisions(
            run=run,
            dataset=dataset,
            output_directory=output,
        )
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, yaml.YAMLError) as exc:
        typer.echo(f"Taxonomy diagnostics failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Taxonomy diagnostic JSON : {json_path}")
    typer.echo(f"Taxonomy report          : {markdown_path}")
    typer.echo("Mode                     : diagnostic only; no inference or routing changes")
