"""Read-only inspection of partial experiment evidence, including incomplete uploads."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer

from standards_atlas.application.semantic_qualification.partial_audit import (
    audit_partial_experiment,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("partial-audit")
def audit_partial_experiment_command(
    experiment: Annotated[
        Path,
        typer.Option(
            "--experiment",
            exists=True,
            readable=True,
            help="Experiment directory, its ZIP, or a partial-run-report JSON.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False, help="New separate audit directory."),
    ],
    run: Annotated[
        Path | None,
        typer.Option(
            "--run",
            exists=True,
            readable=True,
            help="Optional original qualification corpus ZIP/directory.",
        ),
    ] = None,
    dataset: Annotated[
        Path | None,
        typer.Option(
            "--dataset",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Optional source dataset; mutually exclusive with --run.",
        ),
    ] = None,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
) -> None:
    """Report all checkable conflicts; never infer, repair, adopt or publish answers."""
    try:
        report = audit_partial_experiment(
            experiment=experiment,
            output_directory=output,
            resources=resources,
            run=run,
            dataset=dataset,
        )
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, BadZipFile) as exc:
        typer.echo(f"Partial audit failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Selected / accounted : {report['selected_count']} / {report['accounted_count']}")
    typer.echo(f"Response inspection  : {report['response_status_counts']}")
    typer.echo(f"Decision plans       : {report['plan_status_counts']}")
    typer.echo(f"Integrity error cases: {report['integrity_error_case_count']}")
    typer.echo(f"Report               : {output / 'partial-audit.json'}")
    typer.echo("Read-only diagnostic; no model calls or acceptance changes.")
