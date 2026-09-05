"""CLI for offline applicability Presence plus detail end-to-end evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_end_to_end import (
    evaluate_applicability_end_to_end,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("applicability-end-to-end-evaluate")
def evaluate_applicability_end_to_end_corpus(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Evaluate final Presence consensus plus archived detail verification against HITL gold."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = evaluate_applicability_end_to_end(corpus, run_archive)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    presence = report.presence_detection
    detail = report.detail_verification
    end_to_end = report.end_to_end
    typer.echo(f"Published gold cases     : {report.published_cases}")
    typer.echo(f"Matched gold cases       : {report.matched_cases}")
    typer.echo(
        "Golden Presence candidates: "
        f"{detail.golden_presence_candidate_count} / {report.matched_cases}"
    )
    typer.echo(f"Run Presence candidates  : {detail.source_presence_candidate_count}")
    typer.echo(f"Presence recall          : {presence.presence_recall:.3f}")
    typer.echo(f"Detail confirmed         : {detail.confirmed_clause_applicability_count}")
    typer.echo(f"Detail rejected          : {detail.rejected_non_clause_count}")
    typer.echo(f"Detail failed            : {detail.failed_candidate_count}")
    typer.echo(f"False positives rejected : {detail.false_positive_rejected_count}")
    typer.echo(f"True positives retained  : {detail.true_positive_retained_count}")
    typer.echo(f"True positives rejected  : {detail.true_positive_rejected_count}")
    typer.echo(f"End-to-end unresolved    : {report.end_to_end_unresolved_count}")
    typer.echo(f"End-to-end precision     : {end_to_end.presence_precision:.3f}")
    typer.echo(f"End-to-end recall        : {end_to_end.presence_recall:.3f}")
    typer.echo(f"End-to-end F1            : {end_to_end.presence_f1:.3f}")
    typer.echo(f"Report                   : {output}")
