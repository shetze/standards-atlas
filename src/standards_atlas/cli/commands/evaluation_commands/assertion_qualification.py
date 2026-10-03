"""CLI for assertion golden-suite evaluation and assertion review workflows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.filesystem import (
    FileSystemContextSourcePackageRepository,
    FileSystemDocumentKnowledgeProposalRepository,
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.assertion_qualification import (
    AssertionAutoAdoptionPolicyEvaluator,
    AssertionGoldenPartition,
    AssertionQualificationEvaluator,
    AssertionReviewPilotBuildRequest,
    AssertionReviewTargetSuite,
    attach_cascade_to_assertion_review_pilot,
    build_assertion_review_pilot,
    golden_suite_sha256,
    load_applicability_selection_corpus,
    load_assertion_auto_adoption_policy,
    load_assertion_golden_suite,
    load_assertion_qualification_cascade_report,
    load_assertion_qualification_report,
    load_assertion_review_audit,
    load_assertion_review_pilot,
    load_document_knowledge_proposal,
    publish_assertion_review_pilot,
    qualification_report_sha256,
    review_clause_ids,
    run_ap03_preflight,
    select_applicability_pilot_cases,
    validate_assertion_review_pilot_document,
    write_assertion_auto_adoption_report,
    write_assertion_golden_suite,
    write_assertion_qualification_cascade_report,
    write_assertion_qualification_report,
    write_assertion_qualification_summary,
    write_assertion_review_pilot,
)
from standards_atlas.application.assertion_qualification.io import ensure_distinct_output
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import DocumentKey


@evaluation_app.command("assertion-ap03-preflight")
def run_assertion_ap03_preflight_command(
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Optional text-free JSON report path; omit to print to stdout.",
        ),
    ] = None,
) -> None:
    """Inspect AP03 inputs and frozen B0 bindings without model or network execution."""

    try:
        report = run_ap03_preflight(project_root)
        rendered = (
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        if output is None:
            typer.echo(rendered, nl=False)
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        typer.echo(f"AP03 preflight: {output}")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


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
        ensure_distinct_output(output, review)
        audit = load_assertion_review_audit(review)
        suite = publish_assertion_review_pilot(audit)
        suite_path = write_assertion_golden_suite(suite, output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Golden suite            : {suite.id}@{suite.version}")
    typer.echo(f"Partition               : {suite.partition.value}")
    documents = len({case.source_document_key for case in suite.cases})
    typer.echo(f"Documents               : {documents}")
    typer.echo(f"Reviewed clauses        : {len(suite.cases)}")
    typer.echo(f"Golden suite SHA-256    : {golden_suite_sha256(suite)}")
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
        list[Path] | None,
        typer.Option(
            "--proposal",
            exists=True,
            dir_okay=False,
            readable=True,
            help=(
                "Native DocumentKnowledgeProposal artifact; repeat per document. Excludes --review."
            ),
        ),
    ] = None,
    review: Annotated[
        Path | None,
        typer.Option(
            "--review",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Evaluate all stored review snapshots offline. Excludes --proposal.",
        ),
    ] = None,
    source_review: Annotated[
        Path | None,
        typer.Option(
            "--source-review",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Archived review for source verification only; candidates still use --proposal.",
        ),
    ] = None,
    source_package_workspace: Annotated[
        Path | None,
        typer.Option(
            "--source-package-workspace",
            exists=True,
            file_okay=False,
            readable=True,
            help=(
                "Workspace containing private AP02 context-source-packages referenced by "
                "native proposal bindings. Excludes --review."
            ),
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Destination assertion qualification JSON report.",
        ),
    ] = Path("local/evaluation/assertion-qualification.json"),
    summary_output: Annotated[
        Path | None,
        typer.Option(
            "--summary-output",
            dir_okay=False,
            help="Optional deterministic Markdown summary for the same report.",
        ),
    ] = None,
) -> None:
    """Evaluate proposal entities/assertions against an exact versioned golden suite."""
    try:
        if bool(proposal) == (review is not None):
            raise ValueError(
                "exactly one of --proposal or --review is required (mutually exclusive)"
            )
        if review is not None and source_review is not None:
            raise ValueError("--source-review is only valid with --proposal, not --review")
        if review is not None and source_package_workspace is not None:
            raise ValueError(
                "--source-package-workspace is only valid with --proposal, not --review"
            )
        sources = [golden, *(proposal or ())]
        sources.extend(path for path in (review, source_review) if path is not None)
        ensure_distinct_output(output, *sources)
        if summary_output is not None:
            ensure_distinct_output(summary_output, *sources, output)
            ensure_distinct_output(output, summary_output)
        suite = load_assertion_golden_suite(golden)
        proposals = (
            tuple(load_document_knowledge_proposal(path) for path in proposal) if proposal else None
        )
        source_packages = None
        if proposals is not None and source_package_workspace is not None:
            package_repository = FileSystemContextSourcePackageRepository(source_package_workspace)
            source_packages = tuple(
                package
                for candidate in proposals
                for binding in candidate.context_source_bindings
                if (package := package_repository.load(binding)) is not None
            )
        report = AssertionQualificationEvaluator().evaluate(
            suite,
            proposals,
            review_audit=load_assertion_review_audit(review) if review is not None else None,
            source_audit=load_assertion_review_audit(source_review) if source_review else None,
            source_packages=source_packages,
        )
        report_path = write_assertion_qualification_report(report, output)
        summary_path = (
            write_assertion_qualification_summary(report, summary_output)
            if summary_output is not None
            else None
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    aggregate = report.aggregate
    typer.echo(f"Golden suite            : {report.golden_suite_id}@{report.golden_suite_version}")
    typer.echo(f"Partition               : {report.golden_partition.value}")
    typer.echo(f"Documents               : {aggregate.documents}")
    typer.echo(f"Clauses                 : {aggregate.clauses}")
    typer.echo(f"Candidate clauses       : {aggregate.candidate_clauses}")
    typer.echo(f"Evaluation contract     : {report.evaluation_contract}")
    typer.echo(f"Candidate mode          : {report.candidate_mode}")
    typer.echo(f"Source binding          : {report.source_binding}")
    typer.echo(
        "Entities (label)        : "
        f"P={_format_ratio(aggregate.entities.precision)}, "
        f"R={_format_ratio(aggregate.entities.recall)}, "
        f"F1={_format_ratio(aggregate.entities.f1)}"
    )
    typer.echo(
        "Entities (typed)        : "
        f"P={_format_ratio(aggregate.typed_entities.precision)}, "
        f"R={_format_ratio(aggregate.typed_entities.recall)}, "
        f"F1={_format_ratio(aggregate.typed_entities.f1)}"
    )
    typer.echo(
        f"Entity class accuracy   : {_format_ratio(aggregate.entity_class_accuracy.accuracy)}"
    )
    typer.echo(f"Work product precision  : {_format_ratio(aggregate.work_product_precision)}")
    typer.echo(f"Work product recall     : {_format_ratio(aggregate.work_product_recall)}")
    typer.echo(
        f"WP class accuracy       : {_format_ratio(aggregate.work_product_class_accuracy.accuracy)}"
    )
    typer.echo(
        "Required WP relation R  : "
        f"{_format_ratio(aggregate.required_work_product_relation_recall)}"
    )
    typer.echo(
        "Assertions              : "
        f"P={_format_ratio(aggregate.assertions.precision)}, "
        f"R={_format_ratio(aggregate.assertions.recall)}, "
        f"F1={_format_ratio(aggregate.assertions.f1)}"
    )
    typer.echo(f"Predicate accuracy      : {_format_ratio(aggregate.predicate_accuracy.accuracy)}")
    typer.echo(
        f"Normative force accuracy: {_format_ratio(aggregate.normative_force_accuracy.accuracy)}"
    )
    typer.echo(f"Evidence integrity      : {_format_ratio(aggregate.evidence_integrity.validity)}")
    typer.echo(
        f"Evidence span exact     : {_format_ratio(aggregate.evidence_span_exact_match.accuracy)}"
    )
    typer.echo(f"Clause exact match      : {_format_ratio(aggregate.clause_exact_match.accuracy)}")
    typer.echo(f"Semantic evidence       : {aggregate.semantic_evidence.status}")
    finding_count = sum(len(case.diagnostic_findings) for case in report.cases)
    review_count = sum(
        finding.status.value == "needs_review"
        for case in report.cases
        for finding in case.diagnostic_findings
    )
    typer.echo(f"Diagnostic findings     : {finding_count} ({review_count} need review)")
    typer.echo(
        "Ontology resources      : "
        + ", ".join(
            f"{binding.reference}:{binding.resource_sha256[:12]}"
            for binding in report.ontology_resources
        )
    )
    typer.echo(f"Report SHA-256           : {qualification_report_sha256(report)}")
    typer.echo(f"Report                  : {report_path}")
    if summary_path is not None:
        typer.echo(f"Summary                 : {summary_path}")


def _format_ratio(metric) -> str:
    if metric.value is None:
        return f"n/a ({metric.status.value}, n={metric.denominator})"
    return f"{metric.value:.4f} (n={metric.denominator})"


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
    from standards_atlas.adapters.llm import (
        LlmConfig,
        OntologyGuidedAssertionProposalVerifier,
        OntologyGuidedKnowledgeProposalExtractor,
        OpenAICompatibleLlmGateway,
    )
    from standards_atlas.application.assertion_qualification.cascade import (
        AssertionQualificationCascadeService,
    )

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
        source_package_repository = FileSystemContextSourcePackageRepository(workspace)
        persisted_package_hashes = {
            source_package_repository.save(package).package_sha256
            for package in result.source_packages
        }
        expected_package_hashes = {
            binding.package_sha256
            for proposal in (result.efficient_proposal, result.escalation_proposal)
            if proposal is not None
            for binding in proposal.context_source_bindings
        }
        if persisted_package_hashes != expected_package_hashes:
            raise ValueError("persisted context source packages differ from proposal bindings")

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
    typer.echo(f"Source packages         : {len(result.source_packages)}")
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


@evaluation_app.command("assertion-experiment-plan")
def plan_assertion_experiment_command(
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    experiment_id: Annotated[str, typer.Option("--experiment-id")],
    variant_id: Annotated[str, typer.Option("--variant-id")],
    prompt_version: Annotated[str, typer.Option("--prompt-version")],
    model_route: Annotated[str, typer.Option("--model-route")] = "openai-compatible",
    model: Annotated[str | None, typer.Option("--model")] = None,
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    repetitions: Annotated[int, typer.Option("--repetitions", min=1)] = 1,
    max_calls: Annotated[int, typer.Option("--max-calls", min=0)] = 1,
    max_retries_per_case: Annotated[int, typer.Option("--max-retries-per-case", min=0)] = 0,
    max_total_tokens: Annotated[int | None, typer.Option("--max-total-tokens", min=1)] = None,
    max_runtime_seconds: Annotated[
        float | None, typer.Option("--max-runtime-seconds", min=0.001)
    ] = None,
    max_output_tokens: Annotated[int | None, typer.Option("--max-output-tokens", min=1)] = None,
    temperature: Annotated[float, typer.Option("--temperature", min=0.0, max=2.0)] = 0.0,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    reasoning_enabled: Annotated[
        bool | None, typer.Option("--reasoning-enabled/--reasoning-disabled")
    ] = None,
    prompt_staging_root: Annotated[
        Path | None,
        typer.Option(
            "--prompt-staging-root",
            file_okay=False,
            help="Optional AP03 Codex staging root; only codex-* prompt versions may use it.",
        ),
    ] = None,
    authorize_execution: Annotated[
        bool, typer.Option("--authorize-execution/--do-not-authorize-execution")
    ] = False,
    authorization_reference: Annotated[
        str | None, typer.Option("--authorization-reference")
    ] = None,
) -> None:
    """Plan and bind a bounded AP03 assertion experiment without model calls."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        ExperimentBudget,
        plan_assertion_experiment,
    )

    try:
        golden = load_assertion_golden_suite(suite)
        documents_repo = FileSystemEngineeringDocumentRepository(workspace)
        documents = {
            key: documents_repo.load(DocumentKey(value=key))
            for key in sorted({case.source_document_key for case in golden.cases})
        }
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        prompt_repository = _ap03_prompt_repository(
            project_root, prompt_version, prompt_staging_root
        )
        runtime_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        manifest = plan_assertion_experiment(
            golden,
            documents,
            experiment_id=experiment_id,
            code_revision=_ap03_code_revision(project_root),
            variant_id=variant_id,
            prompt_version=prompt_version,
            model_route=model_route,
            source_packages=source_repo,
            budget=ExperimentBudget(
                max_calls=max_calls,
                max_retries_per_case=max_retries_per_case,
                max_total_tokens=max_total_tokens,
                max_runtime_seconds=max_runtime_seconds,
            ),
            requested_model=model,
            runtime_config_sha256=runtime_hash,
            temperature=temperature,
            seed=seed,
            max_output_tokens_per_call=max_output_tokens,
            reasoning_enabled=reasoning_enabled,
            repetitions=repetitions,
            execution_authorized=authorize_execution,
            authorization_reference=authorization_reference,
            prompt_repository=prompt_repository,
        )
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        digest = repository.save_manifest(manifest)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Experiment              : {manifest.experiment_id}")
    typer.echo(f"Variant                 : {manifest.variant_id}")
    typer.echo(f"Cases                   : {len(manifest.cases)}")
    typer.echo(f"Repetitions             : {manifest.repetitions}")
    typer.echo(f"Conservative call bound : {manifest.conservative_call_upper_bound}")
    typer.echo(f"Budget max calls        : {manifest.budget.max_calls}")
    typer.echo(f"Execution authorized   : {manifest.execution_authorized}")
    typer.echo(f"Manifest SHA-256        : {digest}")
    typer.echo("Model calls             : 0 (plan only)")


def _run_assertion_experiment_cli(
    *,
    experiment_id: str,
    suite: Path,
    config: Path,
    workspace: Path,
    project_root: Path,
    resume: bool,
    prompt_staging_root: Path | None = None,
) -> None:
    from dataclasses import replace

    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.adapters.llm import (
        LlmConfig,
        OntologyGuidedKnowledgeProposalExtractor,
        OpenAICompatibleLlmGateway,
    )
    from standards_atlas.application.assertion_qualification import AssertionExperimentService

    try:
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        manifest = repository.load_manifest(experiment_id)
        if manifest.model_route != "openai-compatible":
            raise ValueError(
                "this CLI execution path supports only model_route='openai-compatible'; "
                "use a registered application composition for other routes"
            )
        current_code_revision = _ap03_code_revision(project_root)
        if current_code_revision != manifest.code_revision:
            raise ValueError("project code revision differs from the planned experiment")
        runtime_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        if (
            manifest.runtime_config_sha256 is not None
            and runtime_hash != manifest.runtime_config_sha256
        ):
            raise ValueError("runtime configuration bytes differ from the planned experiment")
        golden = load_assertion_golden_suite(suite)
        documents_repo = FileSystemEngineeringDocumentRepository(workspace)
        documents = {
            key: documents_repo.load(DocumentKey(value=key))
            for key in sorted({case.source_document_key for case in golden.cases})
        }
        llm_config = replace(LlmConfig.load(config), cache_directory=None)
        gateway = OpenAICompatibleLlmGateway(llm_config)
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        prompt_repository = _ap03_prompt_repository(
            project_root, manifest.prompt_version, prompt_staging_root
        )

        def extractor_factory(bound_gateway, bound_manifest):
            return OntologyGuidedKnowledgeProposalExtractor(
                bound_gateway,
                model=bound_manifest.requested_model,
                provider=gateway.provider,
                prompt_version=bound_manifest.prompt_version,
                task_schema_version=bound_manifest.task_schema_version,
                temperature=bound_manifest.temperature,
                seed=bound_manifest.seed,
                max_tokens=bound_manifest.max_output_tokens_per_call,
                reasoning_enabled=bound_manifest.reasoning_enabled,
                prompt_repository=prompt_repository,
            )

        state = AssertionExperimentService(
            repository=repository,
            source_packages=source_repo,
            gateway=gateway,
            extractor_factory=extractor_factory,
        ).run(manifest, golden, documents, resume=resume)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Experiment       : {state.experiment_id}")
    typer.echo(f"Attempts         : {len(state.attempts)}")
    typer.echo(f"Completed cells  : {len(state.completed_cells)}")
    typer.echo(f"Blocked          : {state.blocked_reason or 'no'}")


@evaluation_app.command("assertion-experiment-run")
def run_assertion_experiment_command(
    experiment_id: Annotated[str, typer.Option("--experiment-id")],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    prompt_staging_root: Annotated[
        Path | None,
        typer.Option("--prompt-staging-root", file_okay=False),
    ] = None,
) -> None:
    """Execute a previously planned AP03 experiment in the foreground."""
    _run_assertion_experiment_cli(
        experiment_id=experiment_id,
        suite=suite,
        config=config,
        workspace=workspace,
        project_root=project_root,
        resume=False,
        prompt_staging_root=prompt_staging_root,
    )


@evaluation_app.command("assertion-experiment-resume")
def resume_assertion_experiment_command(
    experiment_id: Annotated[str, typer.Option("--experiment-id")],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    prompt_staging_root: Annotated[
        Path | None,
        typer.Option("--prompt-staging-root", file_okay=False),
    ] = None,
) -> None:
    """Resume only unfinished cells of a bound AP03 experiment."""
    _run_assertion_experiment_cli(
        experiment_id=experiment_id,
        suite=suite,
        config=config,
        workspace=workspace,
        project_root=project_root,
        resume=True,
        prompt_staging_root=prompt_staging_root,
    )


@evaluation_app.command("assertion-experiment-report")
def report_assertion_experiment_command(
    experiment_id: Annotated[str, typer.Option("--experiment-id")],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    repetition: Annotated[int, typer.Option("--repetition", min=1)] = 1,
    baseline_report: Annotated[
        Path | None,
        typer.Option("--baseline-report", exists=True, dir_okay=False, readable=True),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
    summary: Annotated[Path | None, typer.Option("--summary", dir_okay=False)] = None,
) -> None:
    """Evaluate native candidates with the existing evaluator plus stage diagnostics."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        evaluate_assertion_experiment,
        materialize_experiment_inputs,
    )

    try:
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        manifest = repository.load_manifest(experiment_id)
        state = repository.load_state(experiment_id)
        if state is None:
            raise ValueError("experiment has no execution state")
        golden = load_assertion_golden_suite(suite)
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        proposals, packages = materialize_experiment_inputs(
            repository,
            source_repo,
            manifest,
            state,
            repetition=repetition,
        )
        baseline = (
            load_assertion_qualification_report(baseline_report)
            if baseline_report is not None
            else None
        )
        report = evaluate_assertion_experiment(
            manifest,
            state,
            golden,
            proposals=proposals,
            source_packages=packages,
            baseline_report=baseline,
            evaluation_repetition=repetition,
        )
        root = project_root / "local" / "evaluation" / "assertions" / "ap03" / experiment_id
        output_path = output or root / "comparison.json"
        summary_path = summary or root / "comparison-summary.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(_render_assertion_experiment_summary(report), encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Comparison JSON : {output_path}")
    typer.echo(f"Summary         : {summary_path}")
    typer.echo(
        "Coverage        : "
        f"{report.coverage.technically_completed_cells}/"
        f"{report.coverage.planned_cells} technically completed cells"
    )
    typer.echo(f"Evaluator       : {report.qualification_report.evaluation_contract}")


def _render_assertion_experiment_summary(report) -> str:
    baseline = (
        "none"
        if report.baseline_qualification_report is None
        else (
            f"{report.baseline_qualification_report.golden_suite_id}@"
            f"{report.baseline_qualification_report.golden_suite_version}"
        )
    )
    lines = [
        f"# AP03 experiment comparison — {report.experiment_id}",
        "",
        f"- Variant: `{report.variant_id}`",
        f"- Evaluated repetition: {report.evaluation_repetition}",
        f"- Manifest SHA-256: `{report.manifest_sha256}`",
        f"- Clause-local evaluator: `{report.qualification_report.evaluation_contract}`",
        f"- Baseline report: {baseline}",
        "",
        "## Fixed coverage",
        "",
        f"- Selected cases: {report.coverage.selected_cases}",
        f"- Planned cells: {report.coverage.planned_cells}",
        f"- Attempted cells: {report.coverage.attempted_cells}",
        f"- Technically completed cells: {report.coverage.technically_completed_cells}",
        f"- Failed cells: {report.coverage.failed_cells}",
        f"- Not executed cells: {report.coverage.not_executed_cells}",
        "",
        "## Stage failures / rejected candidates",
        "",
    ]
    if report.stage_failures:
        lines.extend(f"- `{key}`: {value}" for key, value in sorted(report.stage_failures.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Effort",
            "",
            f"- Gateway attempts: {report.effort.calls}",
            f"- Cached responses observed: {report.effort.cached_calls}",
            "- Prompt tokens: "
            + (
                str(report.effort.prompt_tokens)
                if report.effort.prompt_tokens is not None
                else "unknown"
            ),
            "- Completion tokens: "
            + (
                str(report.effort.completion_tokens)
                if report.effort.completion_tokens is not None
                else "unknown"
            ),
            "- Total tokens: "
            + (
                str(report.effort.total_tokens)
                if report.effort.total_tokens is not None
                else "unknown"
            ),
            "- Duration ms: "
            + (
                str(report.effort.duration_ms)
                if report.effort.duration_ms is not None
                else "unknown"
            ),
            "- Monetary cost: unknown",
            "",
            "## Qualification aggregate",
            "",
            "The values below are the existing `AssertionQualificationEvaluator` aggregate; "
            "this report does not rematch candidates.",
            "",
            "```json",
            json.dumps(
                report.qualification_report.aggregate.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "```",
            "",
            "## Open diagnostics",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.open_diagnostics or ("none",))
    return "\n".join(lines) + "\n"


def _ap03_prompt_repository(
    project_root: Path, prompt_version: str, prompt_staging_root: Path | None
):
    """Load packaged prompts or an explicitly bounded codex-* staging root."""
    from standards_atlas.application.evaluation.repository import PromptRepository
    from standards_atlas.application.evaluation.source_bound_prompt import (
        semantic_prompt_repository,
    )

    if not prompt_version.startswith("codex-"):
        if prompt_staging_root is not None:
            raise ValueError("--prompt-staging-root is accepted only for codex-* prompt versions")
        return semantic_prompt_repository()
    if prompt_staging_root is None:
        raise ValueError("codex-* prompt versions require --prompt-staging-root")
    project = project_root.resolve()
    staging = (
        prompt_staging_root if prompt_staging_root.is_absolute() else project / prompt_staging_root
    ).resolve()
    allowed = (project / "local" / "evaluation" / "assertions" / "ap03").resolve()
    if not staging.is_relative_to(allowed):
        raise ValueError("Codex prompt staging must stay under local/evaluation/assertions/ap03")
    if staging.is_symlink() or any(parent.is_symlink() for parent in staging.parents):
        raise ValueError("Codex prompt staging paths must not contain symlinks")
    semantic_root = Path(__file__).resolve().parents[3] / "resources" / "semantic"
    return PromptRepository(
        staging / "prompts",
        task_root=semantic_root / "tasks",
        policy_root=semantic_root / "policies",
        example_root=semantic_root / "examples",
    )


def _ap03_code_revision(project_root: Path) -> str:
    """Bind execution-relevant project code without relying on an available Git checkout."""
    digest = hashlib.sha256()
    candidates = [project_root / "pyproject.toml"]
    src_root = project_root / "src"
    if src_root.is_dir():
        candidates.extend(
            sorted(
                path
                for path in src_root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            )
        )
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(project_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


@evaluation_app.command("assertion-reference-corpus-plan")
def assertion_reference_corpus_plan_command(
    request: Annotated[Path, typer.Option("--request", exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = Path(
        "local/review/assertions/ap03/partition-and-exposure.json"
    ),
) -> None:
    """Create a text-free grouped Development/Holdout plan; never create Golden labels."""
    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusRequest,
        build_reference_corpus_plan,
    )

    try:
        parsed = ReferenceCorpusRequest.model_validate_json(request.read_bytes())
        plan = build_reference_corpus_plan(parsed)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Reference plan           : {output}")
    typer.echo(f"Development pending      : {len(plan.development)}")
    typer.echo(f"Holdout pending          : {len(plan.holdout)}")
    typer.echo(f"Open blockers            : {len(plan.blockers)}")


@evaluation_app.command("assertion-review-workbench-build")
def assertion_review_workbench_build_command(
    manifest: Annotated[
        Path, typer.Option("--manifest", exists=True, dir_okay=False, readable=True)
    ],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/review/assertions/ap03/workbench/ap03-assertions"
    ),
) -> None:
    """Prepare a source-first assertion review package from a verified S07 corpus plan."""
    from standards_atlas.application.assertion_qualification.assertion_review import (
        AssertionReviewBuildManifest,
        case_from_source_package,
        package_from_cases,
        review_ontology_options,
        write_assertion_review_package,
    )
    from standards_atlas.application.assertion_qualification.reference_corpus import (
        PlannedReferenceCase,
        ReferenceCorpusPlan,
    )
    from standards_atlas.application.assertion_qualification.review_pilot_models import (
        AssertionReviewProposalSnapshot,
    )
    from standards_atlas.application.knowledge_proposal_extraction import (
        assertion_context_source_package,
    )

    try:
        build = AssertionReviewBuildManifest.model_validate_json(manifest.read_bytes())
        base = manifest.parent
        plan_path = (base / build.corpus_plan).resolve()
        if not plan_path.is_file():
            raise ValueError(f"reference corpus plan does not exist: {plan_path}")
        plan = ReferenceCorpusPlan.model_validate_json(plan_path.read_bytes())
        planned_cases: dict[tuple[str, str], PlannedReferenceCase] = {
            (item.document_key, item.clause_id): item for item in (*plan.development, *plan.holdout)
        }
        if build.cases:
            requested = [(item.document_key, item.clause_id, item.proposal) for item in build.cases]
        else:
            requested = [
                (item.document_key, item.clause_id, None)
                for item in (*plan.development, *plan.holdout)
            ]

        documents_repo = FileSystemEngineeringDocumentRepository(workspace)
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        documents = {}
        cases = []
        for document_key, clause_id, proposal_path in requested:
            planned = planned_cases.get((document_key, clause_id))
            if planned is None:
                raise ValueError(
                    "review case is not selected by the bound corpus plan: "
                    f"{document_key}:{clause_id}"
                )
            document = documents.get(document_key)
            if document is None:
                document = documents_repo.load(DocumentKey(value=document_key))
                documents[document_key] = document
            clause = next((item for item in document.clauses if item.id.value == clause_id), None)
            if clause is None:
                raise ValueError(
                    f"reference corpus case clause is unavailable: {document_key}:{clause_id}"
                )
            if clause.reference.clause != planned.reference:
                raise ValueError(
                    "reference corpus case no longer matches the persisted EngineeringDocument: "
                    f"{document_key}:{clause_id} expected {planned.reference!r}, "
                    f"found {clause.reference.clause!r}"
                )

            source = assertion_context_source_package(document, clause)
            binding = source_repo.save(source)
            proposal = None
            if proposal_path is not None:
                if planned.partition != "development":
                    raise ValueError("Holdout review cases cannot bind model proposals by default")
                proposal = AssertionReviewProposalSnapshot.model_validate_json(
                    (base / proposal_path).resolve().read_bytes()
                )
                if (
                    proposal.source_package_binding is not None
                    and proposal.source_package_binding != binding
                ):
                    raise ValueError(
                        "review proposal source-package binding differs from the reconstructed "
                        "S08 source package"
                    )
            case = case_from_source_package(
                source,
                partition=AssertionGoldenPartition(planned.partition),
                source_group=planned.source_group,
                proposal=proposal,
            )
            if case.source_package_sha256 != binding.package_sha256:
                raise ValueError("persisted source-package hash differs from review case binding")
            cases.append(case)

        class_options, predicate_options = review_ontology_options(build.ontology_versions)
        package = package_from_cases(
            id=build.id,
            version=build.version,
            corpus_plan_sha256=plan.plan_sha256,
            ontology_versions=build.ontology_versions,
            class_options=class_options,
            predicate_options=predicate_options,
            cases=tuple(cases),
        )
        write_assertion_review_package(output, package)
    except (KeyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Assertion review package : {output}")
    typer.echo(f"Corpus plan SHA-256      : {package.corpus_plan_sha256}")
    typer.echo(f"Cases                    : {len(package.cases)}")
    typer.echo(f"Source packages          : {len(package.cases)}")
    typer.echo("Golden publication       : disabled in package preparation")


@evaluation_app.command("assertion-review-workbench-publish")
def assertion_review_workbench_publish_command(
    package: Annotated[
        Path, typer.Option("--package", exists=True, file_okay=False, readable=True)
    ],
    partition: Annotated[AssertionGoldenPartition, typer.Option("--partition")],
    suite_id: Annotated[str, typer.Option("--suite-id")],
    suite_version: Annotated[str, typer.Option("--suite-version")],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Publish only human-confirmed task-specific review decisions into a Golden suite."""
    from standards_atlas.application.assertion_qualification.assertion_review import (
        load_assertion_review_package,
        publish_confirmed_assertion_suite,
    )

    try:
        contract, state = load_assertion_review_package(package)
        suite = publish_confirmed_assertion_suite(
            contract,
            state,
            partition=partition,
            suite_id=suite_id,
            suite_version=suite_version,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_assertion_golden_suite(suite, output)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Published suite          : {output}")
    typer.echo(f"Human-confirmed cases    : {len(suite.cases)}")
