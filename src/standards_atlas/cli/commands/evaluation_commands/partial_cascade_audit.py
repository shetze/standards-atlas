"""Offline cause analysis of an existing partial cascade."""

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer

from standards_atlas.application.semantic_qualification.partial_cascade_audit import (
    audit_partial_cascade,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("partial-cascade-audit")
def audit_partial_cascade_command(
    experiment: Annotated[Path, typer.Option("--experiment", exists=True)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
) -> None:
    """Verify and explain stored stages, models and attempts without changing them."""
    try:
        report = audit_partial_cascade(
            experiment=experiment,
            output_directory=output,
            resources=resources,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, BadZipFile) as exc:
        typer.echo(f"Partial cascade audit failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Verified clauses: {report['selected_count']}; no model calls.")
    typer.echo(f"Report: {output / 'partial-cascade-audit.json'}")
