"""Source readiness and bounded Process-Function regression checks."""

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.semantic_readiness import (
    evaluate_semantic_readiness,
)
from standards_atlas.application.semantic_qualification.taxonomy_pilot import build_taxonomy_pilot
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("taxonomy-pilot")
def taxonomy_pilot_command(
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    run: Annotated[Path | None, typer.Option("--run", exists=True)] = None,
    dataset: Annotated[Path | None, typer.Option("--dataset", exists=True, dir_okay=False)] = None,
    synthetic_smoke: Annotated[
        bool,
        typer.Option(
            "--synthetic-smoke",
            help="Explicit synthetic fixture authority, not real source review.",
        ),
    ] = False,
    dataset_version: Annotated[str, typer.Option("--dataset-version")] = "2.2.0",
    limit: Annotated[int, typer.Option("--limit", min=1)] = 24,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
) -> None:
    """Prepare fixed/hint/conflict controls without confirming legacy sources or rules."""
    try:
        report = build_taxonomy_pilot(
            output_directory=output,
            resources=resources,
            run=run,
            dataset=dataset,
            synthetic_smoke=synthetic_smoke,
            dataset_version=dataset_version,
            limit=limit,
        )
    except (ValueError, OSError, KeyError, TypeError, BadZipFile, yaml.YAMLError) as exc:
        typer.echo(f"Taxonomy pilot failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Scope: {report['scope']}; selected: {report['selected_count']}")
    typer.echo(f"Fixed attributes: {report['decision_plan_summary']['fixed_attribute_count']}")
    typer.echo(f"Dataset: {output / 'dataset.json'}")
    typer.echo("No rules released; source-review.csv remains pending independent review.")


@evaluation_app.command("semantic-readiness-evaluate")
def semantic_readiness_evaluate_command(
    audit: Annotated[Path, typer.Option("--audit", exists=True, dir_okay=False)],
    checks: Annotated[Path, typer.Option("--checks", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
) -> None:
    """Evaluate source-bound sentinels, retaining missing/invalid results as unavailable."""
    try:
        report = evaluate_semantic_readiness(audit=audit, checks=checks, output_directory=output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Semantic readiness evaluation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Sentinel checks: {report['status_counts']}")
    typer.echo(f"Report: {output / 'semantic-readiness.json'}")
    typer.echo("Not a production qualification or a rule release.")
