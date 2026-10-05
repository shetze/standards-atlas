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
    load_assertion_experiment_baseline_report,
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
    verify_escalation: Annotated[
        bool,
        typer.Option(
            "--verify-escalation/--leave-escalation-unverified",
            help=(
                "Run one bounded second verifier pass on escalation output. "
                "Without it escalated output remains needs_review."
            ),
        ),
    ] = False,
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
            escalation_verifier=(
                OntologyGuidedAssertionProposalVerifier(
                    gateway,
                    model=verifier_model,
                    provider=gateway.provider,
                )
                if verify_escalation
                else None
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
    typer.echo(f"Technically verified    : {result.report.technically_verified_clauses}")
    typer.echo(f"Needs review            : {result.report.needs_review_clauses}")
    typer.echo(f"Failed                  : {result.report.failed_clauses}")
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
    max_total_tokens_per_call: Annotated[
        int | None, typer.Option("--max-total-tokens-per-call", min=1)
    ] = None,
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
                max_total_tokens_per_call=max_total_tokens_per_call,
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
    typer.echo(f"Budget max tokens       : {manifest.budget.max_total_tokens}")
    typer.echo(f"Budget token reservation : {manifest.budget.max_total_tokens_per_call}")
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
            load_assertion_experiment_baseline_report(baseline_report)
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
            f"- Budget-charged tokens: {report.effort.budget_charged_tokens}",
            f"- Calls with unknown token usage: {report.effort.unknown_usage_calls}",
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


@evaluation_app.command("assertion-series-f-prepare")
def prepare_assertion_series_f_command(
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    campaign_id: Annotated[str, typer.Option("--campaign-id")],
    model_route: Annotated[str, typer.Option("--model-route")],
    model: Annotated[str | None, typer.Option("--model")] = None,
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    smoke_cases: Annotated[int, typer.Option("--smoke-cases", min=0)] = 3,
    repetitions: Annotated[int, typer.Option("--repetitions", min=1)] = 1,
    max_calls: Annotated[int, typer.Option("--max-calls", min=1)] = 1,
    max_retries_per_case: Annotated[int, typer.Option("--max-retries-per-case", min=0)] = 0,
    max_total_tokens: Annotated[int | None, typer.Option("--max-total-tokens", min=1)] = None,
    max_total_tokens_per_call: Annotated[
        int | None, typer.Option("--max-total-tokens-per-call", min=1)
    ] = None,
    max_runtime_seconds: Annotated[
        float | None, typer.Option("--max-runtime-seconds", min=0.001)
    ] = None,
    max_output_tokens: Annotated[int | None, typer.Option("--max-output-tokens", min=1)] = None,
    temperature: Annotated[float, typer.Option("--temperature", min=0.0, max=2.0)] = 0.0,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    reasoning_enabled: Annotated[
        bool | None, typer.Option("--reasoning-enabled/--reasoning-disabled")
    ] = None,
    authorize_execution: Annotated[
        bool, typer.Option("--authorize-execution/--do-not-authorize-execution")
    ] = False,
    authorization_reference: Annotated[
        str | None, typer.Option("--authorization-reference")
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Prepare the Development-only B0 smoke/full and P1/P2 Series-F run order."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        SERIES_F_PROMPTS,
        ExperimentBudget,
        build_series_f_plan,
        build_series_f_smoke_manifest,
        plan_assertion_experiment,
    )

    try:
        golden = load_assertion_golden_suite(suite)
        if golden.partition is not AssertionGoldenPartition.DEVELOPMENT:
            raise ValueError("AP03 Series F accepts only a Development golden suite")
        if smoke_cases >= len(golden.cases) and smoke_cases != 0:
            raise ValueError(
                "--smoke-cases must be zero or a strict subset of the Development suite"
            )
        required_calls = len(golden.cases) * repetitions * (1 + max_retries_per_case)
        if max_calls < required_calls:
            raise ValueError(
                f"--max-calls={max_calls} is below the full per-variant bound {required_calls}"
            )
        if authorize_execution and not authorization_reference:
            raise ValueError("authorized Series-F preparation requires --authorization-reference")

        documents_repo = FileSystemEngineeringDocumentRepository(workspace)
        documents = {
            key: documents_repo.load(DocumentKey(value=key))
            for key in sorted({case.source_document_key for case in golden.cases})
        }
        if any(document is None for document in documents.values()):
            missing = sorted(key for key, document in documents.items() if document is None)
            raise ValueError(f"missing EngineeringDocument(s) for Series F: {missing!r}")
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        runtime_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        code_revision = _ap03_code_revision(project_root)
        budget = ExperimentBudget(
            max_calls=max_calls,
            max_retries_per_case=max_retries_per_case,
            max_total_tokens=max_total_tokens,
            max_total_tokens_per_call=max_total_tokens_per_call,
            max_runtime_seconds=max_runtime_seconds,
        )

        manifests = []
        for variant_id, prompt_version in SERIES_F_PROMPTS.items():
            prompt_repository = _ap03_prompt_repository(project_root, prompt_version, None)
            manifest = plan_assertion_experiment(
                golden,
                documents,
                experiment_id=(
                    f"{campaign_id}-{variant_id.lower().replace('_', '-').replace('/', '-')}"
                ),
                code_revision=code_revision,
                variant_id=variant_id,
                prompt_version=prompt_version,
                model_route=model_route,
                source_packages=source_repo,
                budget=budget,
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
            repository.save_manifest(manifest)
            manifests.append(manifest)

        smoke_manifest = None
        if smoke_cases:
            smoke_budget = ExperimentBudget(
                max_calls=max_calls,
                max_retries_per_case=max_retries_per_case,
                max_total_tokens=max_total_tokens,
                max_total_tokens_per_call=max_total_tokens_per_call,
                max_runtime_seconds=max_runtime_seconds,
            )
            smoke_manifest = build_series_f_smoke_manifest(
                manifests[0],
                experiment_id=f"{campaign_id}-b0-smoke",
                smoke_cases=smoke_cases,
                budget=smoke_budget,
            )
            repository.save_manifest(smoke_manifest)

        plan = build_series_f_plan(
            campaign_id=campaign_id,
            full_manifests=tuple(manifests),
            smoke_manifest=smoke_manifest,
        )
        target = output or (
            project_root
            / "local"
            / "evaluation"
            / "assertions"
            / "ap03"
            / campaign_id
            / "series-f-plan.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Series-F campaign : {plan.campaign_id}")
    typer.echo(f"Development cases : {len(golden.cases)}")
    typer.echo(f"Experiments       : {len(plan.experiments)}")
    typer.echo(f"Execution allowed : {authorize_execution}")
    typer.echo(f"Token budget      : {max_total_tokens}")
    typer.echo(f"Per-call reserve  : {max_total_tokens_per_call}")
    typer.echo(f"Plan              : {target}")
    typer.echo("Model calls       : 0 (preparation only)")
    typer.echo("Holdout access    : forbidden")


@evaluation_app.command("assertion-series-g-verifier-run")
def run_assertion_series_g_verifier_command(
    campaign_id: Annotated[str, typer.Option("--campaign-id")],
    experiment_id: Annotated[str, typer.Option("--experiment-id")],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    verifier_model: Annotated[str, typer.Option("--verifier-model")],
    max_calls: Annotated[int, typer.Option("--max-calls", min=1)],
    authorization_reference: Annotated[str, typer.Option("--authorization-reference")],
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            min=0.001,
            help=(
                "Per-request verifier timeout in seconds. Overrides the configured timeout for "
                "this run; retry runs inherit the parent timeout when omitted."
            ),
        ),
    ] = None,
    authorize_execution: Annotated[
        bool, typer.Option("--authorize-execution/--do-not-authorize-execution")
    ] = False,
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
    review_csv: Annotated[Path | None, typer.Option("--review-csv", dir_okay=False)] = None,
    retry_errors_from: Annotated[
        Path | None,
        typer.Option("--retry-errors-from", exists=True, dir_okay=False, readable=True),
    ] = None,
) -> None:
    """Verify Development candidates once, or retry technical errors with an optional timeout."""
    from dataclasses import replace

    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.adapters.llm import (
        LlmConfig,
        OntologyGuidedAssertionProposalVerifier,
        OpenAICompatibleLlmGateway,
    )
    from standards_atlas.application.assertion_qualification import (
        SERIES_G_VERIFIER_PROMPT_VERSION,
        SERIES_G_VERIFIER_VERSION,
        SeriesGVerifierRun,
        VerifierRunCandidate,
        VerifierRunCandidateKind,
        VerifierRunCase,
        manifest_sha256,
        materialize_experiment_inputs,
        render_verifier_review_csv,
        verifier_run_sha256,
    )
    from standards_atlas.application.context.input_binding import context_source_package_binding
    from standards_atlas.application.knowledge_proposal_extraction import (
        assertion_interpretation_context,
    )
    from standards_atlas.application.ports.llm_gateway import LlmGatewayError

    try:
        if not authorize_execution:
            raise ValueError("Series-G verifier execution requires --authorize-execution")
        if not authorization_reference.strip():
            raise ValueError("Series-G verifier execution requires authorization_reference")
        golden = load_assertion_golden_suite(suite)
        if golden.partition is not AssertionGoldenPartition.DEVELOPMENT:
            raise ValueError("Series-G verifier benchmark accepts Development suites only")
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        manifest = repository.load_manifest(experiment_id)
        manifest_digest = manifest_sha256(manifest)
        state = repository.load_state(experiment_id)
        if state is None:
            raise ValueError("Series-G verifier benchmark requires a completed experiment state")
        if manifest.partition != AssertionGoldenPartition.DEVELOPMENT.value:
            raise ValueError("Series-G verifier benchmark accepts Development experiments only")
        proposals, packages = materialize_experiment_inputs(
            repository,
            FileSystemContextSourcePackageRepository(workspace),
            manifest,
            state,
        )
        if not packages:
            raise ValueError("Series-G verifier benchmark has no successful native candidates")
        proposals_by_document = {item.source_document_key: item for item in proposals}
        documents_repo = FileSystemEngineeringDocumentRepository(workspace)
        documents = {
            key: documents_repo.load(DocumentKey(value=key))
            for key in sorted({package.document_key for package in packages})
        }

        parent_run = (
            SeriesGVerifierRun.model_validate_json(retry_errors_from.read_bytes())
            if retry_errors_from is not None
            else None
        )
        base_config = LlmConfig.load(config)
        runtime_config_sha256 = _series_g_identity_sha256(
            {
                "base_url": base_config.base_url,
                "configured_model": base_config.model,
                "verifier_model": verifier_model,
                "timeout_seconds": base_config.timeout_seconds,
                "cache_directory": None,
            }
        )
        effective_timeout_seconds = _series_g_effective_timeout_seconds(
            configured_timeout_seconds=base_config.timeout_seconds,
            requested_timeout_seconds=timeout,
            parent_timeout_seconds=(parent_run.timeout_seconds if parent_run is not None else None),
        )
        benchmark_config = replace(
            base_config,
            cache_directory=None,
            timeout_seconds=effective_timeout_seconds,
        )
        gateway = OpenAICompatibleLlmGateway(benchmark_config)
        verifier = OntologyGuidedAssertionProposalVerifier(
            gateway,
            model=verifier_model,
            provider=gateway.provider,
            prompt_version=SERIES_G_VERIFIER_PROMPT_VERSION,
            verifier_version=SERIES_G_VERIFIER_VERSION,
        )
        verifier_provenance = verifier.provenance()
        prepared_cases = []
        for package in packages:
            document = documents[package.document_key]
            clause = next(
                item for item in document.clauses if item.id.value == package.target_clause_id
            )
            proposal = proposals_by_document[package.document_key]
            entities = tuple(
                item for item in proposal.entity_proposals if clause.id in item.proposal_clause_ids
            )
            assertions = tuple(
                item for item in proposal.assertion_proposals if item.source_clause_id == clause.id
            )
            candidates = tuple(
                VerifierRunCandidate(
                    candidate_id=item.id,
                    kind=VerifierRunCandidateKind.ENTITY,
                    summary=f"{item.class_iri} | {item.normalized_label}",
                )
                for item in entities
            ) + tuple(
                VerifierRunCandidate(
                    candidate_id=item.id,
                    kind=VerifierRunCandidateKind.ASSERTION,
                    summary=(
                        f"{item.predicate} | {item.subject_id} -> "
                        f"{
                            json.dumps(
                                item.object.model_dump(mode='json'),
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        } "
                        f"| force={item.normative_force.value}"
                    ),
                )
                for item in assertions
            )
            prepared_cases.append(
                (
                    package,
                    document,
                    clause,
                    proposal,
                    entities,
                    assertions,
                    candidates,
                    context_source_package_binding(package).package_sha256,
                )
            )

        parent_by_key = {}
        retry_keys = set()
        if parent_run is not None:
            if parent_run.campaign_id == campaign_id:
                raise ValueError("Series-G verifier retry requires a new campaign_id")
            if parent_run.experiment_id != experiment_id:
                raise ValueError("Series-G verifier retry experiment differs from parent run")
            if parent_run.experiment_manifest_sha256 != manifest_digest:
                raise ValueError("Series-G verifier retry manifest differs from parent run")
            if parent_run.variant_id != manifest.variant_id:
                raise ValueError("Series-G verifier retry variant differs from parent run")
            if parent_run.verifier_provenance != verifier_provenance:
                raise ValueError(
                    "Series-G verifier retry verifier identity differs from parent run"
                )
            if parent_run.runtime_config_sha256 != runtime_config_sha256:
                raise ValueError("Series-G verifier retry runtime config differs from parent run")
            parent_by_key = {(item.document_key, item.clause_id): item for item in parent_run.cases}
            current_keys = {
                (package.document_key, package.target_clause_id) for package, *_ in prepared_cases
            }
            if set(parent_by_key) != current_keys:
                raise ValueError("Series-G verifier retry case set differs from current experiment")
            for (
                package,
                _document,
                _clause,
                _proposal,
                _entities,
                _assertions,
                candidates,
                source_package_sha256,
            ) in prepared_cases:
                key = (package.document_key, package.target_clause_id)
                parent_case = parent_by_key[key]
                if parent_case.source_package_sha256 != source_package_sha256:
                    raise ValueError(
                        "Series-G verifier retry source package changed for "
                        f"{package.target_clause_id}"
                    )
                if parent_case.candidates != candidates:
                    raise ValueError(
                        f"Series-G verifier retry candidates changed for {package.target_clause_id}"
                    )
                if parent_case.verification is None:
                    retry_keys.add(key)
            if not retry_keys:
                raise ValueError("Series-G verifier retry parent has no technical verifier errors")

        required_calls = len(retry_keys) if parent_run is not None else len(prepared_cases)
        if required_calls > max_calls:
            raise ValueError(
                "Series-G verifier benchmark requires "
                f"{required_calls} calls, above max_calls={max_calls}"
            )
        health = gateway.health()
        if not health.available:
            detail = f": {health.detail}" if health.detail else ""
            raise ValueError(f"Series-G verifier endpoint preflight failed{detail}")

        cases = []
        retried_case_ids = []
        for (
            package,
            document,
            clause,
            proposal,
            entities,
            assertions,
            candidates,
            source_package_sha256,
        ) in prepared_cases:
            key = (package.document_key, package.target_clause_id)
            if parent_run is not None and key not in retry_keys:
                cases.append(parent_by_key[key])
                continue
            verification = None
            error_type = None
            error_message = None
            try:
                verification = verifier.verify(
                    clause,
                    document_key=document.key.value,
                    ontology_versions=manifest.ontology_versions,
                    evidence_anchors=proposal.evidence_anchors,
                    entity_proposals=entities,
                    assertion_proposals=assertions,
                    source_package=package,
                    interpretation_context=assertion_interpretation_context(document, clause),
                )
            except (LlmGatewayError, ValueError) as exc:
                error_type = type(exc).__name__
                error_message = str(exc)
            if parent_run is not None:
                case_id = parent_by_key[key].case_id
                retried_case_ids.append(case_id)
            else:
                case_digest = hashlib.sha256(
                    (
                        f"{campaign_id}\0{experiment_id}\0{package.document_key}\0"
                        f"{package.target_clause_id}"
                    ).encode()
                ).hexdigest()[:24]
                case_id = f"verifier-{case_digest}"
            cases.append(
                VerifierRunCase(
                    case_id=case_id,
                    document_key=package.document_key,
                    clause_id=package.target_clause_id,
                    source_package_sha256=source_package_sha256,
                    candidates=candidates,
                    verification=verification,
                    verification_error_type=error_type,
                    verification_error_message=error_message,
                )
            )
        run = SeriesGVerifierRun(
            campaign_id=campaign_id,
            experiment_id=experiment_id,
            experiment_manifest_sha256=manifest_digest,
            variant_id=manifest.variant_id,
            verifier_provenance=verifier_provenance,
            runtime_config_sha256=runtime_config_sha256,
            timeout_seconds=benchmark_config.timeout_seconds,
            timeout_override_seconds=timeout,
            cache_bypassed=True,
            authorized_max_calls=max_calls,
            actual_calls=required_calls,
            authorization_reference=authorization_reference,
            retry_of_verifier_run_sha256=(
                verifier_run_sha256(parent_run) if parent_run is not None else None
            ),
            retried_case_ids=tuple(retried_case_ids),
            inherited_case_count=len(cases) - required_calls if parent_run is not None else 0,
            cases=tuple(cases),
        )
        root = project_root / "local" / "evaluation" / "assertions" / "ap03" / campaign_id
        target = output or (root / "verifier-run.json")
        review_target = review_csv or (root / "verifier-review.csv")
        target.parent.mkdir(parents=True, exist_ok=True)
        review_target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
        review_target.write_text(render_verifier_review_csv(run), encoding="utf-8")
    except (OSError, StopIteration, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    errors = sum(item.verification is None for item in run.cases)
    typer.echo(f"Verifier campaign        : {campaign_id}")
    typer.echo(f"Candidate experiment     : {experiment_id}")
    typer.echo(f"Verifier calls           : {run.actual_calls}/{run.authorized_max_calls}")
    typer.echo(f"Represented cases        : {len(run.cases)}")
    if run.retry_of_verifier_run_sha256 is not None:
        typer.echo(f"Inherited valid cases    : {run.inherited_case_count}")
        typer.echo(f"Retried technical errors : {len(run.retried_case_ids)}")
        typer.echo(f"Retry parent SHA-256     : {run.retry_of_verifier_run_sha256}")
    typer.echo(f"Verifier prompt          : {run.verifier_provenance.prompt_version}")
    typer.echo(f"Verifier timeout         : {run.timeout_seconds:g}s")
    typer.echo(f"Verifier errors          : {errors}")
    typer.echo(f"Verifier run SHA-256     : {verifier_run_sha256(run)}")
    typer.echo(f"Verifier run             : {target}")
    typer.echo(f"Blind review CSV         : {review_target}")
    typer.echo("Golden mutation          : forbidden")


@evaluation_app.command("assertion-series-g-verifier-observations-build")
def build_assertion_series_g_verifier_observations_command(
    verifier_run: Annotated[
        Path, typer.Option("--verifier-run", exists=True, dir_okay=False, readable=True)
    ],
    reviewed_csv: Annotated[
        Path, typer.Option("--reviewed-csv", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Bind completed human CSV decisions to hidden verifier outcomes."""
    from pydantic import TypeAdapter

    from standards_atlas.application.assertion_qualification import (
        SeriesGVerifierRun,
        VerifierCaseObservation,
        build_verifier_observations_from_review_csv,
    )

    try:
        run = SeriesGVerifierRun.model_validate_json(verifier_run.read_bytes())
        observations = build_verifier_observations_from_review_csv(
            run,
            reviewed_csv.read_text(encoding="utf-8"),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        adapter = TypeAdapter(tuple[VerifierCaseObservation, ...])
        output.write_text(
            json.dumps(adapter.dump_python(observations, mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Annotated cases          : {len(observations)}")
    typer.echo(f"Observations             : {output}")
    typer.echo("Human decisions          : required; never synthesized")


@evaluation_app.command("assertion-series-g-repetitions-build")
def build_assertion_series_g_repetitions_command(
    variant_id: Annotated[str, typer.Option("--variant-id")],
    planned_repetitions: Annotated[int, typer.Option("--planned-repetitions", min=1)],
    report: Annotated[
        list[Path], typer.Option("--report", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Materialize repetition evidence from already-generated experiment reports."""
    from standards_atlas.application.assertion_qualification import (
        AssertionExperimentReport,
        build_repetition_evidence,
    )

    try:
        reports = tuple(
            AssertionExperimentReport.model_validate_json(path.read_bytes()) for path in report
        )
        hashes = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in report)
        evidence = build_repetition_evidence(
            variant_id=variant_id,
            planned_repetitions=planned_repetitions,
            reports=reports,
            report_hashes=hashes,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(evidence.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Completed repetitions    : {evidence.completed_repetitions}")
    typer.echo(f"Fresh repetitions        : {evidence.fresh_inference_repetitions}")
    typer.echo(f"Cached repetitions       : {evidence.cached_repetitions}")
    typer.echo(f"Unstable cases           : {len(evidence.unstable_case_ids)}")
    typer.echo(f"Repetition evidence      : {output}")


@evaluation_app.command("assertion-series-g-gate-profile-build")
def build_assertion_series_g_gate_profile_command(
    max_false_acceptance_rate: Annotated[
        float, typer.Option("--max-false-acceptance-rate", min=0.0, max=1.0)
    ],
    max_false_rejection_rate: Annotated[
        float, typer.Option("--max-false-rejection-rate", min=0.0, max=1.0)
    ],
    min_missing_item_recall: Annotated[
        float, typer.Option("--min-missing-item-recall", min=0.0, max=1.0)
    ],
    min_verifier_coverage: Annotated[
        float, typer.Option("--min-verifier-coverage", min=0.0, max=1.0)
    ],
    min_real_annotated_cases: Annotated[int, typer.Option("--min-real-annotated-cases", min=1)],
    min_candidate_support: Annotated[int, typer.Option("--min-candidate-support", min=1)],
    min_supported_candidate_support: Annotated[
        int, typer.Option("--min-supported-candidate-support", min=1)
    ],
    min_rejected_candidate_support: Annotated[
        int, typer.Option("--min-rejected-candidate-support", min=1)
    ],
    min_missing_item_positive_support: Annotated[
        int, typer.Option("--min-missing-item-positive-support", min=1)
    ],
    required_fresh_repetitions: Annotated[int, typer.Option("--required-fresh-repetitions", min=1)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    max_cached_repetitions: Annotated[int, typer.Option("--max-cached-repetitions", min=0)] = 0,
    human_confirmation_reference: Annotated[
        str | None, typer.Option("--human-confirmation-reference")
    ] = None,
) -> None:
    """Create explicit G4/G5 gates; threshold values are never inferred from measured results."""
    from standards_atlas.application.assertion_qualification import SeriesGGateProfile

    try:
        profile = SeriesGGateProfile(
            max_false_acceptance_rate=max_false_acceptance_rate,
            max_false_rejection_rate=max_false_rejection_rate,
            min_missing_item_recall=min_missing_item_recall,
            min_verifier_coverage=min_verifier_coverage,
            min_real_annotated_cases=min_real_annotated_cases,
            min_candidate_support=min_candidate_support,
            min_supported_candidate_support=min_supported_candidate_support,
            min_rejected_candidate_support=min_rejected_candidate_support,
            min_missing_item_positive_support=min_missing_item_positive_support,
            required_fresh_repetitions=required_fresh_repetitions,
            max_cached_repetitions=max_cached_repetitions,
            human_confirmed=human_confirmation_reference is not None,
            human_confirmation_reference=human_confirmation_reference,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("Gates explicitly defined : True")
    typer.echo(f"Human H3 confirmed       : {profile.human_confirmed}")
    typer.echo(f"Gate profile             : {output}")


def _series_g_effective_timeout_seconds(
    *,
    configured_timeout_seconds: float,
    requested_timeout_seconds: float | None,
    parent_timeout_seconds: float | None,
) -> float:
    if requested_timeout_seconds is not None:
        return requested_timeout_seconds
    if parent_timeout_seconds is not None:
        return parent_timeout_seconds
    return configured_timeout_seconds


def _series_g_identity_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@evaluation_app.command("assertion-series-g-freeze-build")
def build_assertion_series_g_freeze_command(
    freeze_id: Annotated[str, typer.Option("--freeze-id")],
    finalist_experiment: Annotated[str, typer.Option("--finalist-experiment")],
    partition_plan: Annotated[
        Path, typer.Option("--partition-plan", exists=True, dir_okay=False, readable=True)
    ],
    holdout_campaign: Annotated[
        Path, typer.Option("--holdout-campaign", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    verify_escalation: Annotated[
        bool, typer.Option("--verify-escalation/--leave-escalation-unverified")
    ] = False,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
) -> None:
    """Materialize the Series-G freeze from bound manifests/plans without manual hash upkeep."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        ASSERTION_EVALUATION_CONTRACT,
        SeriesGFreeze,
        SeriesHHoldoutCampaign,
        series_h_campaign_sha256,
    )
    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusPlan,
    )

    try:
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        manifest = repository.load_manifest(finalist_experiment)
        if manifest.partition != AssertionGoldenPartition.DEVELOPMENT.value:
            raise ValueError("Series-G Finalist freeze requires a Development experiment")
        partition = ReferenceCorpusPlan.model_validate_json(partition_plan.read_bytes())
        campaign = SeriesHHoldoutCampaign.model_validate_json(holdout_campaign.read_bytes())
        code_revision = _ap03_code_revision(project_root)
        case_bindings = [
            {
                "document_key": item.document_key,
                "clause_id": item.clause_id,
                "source_package_sha256": item.source_package_sha256,
                "rendered_request_sha256": item.rendered_request_sha256,
            }
            for item in manifest.cases
        ]
        freeze = SeriesGFreeze(
            freeze_id=freeze_id,
            code_revision=code_revision,
            prompt_bundle_sha256=_series_g_identity_sha256(
                {
                    "prompt_version": manifest.prompt_version,
                    "variant_id": manifest.variant_id,
                    "rendered_requests": [
                        item["rendered_request_sha256"] for item in case_bindings
                    ],
                }
            ),
            task_schema_sha256=_series_g_identity_sha256(
                {
                    "task_schema_version": manifest.task_schema_version,
                    "code_revision": code_revision,
                }
            ),
            ontology_fingerprint=_series_g_identity_sha256(
                {"ontology_versions": manifest.ontology_versions}
            ),
            source_context_policy_sha256=_series_g_identity_sha256(
                {"data_route": manifest.data_route, "cases": case_bindings}
            ),
            model_backend_sha256=_series_g_identity_sha256(
                {
                    "model_route": manifest.model_route,
                    "runtime_config_sha256": manifest.runtime_config_sha256,
                    "requested_model": manifest.requested_model,
                    "temperature": manifest.temperature,
                    "seed": manifest.seed,
                    "max_output_tokens_per_call": manifest.max_output_tokens_per_call,
                    "reasoning_enabled": manifest.reasoning_enabled,
                }
            ),
            cascade_policy_sha256=_series_g_identity_sha256(
                {"verify_escalation": verify_escalation, "code_revision": code_revision}
            ),
            retry_budget_policy_sha256=_series_g_identity_sha256(
                {
                    "budget": manifest.budget.model_dump(mode="json"),
                    "repetitions": manifest.repetitions,
                    "bypass_cache_for_repetitions": manifest.bypass_cache_for_repetitions,
                }
            ),
            development_golden_sha256=manifest.golden_suite_sha256,
            partition_exposure_sha256=partition.plan_sha256,
            evaluator_sha256=_series_g_identity_sha256(
                {
                    "evaluation_contract": ASSERTION_EVALUATION_CONTRACT,
                    "code_revision": code_revision,
                }
            ),
            holdout_campaign_sha256=series_h_campaign_sha256(campaign),
            canonical_adoption_enabled=False,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(freeze.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Freeze id                : {freeze.freeze_id}")
    typer.echo(f"Code revision            : {freeze.code_revision}")
    typer.echo(f"Holdout campaign SHA-256 : {freeze.holdout_campaign_sha256}")
    typer.echo("Canonical adoption       : disabled")
    typer.echo(f"Freeze                   : {output}")


@evaluation_app.command("assertion-series-g-verifier-evaluate")
def evaluate_assertion_series_g_verifier_command(
    observations: Annotated[
        Path, typer.Option("--observations", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Measure verifier errors against explicitly annotated Development truth."""
    from pydantic import TypeAdapter

    from standards_atlas.application.assertion_qualification import (
        VerifierCaseObservation,
        evaluate_verifier_quality,
    )

    try:
        adapter = TypeAdapter(tuple[VerifierCaseObservation, ...])
        cases = adapter.validate_json(observations.read_text(encoding="utf-8"))
        metrics = evaluate_verifier_quality(cases)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(metrics.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Annotated cases          : {metrics.annotated_cases}")
    typer.echo(f"Real annotated cases     : {metrics.real_annotated_cases}")
    typer.echo(f"Synthetic cases          : {metrics.synthetic_cases}")
    typer.echo(f"Verifier errors          : {metrics.verifier_error_cases}")
    typer.echo(f"Candidate support        : {metrics.candidate_support}")
    typer.echo(f"Candidate reviewed       : {metrics.candidate_reviewed}")
    typer.echo(f"Supported support        : {metrics.supported_candidate_support}")
    typer.echo(f"Rejected support         : {metrics.rejected_candidate_support}")
    typer.echo(f"Missing positive support : {metrics.missing_item_positive_support}")
    typer.echo(f"Verifier coverage        : {metrics.coverage}")
    typer.echo(f"Metrics                  : {output}")


@evaluation_app.command("assertion-series-g-readiness")
def evaluate_assertion_series_g_readiness_command(
    metrics: Annotated[Path, typer.Option("--metrics", exists=True, dir_okay=False, readable=True)],
    repetitions: Annotated[
        Path, typer.Option("--repetitions", exists=True, dir_okay=False, readable=True)
    ],
    gate_profile: Annotated[
        Path, typer.Option("--gate-profile", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    freeze: Annotated[
        Path | None, typer.Option("--freeze", exists=True, dir_okay=False, readable=True)
    ] = None,
) -> None:
    """Assess pre-Holdout readiness without claiming qualification or canonical adoption."""
    from standards_atlas.application.assertion_qualification import (
        RepetitionEvidence,
        SeriesGFreeze,
        SeriesGGateProfile,
        VerifierQualityMetrics,
        assess_series_g_readiness,
    )

    try:
        measured = VerifierQualityMetrics.model_validate_json(metrics.read_text(encoding="utf-8"))
        repeat = RepetitionEvidence.model_validate_json(repetitions.read_text(encoding="utf-8"))
        gates = SeriesGGateProfile.model_validate_json(gate_profile.read_text(encoding="utf-8"))
        frozen = (
            SeriesGFreeze.model_validate_json(freeze.read_text(encoding="utf-8"))
            if freeze is not None
            else None
        )
        readiness = assess_series_g_readiness(
            metrics=measured,
            repetitions=repeat,
            gate_profile=gates,
            freeze=frozen,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(readiness.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Ready for Holdout        : {readiness.ready_for_holdout}")
    typer.echo("Qualification claim      : forbidden in Series G")
    typer.echo(f"Blockers                 : {', '.join(readiness.blockers) or 'none'}")
    typer.echo(f"Readiness                : {output}")


@evaluation_app.command("assertion-series-h-campaign-prepare")
def prepare_assertion_series_h_campaign_command(
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    partition_plan: Annotated[
        Path, typer.Option("--partition-plan", exists=True, dir_okay=False, readable=True)
    ],
    gate_profile: Annotated[
        Path, typer.Option("--gate-profile", exists=True, dir_okay=False, readable=True)
    ],
    campaign_id: Annotated[str, typer.Option("--campaign-id")],
    finalist_experiment: Annotated[str, typer.Option("--finalist-experiment")],
    baseline_experiment: Annotated[list[str] | None, typer.Option("--baseline-experiment")] = None,
    campaign_version: Annotated[str, typer.Option("--campaign-version")] = "1.0.0",
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Freeze the exact Holdout run order before Series-G readiness/freeze confirmation."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        SeriesHExperimentRole,
        SeriesHGateProfile,
        build_series_h_campaign,
        series_h_campaign_sha256,
    )
    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusPlan,
    )

    try:
        golden = load_assertion_golden_suite(suite)
        partition = ReferenceCorpusPlan.model_validate_json(partition_plan.read_bytes())
        gates = SeriesHGateProfile.model_validate_json(gate_profile.read_bytes())
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        experiments = [
            (SeriesHExperimentRole.BASELINE, repository.load_manifest(experiment_id))
            for experiment_id in (baseline_experiment or [])
        ]
        experiments.append(
            (SeriesHExperimentRole.FINALIST, repository.load_manifest(finalist_experiment))
        )
        campaign = build_series_h_campaign(
            campaign_id=campaign_id,
            campaign_version=campaign_version,
            suite=golden,
            reference_plan=partition,
            gate_profile=gates,
            experiments=tuple(experiments),
        )
        target = output or (
            project_root
            / "local"
            / "evaluation"
            / "assertions"
            / "ap03"
            / campaign_id
            / "series-h-campaign.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                campaign.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Series-H campaign        : {target}")
    typer.echo(f"Campaign SHA-256         : {series_h_campaign_sha256(campaign)}")
    typer.echo(f"Frozen experiments       : {len(campaign.experiments)}")
    typer.echo("Model calls              : 0 (campaign preparation only)")
    typer.echo("Optimizer access         : forbidden")


def _series_h_preflight_from_paths(
    *,
    readiness_path: Path,
    campaign_path: Path,
    gate_profile_path: Path,
    suite_path: Path,
    partition_plan_path: Path,
    workspace: Path,
    project_root: Path,
):
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        SeriesGReadiness,
        SeriesHGateProfile,
        SeriesHHoldoutCampaign,
        validate_series_h_campaign,
    )
    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusPlan,
    )

    readiness = SeriesGReadiness.model_validate_json(readiness_path.read_bytes())
    campaign = SeriesHHoldoutCampaign.model_validate_json(campaign_path.read_bytes())
    gates = SeriesHGateProfile.model_validate_json(gate_profile_path.read_bytes())
    suite = load_assertion_golden_suite(suite_path)
    partition = ReferenceCorpusPlan.model_validate_json(partition_plan_path.read_bytes())
    repository = FileSystemAssertionExperimentRepository(project_root, workspace)
    manifests = tuple(repository.load_manifest(item.experiment_id) for item in campaign.experiments)
    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=gates,
        suite=suite,
        reference_plan=partition,
        manifests=manifests,
    )
    return preflight, campaign, gates, suite, partition, manifests


@evaluation_app.command("assertion-series-h-preflight")
def assertion_series_h_preflight_command(
    readiness: Annotated[
        Path, typer.Option("--readiness", exists=True, dir_okay=False, readable=True)
    ],
    campaign: Annotated[
        Path, typer.Option("--campaign", exists=True, dir_okay=False, readable=True)
    ],
    gate_profile: Annotated[
        Path, typer.Option("--gate-profile", exists=True, dir_okay=False, readable=True)
    ],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    partition_plan: Annotated[
        Path, typer.Option("--partition-plan", exists=True, dir_okay=False, readable=True)
    ],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Check freeze, exposure and exact Holdout bindings without inference."""
    try:
        preflight, frozen, _, _, _, _ = _series_h_preflight_from_paths(
            readiness_path=readiness,
            campaign_path=campaign,
            gate_profile_path=gate_profile,
            suite_path=suite,
            partition_plan_path=partition_plan,
            workspace=workspace,
            project_root=project_root,
        )
        target = output or (
            project_root
            / "local"
            / "evaluation"
            / "assertions"
            / "ap03"
            / frozen.campaign_id
            / "series-h-preflight.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(preflight.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Ready to execute         : {preflight.ready_to_execute}")
    typer.echo(f"Independent groups       : {preflight.independent_source_groups}")
    typer.echo(f"Blockers                 : {', '.join(preflight.blockers) or 'none'}")
    typer.echo(f"Preflight                : {target}")
    typer.echo("Model calls              : 0")


@evaluation_app.command("assertion-series-h-run")
def run_assertion_series_h_campaign_command(
    readiness: Annotated[
        Path, typer.Option("--readiness", exists=True, dir_okay=False, readable=True)
    ],
    campaign: Annotated[
        Path, typer.Option("--campaign", exists=True, dir_okay=False, readable=True)
    ],
    gate_profile: Annotated[
        Path, typer.Option("--gate-profile", exists=True, dir_okay=False, readable=True)
    ],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    partition_plan: Annotated[
        Path, typer.Option("--partition-plan", exists=True, dir_okay=False, readable=True)
    ],
    config: Annotated[
        Path, typer.Option("--config", exists=True, dir_okay=False, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    prompt_staging_root: Annotated[
        Path | None, typer.Option("--prompt-staging-root", file_okay=False)
    ] = None,
) -> None:
    """Execute only the already frozen Holdout experiment sequence, with no adaptive selection."""
    try:
        preflight, frozen, _, _, _, _ = _series_h_preflight_from_paths(
            readiness_path=readiness,
            campaign_path=campaign,
            gate_profile_path=gate_profile,
            suite_path=suite,
            partition_plan_path=partition_plan,
            workspace=workspace,
            project_root=project_root,
        )
        if not preflight.ready_to_execute:
            raise ValueError("Series-H Holdout execution blocked: " + ", ".join(preflight.blockers))
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Frozen Holdout campaign  : {frozen.campaign_id}")
    typer.echo("Adaptive variant choice  : forbidden")
    typer.echo("Optimizer client          : not invoked")
    for experiment_id in frozen.execution_order:
        _run_assertion_experiment_cli(
            experiment_id=experiment_id,
            suite=suite,
            config=config,
            workspace=workspace,
            project_root=project_root,
            resume=False,
            prompt_staging_root=prompt_staging_root,
        )


@evaluation_app.command("assertion-series-h-finalize")
def finalize_assertion_series_h_command(
    readiness: Annotated[
        Path, typer.Option("--readiness", exists=True, dir_okay=False, readable=True)
    ],
    campaign: Annotated[
        Path, typer.Option("--campaign", exists=True, dir_okay=False, readable=True)
    ],
    gate_profile: Annotated[
        Path, typer.Option("--gate-profile", exists=True, dir_okay=False, readable=True)
    ],
    suite: Annotated[Path, typer.Option("--suite", exists=True, dir_okay=False, readable=True)],
    partition_plan: Annotated[
        Path, typer.Option("--partition-plan", exists=True, dir_okay=False, readable=True)
    ],
    release_decision: Annotated[
        str | None,
        typer.Option(
            "--release-decision",
            help="Human decision: approve_bounded_pilot or do_not_approve.",
        ),
    ] = None,
    release_reference: Annotated[str | None, typer.Option("--release-reference")] = None,
    qualification_scope: Annotated[str | None, typer.Option("--qualification-scope")] = None,
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = (
        cli_defaults.DEFAULT_WORKSPACE
    ),
    project_root: Annotated[Path, typer.Option("--project-root", file_okay=False)] = Path("."),
    output_root: Annotated[Path | None, typer.Option("--output-root", file_okay=False)] = None,
) -> None:
    """Evaluate every frozen Holdout repetition and emit the AP03 decision plus AP04 handover."""
    from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
    from standards_atlas.application.assertion_qualification import (
        SeriesHReleaseAttestation,
        SeriesHReleaseDecision,
        assess_series_h_holdout,
        evaluate_assertion_experiment,
        finalize_series_h,
        materialize_experiment_inputs,
        render_ap04_handover,
        render_series_h_quality_report,
    )

    try:
        preflight, frozen, gates, golden, partition, manifests = _series_h_preflight_from_paths(
            readiness_path=readiness,
            campaign_path=campaign,
            gate_profile_path=gate_profile,
            suite_path=suite,
            partition_plan_path=partition_plan,
            workspace=workspace,
            project_root=project_root,
        )
        repository = FileSystemAssertionExperimentRepository(project_root, workspace)
        source_repo = FileSystemContextSourcePackageRepository(workspace)
        reports = []
        root = output_root or (
            project_root / "local" / "evaluation" / "assertions" / "ap03" / frozen.campaign_id
        )
        report_root = root / "holdout-reports"
        if preflight.ready_to_execute:
            for manifest in manifests:
                state = repository.load_state(manifest.experiment_id)
                if state is None or not state.attempts:
                    continue
                for repetition in range(1, manifest.repetitions + 1):
                    proposals, packages = materialize_experiment_inputs(
                        repository,
                        source_repo,
                        manifest,
                        state,
                        repetition=repetition,
                    )
                    report = evaluate_assertion_experiment(
                        manifest,
                        state,
                        golden,
                        proposals=proposals,
                        source_packages=packages,
                        evaluation_repetition=repetition,
                    )
                    reports.append(report)
                    report_root.mkdir(parents=True, exist_ok=True)
                    path = report_root / f"{manifest.experiment_id}-r{repetition}.json"
                    path.write_text(
                        json.dumps(
                            report.model_dump(mode="json"),
                            indent=2,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
        assessment = assess_series_h_holdout(
            preflight=preflight,
            campaign=frozen,
            gate_profile=gates,
            reports=tuple(reports),
        )
        attestation = None
        if release_decision is not None or release_reference is not None:
            if release_decision is None or release_reference is None:
                raise ValueError(
                    "--release-decision and --release-reference must be supplied together"
                )
            attestation = SeriesHReleaseAttestation(
                decision=SeriesHReleaseDecision(release_decision),
                reference=release_reference,
            )
        completion = finalize_series_h(
            assessment=assessment,
            release_attestation=attestation,
            qualification_scope=qualification_scope,
        )
        root.mkdir(parents=True, exist_ok=True)
        completion_path = root / "series-h-completion.json"
        quality_path = root / "series-h-quality-report.md"
        handover_path = root / "ap04-handover.md"
        completion_path.write_text(completion.model_dump_json(indent=2) + "\n", encoding="utf-8")
        quality_path.write_text(
            render_series_h_quality_report(
                completion,
                campaign=frozen,
                experiment_reports=tuple(reports),
                reference_plan=partition,
            ),
            encoding="utf-8",
        )
        handover_path.write_text(
            render_ap04_handover(completion=completion, reports=tuple(reports)),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"AP03 completion state     : {completion.state.value}")
    typer.echo(f"Experimentally evaluated : {completion.experimentally_evaluated}")
    typer.echo(f"Bounded pilot qualified  : {completion.qualified_for_bounded_pilot}")
    typer.echo(f"Completion report        : {completion_path}")
    typer.echo(f"Quality report           : {quality_path}")
    typer.echo(f"AP04 handover            : {handover_path}")
    typer.echo("Canonical adoption       : disabled")
