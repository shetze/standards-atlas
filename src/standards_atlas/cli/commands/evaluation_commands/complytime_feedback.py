"""Import ComplyTime/Gemara EvaluationLog results as Standards Atlas feedback."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from standards_atlas.adapters.complytime import EvaluationLogFeedbackImporter
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("complytime-feedback")
def import_complytime_feedback(
    evaluation_log: Annotated[
        Path,
        typer.Option(
            "--log",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Gemara EvaluationLog YAML or JSON produced by ComplyTime/evaluator tooling.",
        ),
    ],
    bundle: Annotated[
        Path,
        typer.Option(
            "--bundle",
            exists=True,
            readable=True,
            file_okay=False,
            help="Standards Atlas ComplyTime governance bundle used by the evaluation.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            dir_okay=False,
            help=(
                "Feedback JSON destination. Defaults to "
                "local/evaluation/complytime/<log-stem>-feedback.json."
            ),
        ),
    ] = None,
) -> None:
    """Resolve a Gemara EvaluationLog back to Standards Atlas clause provenance."""
    target = output or (
        Path("local/evaluation/complytime") / f"{evaluation_log.stem}-feedback.json"
    )
    try:
        result = EvaluationLogFeedbackImporter().import_log(
            evaluation_log,
            bundle,
            target,
        )
    except (OSError, ValueError, ValidationError) as exc:
        typer.echo(f"ComplyTime feedback import failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"EvaluationLog          : {evaluation_log}")
    typer.echo(f"Governance bundle      : {bundle}")
    typer.echo(f"Feedback               : {result}")
