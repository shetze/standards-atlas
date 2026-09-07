"""CLI for HITL resolution of applicability-detail prompt disagreements."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_detail_disagreement import (
    build_applicability_detail_disagreement_review,
    evaluate_applicability_detail_hitl_consensus,
    publish_applicability_detail_disagreement_review,
)
from standards_atlas.cli.apps import evaluation_app

_DEFAULT_REVIEW = Path(
    "local/review/applicability/detail-disagreement/applicability-detail-disagreement-review.csv"
)


@evaluation_app.command("applicability-detail-disagreement-build")
def build_applicability_detail_disagreement_hitl(
    run_archive: Annotated[
        Path,
        typer.Option(
            "--run",
            exists=True,
            dir_okay=False,
            help="Archived qualification run providing immutable clause text.",
        ),
    ],
    golden: Annotated[
        Path,
        typer.Option(
            "--golden",
            exists=True,
            dir_okay=False,
            help="Published Applicability Golden corpus used to auto-resolve known cases.",
        ),
    ],
    left_directory: Annotated[
        Path,
        typer.Option("--left-directory", exists=True, file_okay=False),
    ],
    right_directory: Annotated[
        Path,
        typer.Option("--right-directory", exists=True, file_okay=False),
    ],
    review_output: Annotated[
        Path,
        typer.Option("--review-output", dir_okay=False),
    ] = _DEFAULT_REVIEW,
) -> None:
    """Build a flat HITL CSV for all primary v3/v4 detail disagreements."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        result = build_applicability_detail_disagreement_review(
            golden=corpus,
            run_archive=run_archive,
            left_directory=left_directory,
            right_directory=right_directory,
            review_path=review_output,
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Exact selection clauses : {result.selected_clause_count}")
    typer.echo(f"Automatic agreements    : {result.agreement_count}")
    typer.echo(f"Semantic disagreements  : {result.disagreement_count}")
    typer.echo(f"Golden auto-resolved    : {result.golden_auto_resolved_count}")
    typer.echo(f"New HITL cases          : {result.new_hitl_count}")
    typer.echo(f"Source failures         : {result.source_failure_count}")
    typer.echo(f"HITL review CSV         : {result.review_path}")
    typer.echo(f"HITL review guide       : {result.review_guide_path}")
    review_message = (
        "                          EDIT THIS CSV FILE"
        if result.review_created
        else "                          existing review preserved"
    )
    typer.echo(review_message)


@evaluation_app.command("applicability-detail-disagreement-publish")
def publish_applicability_detail_disagreement_hitl(
    review: Annotated[Path, typer.Option("--review", exists=True, dir_okay=False)],
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    golden: Annotated[
        Path,
        typer.Option(
            "--golden",
            exists=True,
            dir_okay=False,
            help="Published Applicability Golden corpus used for automatic resolution.",
        ),
    ],
    left_directory: Annotated[
        Path,
        typer.Option("--left-directory", exists=True, file_okay=False),
    ],
    right_directory: Annotated[
        Path,
        typer.Option("--right-directory", exists=True, file_okay=False),
    ],
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Publish automatic agreements plus reviewed disagreements into HITL consensus."""
    resolved_output = output or review.parent / "applicability-detail-hitl-consensus.json"
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = publish_applicability_detail_disagreement_review(
            golden=corpus,
            review_path=review,
            run_archive=run_archive,
            left_directory=left_directory,
            right_directory=right_directory,
            output_path=resolved_output,
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Automatic agreements    : {report.automatic_agreement_count}")
    typer.echo(f"Semantic disagreements  : {report.disagreement_count}")
    typer.echo(f"Golden auto-resolved    : {report.golden_auto_resolved_count}")
    typer.echo(f"HITL review cases       : {report.hitl_review_count}")
    typer.echo(f"HITL resolved           : {report.hitl_resolved_count}")
    typer.echo(f"HITL pending            : {report.pending_count}")
    typer.echo(f"Source failures         : {report.source_failure_count}")
    typer.echo(f"Final positive          : {report.final_positive_count}")
    typer.echo(f"Final negative          : {report.final_negative_count}")
    typer.echo(f"Consensus report        : {resolved_output}")


@evaluation_app.command("applicability-detail-disagreement-evaluate")
def evaluate_applicability_detail_disagreement_hitl(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    baseline_run: Annotated[
        Path,
        typer.Option("--baseline-run", exists=True, dir_okay=False),
    ],
    consensus: Annotated[Path, typer.Option("--consensus", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Evaluate Presence plus the published v3/v4 HITL consensus against gold."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = evaluate_applicability_detail_hitl_consensus(
            corpus,
            baseline_archive=baseline_run,
            consensus_path=consensus,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Matched golden cases    : {report.matched_cases}")
    typer.echo(f"Unresolved cases        : {report.unresolved_count}")
    typer.echo(
        "End-to-end             : "
        f"TP={report.metrics.true_positive} FP={report.metrics.false_positive} "
        f"FN={report.metrics.false_negative} F1={report.metrics.presence_f1:.3f} "
        f"BAcc={report.metrics.presence_balanced_accuracy:.3f}"
    )
    typer.echo(f"Evaluation report       : {output}")
