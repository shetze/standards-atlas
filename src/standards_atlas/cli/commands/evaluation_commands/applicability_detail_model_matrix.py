"""CLI for applicability-detail prompt-by-model comparison matrices."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_detail_model_matrix import (
    build_applicability_detail_model_matrix,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("applicability-detail-model-matrix")
def compare_applicability_detail_model_matrix(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    baseline_run: Annotated[
        Path,
        typer.Option(
            "--baseline-run",
            exists=True,
            dir_okay=False,
            help="Archived qualification run containing the shared baseline detail result.",
        ),
    ],
    candidate_directories: Annotated[
        list[Path],
        typer.Option(
            "--candidate-directory",
            exists=True,
            file_okay=False,
            help="Repeat for each isolated prompt/model detail output directory.",
        ),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Summarize several prompt/model detail candidates against one archived baseline."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = build_applicability_detail_model_matrix(
            corpus,
            baseline_archive=baseline_run,
            candidate_directories=tuple(candidate_directories),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(
        f"Baseline                 : {report.baseline_model_id} / {report.baseline_prompt_version}"
    )
    typer.echo(f"Exact selection clauses : {report.selected_clause_count}")
    typer.echo(f"Candidates               : {len(report.rows)}")
    for row in report.rows:
        typer.echo(
            "Candidate                : "
            f"{row.model_id} / {row.prompt_version} "
            f"TP={row.metrics.true_positive} FP={row.metrics.false_positive} "
            f"FN={row.metrics.false_negative} F1={row.metrics.presence_f1:.3f} "
            f"BAcc={row.metrics.presence_balanced_accuracy:.3f}"
        )
    typer.echo(f"Report                   : {output}")
