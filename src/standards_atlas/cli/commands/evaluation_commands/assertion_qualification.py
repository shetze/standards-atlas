"""CLI for assertion golden-suite evaluation and Slice-7B cascade execution."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.filesystem import (
    FileSystemDocumentKnowledgeProposalRepository,
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.llm import (
    LlmConfig,
    OntologyGuidedAssertionProposalVerifier,
    OntologyGuidedKnowledgeProposalExtractor,
    OpenAICompatibleLlmGateway,
)
from standards_atlas.application.assertion_qualification import (
    AssertionQualificationCascadeService,
    AssertionQualificationEvaluator,
    load_assertion_golden_suite,
    load_document_knowledge_proposal,
    write_assertion_qualification_cascade_report,
    write_assertion_qualification_report,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import DocumentKey


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


@evaluation_app.command("assertion-cascade")
def run_assertion_qualification_cascade(
    document_key: Annotated[str, typer.Option("--document-key")],
    ontology_version: Annotated[
        list[str],
        typer.Option(
            "--ontology-version",
            help="Formal ontology reference '<id>@<version>'; repeat for the ordered selection.",
        ),
    ],
    efficient_model: Annotated[str, typer.Option("--efficient-model")],
    verifier_model: Annotated[str, typer.Option("--verifier-model")],
    escalation_model: Annotated[str, typer.Option("--escalation-model")],
    cascade_run_id: Annotated[str, typer.Option("--cascade-run-id")],
    efficient_run_id: Annotated[str, typer.Option("--efficient-run-id")],
    escalation_run_id: Annotated[str, typer.Option("--escalation-run-id")],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    config: Annotated[
        Path, typer.Option("--config", exists=True, readable=True, dir_okay=False)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = Path(
        "local/evaluation/assertion-cascade.json"
    ),
    clause_id: Annotated[
        list[str] | None,
        typer.Option("--clause-id", help="Limit the cascade to selected clause ids."),
    ] = None,
) -> None:
    """Run the threshold-free Efficient → Verify → Escalate assertion cascade."""
    try:
        base_config = LlmConfig.load(config)
        gateway = OpenAICompatibleLlmGateway(base_config)
        service = AssertionQualificationCascadeService(
            efficient_extractor=OntologyGuidedKnowledgeProposalExtractor(
                gateway,
                model=efficient_model,
                provider=gateway.provider,
                prompt_version="ontology-guided-assertions-v1",
            ),
            verifier=OntologyGuidedAssertionProposalVerifier(
                gateway,
                model=verifier_model,
                provider=gateway.provider,
            ),
            escalation_extractor=OntologyGuidedKnowledgeProposalExtractor(
                gateway,
                model=escalation_model,
                provider=gateway.provider,
                prompt_version="ontology-guided-assertions-v1",
            ),
        )
        document = FileSystemEngineeringDocumentRepository(workspace).load(
            DocumentKey(value=document_key)
        )
        result = service.run_document(
            document,
            cascade_run_id=cascade_run_id,
            efficient_proposal_run_id=efficient_run_id,
            escalation_proposal_run_id=escalation_run_id,
            ontology_versions=tuple(ontology_version),
            clause_ids=frozenset(clause_id) if clause_id else None,
        )
        proposal_repository = FileSystemDocumentKnowledgeProposalRepository(workspace)
        proposal_repository.save(result.efficient_proposal)
        if result.escalation_proposal is not None:
            proposal_repository.save(result.escalation_proposal)
        report_path = write_assertion_qualification_cascade_report(result.report, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Cascade run             : {result.report.cascade_run_id}")
    typer.echo(f"Document                : {result.report.source_document_key}")
    typer.echo(f"Efficient accepted      : {result.report.efficient_accepted_clauses}")
    typer.echo(f"Escalated               : {result.report.escalated_clauses}")
    typer.echo(f"Report                  : {report_path}")
