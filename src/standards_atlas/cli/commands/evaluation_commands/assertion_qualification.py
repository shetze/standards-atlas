"""CLI for assertion golden-suite evaluation and Slice-7B cascade execution."""

from __future__ import annotations

import hashlib
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
    AssertionAutoAdoptionPolicyEvaluator,
    AssertionGoldenPartition,
    AssertionQualificationCascadeService,
    AssertionQualificationEvaluator,
    AssertionReviewPilotBuildRequest,
    AssertionReviewTargetSuite,
    attach_cascade_to_assertion_review_pilot,
    build_assertion_review_pilot,
    load_applicability_selection_corpus,
    load_assertion_auto_adoption_policy,
    load_assertion_golden_suite,
    load_assertion_qualification_cascade_report,
    load_assertion_qualification_report,
    load_assertion_review_pilot,
    load_document_knowledge_proposal,
    publish_assertion_review_pilot,
    review_clause_ids,
    select_applicability_pilot_cases,
    validate_assertion_review_pilot_document,
    write_assertion_auto_adoption_report,
    write_assertion_golden_suite,
    write_assertion_qualification_cascade_report,
    write_assertion_qualification_report,
    write_assertion_review_pilot,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import DocumentKey


@evaluation_app.command("assertion-review-pilot-build")
def build_assertion_review_pilot_command(
    source: Annotated[
        Path,
        typer.Option(
            "--source",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Applicability golden corpus used only as the pilot clause selection source.",
        ),
    ],
    ontology_version: Annotated[
        list[str],
        typer.Option(
            "--ontology-version",
            help="Formal ontology reference '<id>@<version>'; repeat for the target suite.",
        ),
    ],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    review_id: Annotated[str, typer.Option("--review-id")] = "assertion-pilot",
    review_version: Annotated[str, typer.Option("--review-version")] = "0.1.0",
    suite_id: Annotated[str, typer.Option("--suite-id")] = "assertion-pilot-development",
    suite_version: Annotated[str, typer.Option("--suite-version")] = "0.1.0",
    partition: Annotated[
        AssertionGoldenPartition, typer.Option("--partition")
    ] = AssertionGoldenPartition.DEVELOPMENT,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
    clause_id: Annotated[
        list[str] | None,
        typer.Option(
            "--clause-id",
            help="Explicit published source clause id; repeat to bypass stratified selection.",
        ),
    ] = None,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = Path(
        "local/review/assertions/pilot/assertion-review-pilot.yaml"
    ),
) -> None:
    """Build a verified editable assertion review pilot from applicability gold cases."""
    try:
        corpus = load_applicability_selection_corpus(source)
        repository = FileSystemEngineeringDocumentRepository(workspace)
        explicit_clause_ids = tuple(clause_id or ())
        if explicit_clause_ids:
            selected = select_applicability_pilot_cases(
                corpus, limit=limit, clause_ids=explicit_clause_ids
            )
            documents = {
                document_key: repository.load(DocumentKey(value=document_key))
                for document_key in sorted({case.document_key for case in selected})
            }
        else:
            source_document_keys = sorted(
                {
                    case.document_key
                    for case in corpus.cases
                    if case.status == "published"
                    and case.expected is not None
                    and case.provenance is not None
                }
            )
            scope_documents = {
                document_key: repository.load(DocumentKey(value=document_key))
                for document_key in source_document_keys
            }
            selected = select_applicability_pilot_cases(
                corpus, limit=limit, documents=scope_documents
            )
            documents = {
                document_key: scope_documents[document_key]
                for document_key in sorted({case.document_key for case in selected})
            }
        target_suite = AssertionReviewTargetSuite(
            id=suite_id,
            version=suite_version,
            partition=partition,
            ontology_versions=tuple(ontology_version),
        )
        review = build_assertion_review_pilot(
            corpus,
            selected,
            documents,
            AssertionReviewPilotBuildRequest(
                review_id=review_id,
                review_version=review_version,
                target_suite=target_suite,
                source_corpus_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                limit=limit,
                clause_ids=explicit_clause_ids,
            ),
        )
        review_path = write_assertion_review_pilot(review, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    positive = sum(case.applicability_source.present for case in review.cases)
    typer.echo(f"Review                  : {review.review_id}@{review.review_version}")
    typer.echo(f"Selection               : {review.selection.strategy}")
    typer.echo(f"Selected clauses        : {len(review.cases)}")
    typer.echo(
        f"Applicability provenance: {positive} present / {len(review.cases) - positive} absent"
    )
    source_text_drift = sum(
        not case.applicability_source.selection_text_matches_current for case in review.cases
    )
    typer.echo(f"Selection text drift    : {source_text_drift} case(s); current text embedded")
    typer.echo(
        "Documents               : "
        + ", ".join(sorted({case.document_key for case in review.cases}))
    )
    typer.echo(f"Review artifact         : {review_path}")


@evaluation_app.command("assertion-review-pilot-attach")
def attach_assertion_review_pilot_command(
    review: Annotated[Path, typer.Option("--review", exists=True, dir_okay=False, readable=True)],
    cascade_report: Annotated[
        Path, typer.Option("--cascade-report", exists=True, dir_okay=False, readable=True)
    ],
    efficient_proposal: Annotated[
        Path, typer.Option("--efficient-proposal", exists=True, dir_okay=False, readable=True)
    ],
    escalation_proposal: Annotated[
        Path | None,
        typer.Option("--escalation-proposal", exists=True, dir_okay=False, readable=True),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Attach one document's exact final cascade candidates to an existing pilot review."""
    try:
        pilot = load_assertion_review_pilot(review)
        cascade = load_assertion_qualification_cascade_report(cascade_report)
        efficient = load_document_knowledge_proposal(efficient_proposal)
        escalation = (
            load_document_knowledge_proposal(escalation_proposal)
            if escalation_proposal is not None
            else None
        )
        updated = attach_cascade_to_assertion_review_pilot(
            pilot,
            cascade=cascade,
            efficient=efficient,
            escalation=escalation,
        )
        target = output or review
        review_path = write_assertion_review_pilot(updated, target)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    attached = sum(
        case.document_key == cascade.source_document_key and case.proposal is not None
        for case in updated.cases
    )
    typer.echo(f"Document                : {cascade.source_document_key}")
    typer.echo(f"Attached cases          : {attached}")
    typer.echo(f"Review artifact         : {review_path}")


@evaluation_app.command("assertion-review-pilot-publish")
def publish_assertion_review_pilot_command(
    review: Annotated[Path, typer.Option("--review", exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = Path(
        "local/review/assertions/pilot/assertion-golden-suite.yaml"
    ),
) -> None:
    """Publish a completed pilot review into the current AssertionGoldenSuite contract."""
    try:
        pilot = load_assertion_review_pilot(review)
        suite = publish_assertion_review_pilot(pilot)
        suite_path = write_assertion_golden_suite(suite, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Golden suite            : {suite.id}@{suite.version}")
    typer.echo(f"Partition               : {suite.partition.value}")
    typer.echo(f"Documents               : {len(suite.cases)}")
    typer.echo(f"Reviewed clauses        : {len(pilot.cases)}")
    typer.echo(f"Golden suite artifact   : {suite_path}")


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
    review_pilot: Annotated[
        Path | None,
        typer.Option(
            "--review-pilot",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Use the exact Slice-7D pilot clause selection for this document.",
        ),
    ] = None,
    clause_id: Annotated[
        list[str] | None,
        typer.Option("--clause-id", help="Limit the cascade to selected clause ids."),
    ] = None,
) -> None:
    """Run the threshold-free Efficient → Verify → Escalate assertion cascade."""
    try:
        if review_pilot is not None and clause_id:
            raise ValueError("--review-pilot and --clause-id are mutually exclusive")
        selected_clause_ids = frozenset(clause_id) if clause_id else None
        if review_pilot is not None:
            pilot = load_assertion_review_pilot(review_pilot)
            if pilot.target_suite.ontology_versions != tuple(ontology_version):
                raise ValueError(
                    "review pilot ontology versions do not match --ontology-version selection"
                )
            selected_clause_ids = frozenset(review_clause_ids(pilot, document_key=document_key))

        base_config = LlmConfig.load(config)
        gateway = OpenAICompatibleLlmGateway(base_config)
        service = AssertionQualificationCascadeService(
            efficient_extractor=OntologyGuidedKnowledgeProposalExtractor(
                gateway,
                model=efficient_model,
                provider=gateway.provider,
                prompt_version="ontology-guided-assertions-v2",
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
                prompt_version="ontology-guided-assertions-v2",
            ),
        )
        document = FileSystemEngineeringDocumentRepository(workspace).load(
            DocumentKey(value=document_key)
        )
        if review_pilot is not None:
            validate_assertion_review_pilot_document(pilot, document)
        result = service.run_document(
            document,
            cascade_run_id=cascade_run_id,
            efficient_proposal_run_id=efficient_run_id,
            escalation_proposal_run_id=escalation_run_id,
            ontology_versions=tuple(ontology_version),
            clause_ids=selected_clause_ids,
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


@evaluation_app.command("assertion-auto-adoption")
def evaluate_assertion_auto_adoption(
    policy: Annotated[
        Path,
        typer.Option(
            "--policy",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Versioned assertion auto-adoption policy YAML or JSON.",
        ),
    ],
    development_golden: Annotated[
        Path,
        typer.Option(
            "--development-golden",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Development assertion golden suite used by the qualification report.",
        ),
    ],
    development_report: Annotated[
        Path,
        typer.Option(
            "--development-report",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Development assertion qualification report.",
        ),
    ],
    holdout_golden: Annotated[
        Path,
        typer.Option(
            "--holdout-golden",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Protected holdout assertion golden suite used by the qualification report.",
        ),
    ],
    holdout_report: Annotated[
        Path,
        typer.Option(
            "--holdout-report",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Holdout assertion qualification report.",
        ),
    ],
    cascade_report: Annotated[
        Path,
        typer.Option(
            "--cascade-report",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Slice-7B cascade report for the production candidate document.",
        ),
    ],
    efficient_proposal: Annotated[
        Path,
        typer.Option(
            "--efficient-proposal",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Exact efficient-stage proposal artifact referenced by the cascade report.",
        ),
    ],
    escalation_proposal: Annotated[
        Path | None,
        typer.Option(
            "--escalation-proposal",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Exact escalation proposal artifact when the cascade escalated clauses.",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Destination Slice-7C auto-adoption eligibility report.",
        ),
    ] = Path("local/evaluation/assertion-auto-adoption.json"),
) -> None:
    """Evaluate Development/Holdout gates and per-assertion auto-adoption eligibility."""
    try:
        policy_contract = load_assertion_auto_adoption_policy(policy)
        development_suite = load_assertion_golden_suite(development_golden)
        development_metrics = load_assertion_qualification_report(development_report)
        holdout_suite = load_assertion_golden_suite(holdout_golden)
        holdout_metrics = load_assertion_qualification_report(holdout_report)
        cascade = load_assertion_qualification_cascade_report(cascade_report)
        efficient = load_document_knowledge_proposal(efficient_proposal)
        escalation = (
            load_document_knowledge_proposal(escalation_proposal)
            if escalation_proposal is not None
            else None
        )
        report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
            policy=policy_contract,
            development_suite=development_suite,
            development_report=development_metrics,
            holdout_suite=holdout_suite,
            holdout_report=holdout_metrics,
            cascade_report=cascade,
            efficient_proposal=efficient,
            escalation_proposal=escalation,
        )
        report_path = write_assertion_auto_adoption_report(report, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Policy                  : {report.policy_id}@{report.policy_version}")
    typer.echo(f"Development gate        : {'PASS' if report.development_gate.passed else 'FAIL'}")
    typer.echo(f"Holdout gate            : {'PASS' if report.holdout_gate.passed else 'FAIL'}")
    typer.echo(
        f"Pipeline identity       : {'PASS' if report.pipeline_identity_gate.passed else 'FAIL'}"
    )
    typer.echo(
        f"Qualification gate      : {'PASS' if report.qualification_gate_passed else 'FAIL'}"
    )
    typer.echo(f"Auto-adoption eligible  : {report.auto_adoption_eligible_assertions}")
    typer.echo(f"Review required         : {report.review_required_assertions}")
    typer.echo(f"Report                  : {report_path}")
