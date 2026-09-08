"""CLI commands for offline applicability policy replay and evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_policy_evaluation import (
    evaluate_applicability_policy,
)
from standards_atlas.application.semantic_qualification.applicability_policy_replay import (
    ApplicabilityPolicyReplayReport,
    replay_applicability_policy,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("applicability-policy-replay")
def replay_applicability_policy_command(
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    primary: Annotated[Path, typer.Option("--primary", exists=True, dir_okay=False)],
    rescue: Annotated[Path, typer.Option("--rescue", exists=True, dir_okay=False)],
    confirmation: Annotated[
        Path,
        typer.Option("--confirmation", exists=True, dir_okay=False),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Replay D4 OR (D3 AND D1) from persisted artifacts without inference."""
    try:
        report = replay_applicability_policy(
            run_archive=run_archive,
            primary_report_path=primary,
            rescue_report_path=rescue,
            confirmation_report_path=confirmation,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Policy                   : {report.policy_id} {report.policy_version}")
    typer.echo(f"Consensus clauses        : {report.consensus_clause_count}")
    typer.echo(f"Detail selection         : {report.selected_clause_count}")
    typer.echo(f"Final positive           : {report.final_positive_count}")
    typer.echo(f"Final negative           : {report.final_negative_count}")
    typer.echo(f"Final unknown            : {report.final_unknown_count}")
    typer.echo(f"Report                   : {output}")


@evaluation_app.command("applicability-policy-evaluate")
def evaluate_applicability_policy_command(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    replay: Annotated[Path, typer.Option("--replay", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    max_false_positive: Annotated[int, typer.Option("--max-fp", min=0)] = 2,
    max_false_negative: Annotated[int, typer.Option("--max-fn", min=0)] = 2,
) -> None:
    """Evaluate an offline policy replay against published applicability gold."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        replay_report = ApplicabilityPolicyReplayReport.load(replay)
        report = evaluate_applicability_policy(
            corpus,
            replay_report,
            max_false_positive=max_false_positive,
            max_false_negative=max_false_negative,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    metrics = report.metrics
    typer.echo(f"Published gold cases     : {report.published_cases}")
    typer.echo(f"Matched gold cases       : {report.matched_cases}")
    typer.echo(f"Missing gold cases       : {len(report.missing_cases)}")
    typer.echo(f"Unknown gold decisions   : {len(report.unknown_cases)}")
    typer.echo(f"False positives          : {metrics.false_positive} / {report.max_false_positive}")
    typer.echo(f"False negatives          : {metrics.false_negative} / {report.max_false_negative}")
    typer.echo(f"Qualification passed     : {'yes' if report.passed else 'no'}")
    typer.echo(f"Report                   : {output}")
