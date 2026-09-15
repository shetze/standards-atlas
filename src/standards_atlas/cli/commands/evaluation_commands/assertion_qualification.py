"""CLI for Slice-7A assertion golden-suite evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.assertion_qualification import (
    AssertionQualificationEvaluator,
    load_assertion_golden_suite,
    load_document_knowledge_proposal,
    write_assertion_qualification_report,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("assertion-evaluate")
def evaluate_assertion_proposals(
    golden: Annotated[
        Path,
        typer.Option(
            "--golden",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Assertion golden-suite YAML or JSON.",
        ),
    ],
    proposal: Annotated[
        list[Path],
        typer.Option(
            "--proposal",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Persisted DocumentKnowledgeProposal artifact; repeat for multiple documents.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Destination assertion qualification JSON report.",
        ),
    ] = Path("local/evaluation/assertion-qualification.json"),
) -> None:
    """Evaluate proposal entities/assertions against an exact versioned golden suite."""
    try:
        suite = load_assertion_golden_suite(golden)
        proposals = tuple(load_document_knowledge_proposal(path) for path in proposal)
        report = AssertionQualificationEvaluator().evaluate(suite, proposals)
        report_path = write_assertion_qualification_report(report, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    aggregate = report.aggregate
    typer.echo(f"Golden suite            : {report.golden_suite_id}@{report.golden_suite_version}")
    typer.echo(f"Partition               : {report.golden_partition.value}")
    typer.echo(f"Documents               : {aggregate.documents}")
    typer.echo(
        "Entities                : "
        f"P={aggregate.entities.precision:.4f}, "
        f"R={aggregate.entities.recall:.4f}, F1={aggregate.entities.f1:.4f}"
    )
    typer.echo(
        "Assertions              : "
        f"P={aggregate.assertions.precision:.4f}, "
        f"R={aggregate.assertions.recall:.4f}, F1={aggregate.assertions.f1:.4f}"
    )
    typer.echo(
        f"Normative force accuracy: {_format_accuracy(aggregate.normative_force_accuracy.accuracy)}"
    )
    typer.echo(
        f"Grounding accuracy      : {_format_accuracy(aggregate.grounding_accuracy.accuracy)}"
    )
    typer.echo(f"Report                  : {report_path}")


def _format_accuracy(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
