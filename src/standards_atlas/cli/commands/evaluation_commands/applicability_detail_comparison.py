"""CLI for offline applicability-detail contract A/B comparison."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_detail_comparison import (
    compare_applicability_detail_contracts,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("applicability-detail-compare")
def compare_applicability_detail_runs(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    baseline_run: Annotated[
        Path,
        typer.Option(
            "--baseline-run",
            exists=True,
            dir_okay=False,
            help="Archived qualification run containing the baseline detail result.",
        ),
    ],
    candidate_directory: Annotated[
        Path,
        typer.Option(
            "--candidate-directory",
            exists=True,
            file_okay=False,
            help="Isolated detail-contract output directory produced from the reused selection.",
        ),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Compare a candidate detail contract against an archived baseline without inference."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = compare_applicability_detail_contracts(
            corpus,
            baseline_archive=baseline_run,
            candidate_directory=candidate_directory,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    metrics = report.end_to_end_metrics
    typer.echo(f"Exact selection clauses : {report.selected_clause_count}")
    typer.echo(f"Golden detail candidates: {report.golden_candidate_count}")
    typer.echo(
        "Detail contract          : "
        f"{report.baseline_task_version}/{report.baseline_prompt_version} -> "
        f"{report.candidate_task_version}/{report.candidate_prompt_version}"
    )
    typer.echo(f"Improvements             : {report.improvement_count}")
    typer.echo(f"Regressions              : {report.regression_count}")
    typer.echo(f"Stable wrong             : {report.stable_wrong_count}")
    typer.echo(f"End-to-end TP delta      : {metrics.true_positive_delta:+d}")
    typer.echo(f"End-to-end FP delta      : {metrics.false_positive_delta:+d}")
    typer.echo(f"End-to-end FN delta      : {metrics.false_negative_delta:+d}")
    typer.echo(f"End-to-end F1 delta      : {metrics.f1_delta:+.3f}")
    typer.echo(f"Balanced accuracy delta : {metrics.balanced_accuracy_delta:+.3f}")
    typer.echo(f"Candidate target patterns: {report.candidate_target_pattern_counts}")
    typer.echo(f"Decision transitions     : {report.decision_transition_counts}")
    typer.echo(f"Correctness transitions  : {report.correctness_transition_counts}")
    typer.echo(f"Report                   : {output}")
