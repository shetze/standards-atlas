from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionCandidateVerification,
    AssertionCascadeClauseReport,
    AssertionCascadeProposalSource,
    AssertionCascadeReason,
    AssertionCascadeRoute,
    AssertionClauseVerification,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationCascadeReport,
    AssertionQualificationEvaluator,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
    CountMetrics,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
    MetricStatus,
    RatioMetric,
)
from standards_atlas.application.assertion_qualification.evaluation import proposal_sha256
from standards_atlas.application.assertion_qualification.policy import (
    AssertionAutoAdoptionPolicyEvaluator,
)
from standards_atlas.application.assertion_qualification.policy_models import (
    AssertionAutoAdoptionDisposition,
    AssertionAutoAdoptionPolicy,
    AssertionAutoAdoptionReason,
    AssertionQualityThresholds,
)
from standards_atlas.application.knowledge_proposal_extraction.source_bound_contract import (
    ASSERTION_VERIFIER_REQUEST_CONTRACT,
    KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
    KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
)
from standards_atlas.domain.model import (
    CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
    ClauseId,
    ContextInputFingerprints,
    ContextSourcePackageBinding,
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    NormativeAssertionProposal,
    NormativeForce,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
HASH = "1" * 64


def _source_binding(
    *,
    document: str,
    clause_id: str,
    seed: str,
    completeness: str = "complete",
    gaps: tuple[str, ...] = (),
) -> ContextSourcePackageBinding:
    def digest(label: str) -> str:
        value = hashlib.sha256(f"{document}:{clause_id}:{seed}:{label}".encode()).hexdigest()
        return f"sha256:{value}"

    return ContextSourcePackageBinding(
        package_sha256=digest("package"),
        document_key=document,
        document_revision=digest("document"),
        target_clause_id=clause_id,
        target_reference=f"{document}:{clause_id}",
        selection_contract_id="structured-context-selection-v1",
        selection_profile_id="assertion-context-selection-v1",
        selection_completeness=completeness,
        selection_gap_codes=gaps,
        fingerprints=ContextInputFingerprints(
            source_state_sha256=digest("source"),
            candidate_space_sha256=digest("candidates"),
            selection_decision_sha256=digest("selection"),
            actual_input_sha256=digest("input"),
        ),
    )


def _thresholds(**changes) -> AssertionQualityThresholds:
    values = {
        "min_entity_precision": 1.0,
        "min_entity_recall": 1.0,
        "min_assertion_precision": 1.0,
        "min_assertion_recall": 1.0,
        "min_predicate_accuracy": 1.0,
        "min_normative_force_accuracy": 1.0,
        "min_evidence_span_exact_match_accuracy": 1.0,
        "min_exact_assertion_accuracy": 1.0,
        "max_entity_false_positives": 0,
        "max_entity_false_negatives": 0,
        "max_assertion_false_positives": 0,
        "max_assertion_false_negatives": 0,
    }
    values.update(changes)
    return AssertionQualityThresholds(**values)


def _policy(**changes) -> AssertionAutoAdoptionPolicy:
    values = {
        "id": "assertion-auto-v1",
        "version": "1.0.0",
        "ontology_versions": ONTOLOGIES,
        "development": _thresholds(),
        "holdout": _thresholds(),
    }
    values.update(changes)
    return AssertionAutoAdoptionPolicy(**values)


def _suite(
    *,
    partition: AssertionGoldenPartition,
    document: str,
    clause_id: str,
) -> AssertionGoldenSuite:
    entity_id = f"gold:{document}:entity"
    return AssertionGoldenSuite(
        id=f"{partition.value}-suite",
        version="1.0.0",
        partition=partition,
        audit=AssertionAuditBinding(
            review_id=f"{partition.value}-review",
            review_version="1",
            audit_sha256="b" * 64,
        ),
        ontology_versions=ONTOLOGIES,
        cases=(
            AssertionGoldenCase(
                source_document_key=document,
                clause_id=ClauseId(value=clause_id),
                reference=f"{document}:{clause_id}",
                canonical_reference=f"{document} {clause_id}",
                text_sha256=HASH,
                source_sha256=HASH,
                entities=(
                    GoldenKnowledgeEntity(
                        id=entity_id,
                        class_iri=f"{STAT}Requirement",
                        normalized_label=f"requirement {document.lower()}",
                    ),
                ),
                assertions=(
                    GoldenNormativeAssertion(
                        id=f"gold:{document}:assertion",
                        source_clause_id=ClauseId(value=clause_id),
                        subject_id=entity_id,
                        predicate=f"{STAT}requires",
                        object=EntityAssertionObject(entity_id=entity_id),
                        normative_force=NormativeForce.REQUIREMENT,
                        evidence=(
                            GoldenEvidenceSpan(
                                source_document_key=document,
                                source_kind="body",
                                clause_id=ClauseId(value=clause_id),
                                start_offset=0,
                                end_offset=10,
                                content_hash=HASH,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _proposal(
    *,
    document: str,
    clause_id: str,
    run_id: str,
    entity_id: str | None = None,
    assertion_id: str | None = None,
    label: str | None = None,
) -> DocumentKnowledgeProposal:
    entity_id = entity_id or f"proposal:{document}:entity"
    assertion_id = assertion_id or f"proposal:{document}:assertion"
    anchor = EvidenceAnchor(
        id=f"anchor:{run_id}:{clause_id}",
        source_clause_id=ClauseId(value=clause_id),
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=10,
        content_hash=HASH,
    )
    entity = KnowledgeEntityProposal(
        id=entity_id,
        proposal_clause_ids=(ClauseId(value=clause_id),),
        class_iri=f"{STAT}Requirement",
        normalized_label=label or f"requirement {document.lower()}",
        source_anchor_ids=(anchor.id,),
        confidence=0.95,
    )
    assertion = NormativeAssertionProposal(
        id=assertion_id,
        source_clause_id=ClauseId(value=clause_id),
        subject_id=entity.id,
        predicate=f"{STAT}requires",
        object=EntityAssertionObject(entity_id=entity.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        confidence=0.95,
    )
    return DocumentKnowledgeProposal(
        proposal_run_id=run_id,
        source_document_key=document,
        ontology_versions=ONTOLOGIES,
        context_source_bindings=(
            _source_binding(document=document, clause_id=clause_id, seed=run_id),
        ),
        evidence_anchors=(anchor,),
        entity_proposals=(entity,),
        assertion_proposals=(assertion,),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="ontology-guided-knowledge-proposal",
            extractor_version="1.0.0",
            model="granite",
            provider="ramalama",
            prompt_version="ontology-guided-assertions-source-bound-v1",
            request_contract_id=KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
            output_contract_id=KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
            source_binding_contract_id=CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        ),
    )


def _qualification_inputs():
    development_suite = _suite(
        partition=AssertionGoldenPartition.DEVELOPMENT,
        document="DEV",
        clause_id="d1",
    )
    holdout_suite = _suite(
        partition=AssertionGoldenPartition.HOLDOUT,
        document="HOLD",
        clause_id="h1",
    )
    development_proposal = _proposal(document="DEV", clause_id="d1", run_id="dev-run")
    holdout_proposal = _proposal(document="HOLD", clause_id="h1", run_id="hold-run")
    evaluator = AssertionQualificationEvaluator()
    return (
        development_suite,
        evaluator.evaluate(development_suite, (development_proposal,)),
        holdout_suite,
        evaluator.evaluate(holdout_suite, (holdout_proposal,)),
    )


def _production_inputs():
    efficient_c1 = _proposal(
        document="PROD",
        clause_id="c1",
        run_id="efficient-run",
        entity_id="e1",
        assertion_id="a1",
        label="requirement c1",
    )
    efficient_c2 = _proposal(
        document="PROD",
        clause_id="c2",
        run_id="efficient-run-2",
        entity_id="e2",
        assertion_id="a2",
        label="requirement c2",
    )
    efficient = efficient_c1.model_copy(
        update={
            "proposal_run_id": "efficient-run",
            "context_source_bindings": (
                *efficient_c1.context_source_bindings,
                *efficient_c2.context_source_bindings,
            ),
            "evidence_anchors": (
                *efficient_c1.evidence_anchors,
                *efficient_c2.evidence_anchors,
            ),
            "entity_proposals": (
                *efficient_c1.entity_proposals,
                *efficient_c2.entity_proposals,
            ),
            "assertion_proposals": (
                *efficient_c1.assertion_proposals,
                *efficient_c2.assertion_proposals,
            ),
        }
    )
    escalation = _proposal(
        document="PROD",
        clause_id="c2",
        run_id="escalation-run",
        entity_id="e3",
        assertion_id="a3",
        label="requirement c2 escalated",
    )
    escalation = escalation.model_copy(
        update={"context_source_bindings": efficient_c2.context_source_bindings}
    )
    provenance = efficient.proposal_provenance
    c1_package = efficient_c1.context_source_bindings[0].package_sha256
    c2_package = efficient_c2.context_source_bindings[0].package_sha256
    report = AssertionQualificationCascadeReport(
        cascade_run_id="cascade-prod",
        source_document_key="PROD",
        ontology_versions=ONTOLOGIES,
        proposal_sources=(
            AssertionCascadeProposalSource(
                stage="efficient",
                proposal_run_id=efficient.proposal_run_id,
                proposal_hash=proposal_sha256(efficient),
                extractor=provenance.extractor,
                extractor_version=provenance.extractor_version,
                model=provenance.model,
                provider=provenance.provider,
                request_contract_id=provenance.request_contract_id,
                output_contract_id=provenance.output_contract_id,
                source_binding_contract_id=provenance.source_binding_contract_id,
            ),
            AssertionCascadeProposalSource(
                stage="escalation",
                proposal_run_id=escalation.proposal_run_id,
                proposal_hash=proposal_sha256(escalation),
                extractor=escalation.proposal_provenance.extractor,
                extractor_version=escalation.proposal_provenance.extractor_version,
                model=escalation.proposal_provenance.model,
                provider=escalation.proposal_provenance.provider,
                request_contract_id=escalation.proposal_provenance.request_contract_id,
                output_contract_id=escalation.proposal_provenance.output_contract_id,
                source_binding_contract_id=(
                    escalation.proposal_provenance.source_binding_contract_id
                ),
            ),
        ),
        verifier_provenance=AssertionVerifierProvenance(
            verifier="ontology-guided-assertion-verifier",
            verifier_version="1.0.0",
            model="verify-model",
            provider="ramalama",
            prompt_version="ontology-guided-assertion-verifier-source-bound-v1",
            request_contract_id=ASSERTION_VERIFIER_REQUEST_CONTRACT,
            source_binding_contract_id=CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        ),
        clauses=(
            AssertionCascadeClauseReport(
                clause_id=ClauseId(value="c1"),
                route=AssertionCascadeRoute.EFFICIENT_ACCEPTED,
                verification=AssertionClauseVerification(
                    clause_id=ClauseId(value="c1"),
                    entity_reviews=(
                        AssertionCandidateVerification(
                            candidate_id="e1",
                            disposition=AssertionVerificationDisposition.SUPPORTED,
                        ),
                    ),
                    assertion_reviews=(
                        AssertionCandidateVerification(
                            candidate_id="a1",
                            disposition=AssertionVerificationDisposition.SUPPORTED,
                        ),
                    ),
                    source_package_sha256=c1_package,
                ),
                efficient_source_package_sha256=c1_package,
                verifier_source_package_sha256=c1_package,
                efficient_entities=1,
                efficient_assertions=1,
                final_state="technically_verified",
            ),
            AssertionCascadeClauseReport(
                clause_id=ClauseId(value="c2"),
                route=AssertionCascadeRoute.ESCALATED,
                reasons=(AssertionCascadeReason.UNCERTAIN_CANDIDATE,),
                verification=AssertionClauseVerification(
                    clause_id=ClauseId(value="c2"),
                    entity_reviews=(
                        AssertionCandidateVerification(
                            candidate_id="e2",
                            disposition=AssertionVerificationDisposition.SUPPORTED,
                        ),
                    ),
                    assertion_reviews=(
                        AssertionCandidateVerification(
                            candidate_id="a2",
                            disposition=AssertionVerificationDisposition.UNCERTAIN,
                        ),
                    ),
                    source_package_sha256=c2_package,
                ),
                efficient_source_package_sha256=c2_package,
                verifier_source_package_sha256=c2_package,
                escalation_source_package_sha256=c2_package,
                efficient_entities=1,
                efficient_assertions=1,
                escalation_entities=1,
                escalation_assertions=1,
                final_state="needs_review",
            ),
        ),
        efficient_accepted_clauses=1,
        escalated_clauses=1,
        technically_verified_clauses=1,
        needs_review_clauses=1,
    )
    return report, efficient, escalation


def test_policy_allows_only_supported_efficient_assertions() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )

    assert report.qualification_gate_passed is True
    assert report.auto_adoption_eligible_assertions == 1
    assert report.review_required_assertions == 1
    assert [(item.assertion_id, item.disposition) for item in report.decisions] == [
        ("a1", AssertionAutoAdoptionDisposition.AUTO_ADOPTION_ELIGIBLE),
        ("a3", AssertionAutoAdoptionDisposition.REVIEW_REQUIRED),
    ]
    assert report.decisions[1].reasons == (
        AssertionAutoAdoptionReason.ESCALATED_CLAUSE,
        AssertionAutoAdoptionReason.ESCALATION_NOT_REVERIFIED,
    )


def test_holdout_gate_failure_blocks_all_auto_adoption() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    strict_holdout = _thresholds(max_assertion_false_negatives=0, min_assertion_recall=1.0)
    failed_holdout = holdout_report.model_copy(
        update={
            "aggregate": holdout_report.aggregate.model_copy(
                update={
                    "assertions": CountMetrics(
                        expected=2,
                        predicted=1,
                        true_positive=1,
                        false_positive=0,
                        false_negative=1,
                        precision=RatioMetric(
                            numerator=1, denominator=1, value=1.0, status=MetricStatus.OK
                        ),
                        recall=RatioMetric(
                            numerator=1, denominator=2, value=0.5, status=MetricStatus.OK
                        ),
                        f1=RatioMetric(
                            numerator=2, denominator=3, value=2 / 3, status=MetricStatus.OK
                        ),
                        over_extraction=RatioMetric(
                            numerator=0, denominator=1, value=0.0, status=MetricStatus.OK
                        ),
                        under_extraction=RatioMetric(
                            numerator=1, denominator=2, value=0.5, status=MetricStatus.OK
                        ),
                    )
                }
            )
        }
    )

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(holdout=strict_holdout),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=failed_holdout,
        cascade_report=cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )

    assert report.qualification_gate_passed is False
    assert report.auto_adoption_eligible_assertions == 0
    efficient_decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert efficient_decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert AssertionAutoAdoptionReason.HOLDOUT_GATE_FAILED in efficient_decision.reasons


def test_pipeline_identity_drift_blocks_auto_adoption() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    drifted = holdout_report.model_copy(
        update={
            "proposal_sources": tuple(
                source.model_copy(update={"model": "different-model"})
                for source in holdout_report.proposal_sources
            )
        }
    )

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=drifted,
        cascade_report=cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )

    assert report.pipeline_identity_gate.passed is False
    assert report.qualification_gate_passed is False
    assert AssertionAutoAdoptionReason.PIPELINE_IDENTITY_MISMATCH in report.decisions[0].reasons


def test_development_and_holdout_must_not_share_source_clause() -> None:
    development_suite, development_report, _, _ = _qualification_inputs()
    holdout_suite = _suite(
        partition=AssertionGoldenPartition.HOLDOUT,
        document="DEV",
        clause_id="d1",
    )
    holdout_report = AssertionQualificationEvaluator().evaluate(
        holdout_suite,
        (_proposal(document="DEV", clause_id="d1", run_id="hold-run"),),
    )
    cascade, efficient, escalation = _production_inputs()

    with pytest.raises(ValueError, match="overlap on source clauses"):
        AssertionAutoAdoptionPolicyEvaluator().evaluate(
            policy=_policy(),
            development_suite=development_suite,
            development_report=development_report,
            holdout_suite=holdout_suite,
            holdout_report=holdout_report,
            cascade_report=cascade,
            efficient_proposal=efficient,
            escalation_proposal=escalation,
        )


def test_cascade_must_bind_exact_proposal_hash() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    tampered = efficient.model_copy(update={"proposal_run_id": "tampered"})

    with pytest.raises(ValueError, match="run id differs"):
        AssertionAutoAdoptionPolicyEvaluator().evaluate(
            policy=_policy(),
            development_suite=development_suite,
            development_report=development_report,
            holdout_suite=holdout_suite,
            holdout_report=holdout_report,
            cascade_report=cascade,
            efficient_proposal=tampered,
            escalation_proposal=escalation,
        )


def test_auto_adoption_policy_and_report_roundtrip(tmp_path) -> None:
    from standards_atlas.application.assertion_qualification import (
        load_assertion_auto_adoption_policy,
        load_assertion_auto_adoption_report,
        write_assertion_auto_adoption_report,
    )

    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(_policy().model_dump_json(indent=2), encoding="utf-8")
    loaded_policy = load_assertion_auto_adoption_policy(policy_path)
    assert loaded_policy == _policy()

    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=loaded_policy,
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )
    output = write_assertion_auto_adoption_report(report, tmp_path / "report.json")
    assert load_assertion_auto_adoption_report(output) == report


def test_cascade_diagnostic_counts_must_match_bound_proposal() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    first = cascade.clauses[0].model_copy(update={"efficient_violations": 1})
    forged = cascade.model_copy(update={"clauses": (first, cascade.clauses[1])})

    with pytest.raises(ValueError, match="diagnostic counts differ"):
        AssertionAutoAdoptionPolicyEvaluator().evaluate(
            policy=_policy(),
            development_suite=development_suite,
            development_report=development_report,
            holdout_suite=holdout_suite,
            holdout_report=holdout_report,
            cascade_report=forged,
            efficient_proposal=efficient,
            escalation_proposal=escalation,
        )


def test_non_exact_production_grounding_requires_review() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    first_anchor = efficient.evidence_anchors[0].model_copy(update={"content_hash": None})
    degraded = efficient.model_copy(
        update={"evidence_anchors": (first_anchor, *efficient.evidence_anchors[1:])}
    )
    sources = tuple(
        source.model_copy(update={"proposal_hash": proposal_sha256(degraded)})
        if source.stage == "efficient"
        else source
        for source in cascade.proposal_sources
    )
    rebound_cascade = cascade.model_copy(update={"proposal_sources": sources})

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=rebound_cascade,
        efficient_proposal=degraded,
        escalation_proposal=escalation,
    )

    decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert decision.reasons == (AssertionAutoAdoptionReason.NON_EXACT_GROUNDING,)


@pytest.mark.parametrize("entity_only", [False, True])
def test_partition_overlap_uses_cases_even_without_assertions(entity_only: bool) -> None:
    from standards_atlas.application.assertion_qualification.policy import (
        _validate_partition_separation,
    )

    dev = _suite(partition=AssertionGoldenPartition.DEVELOPMENT, document="DOC", clause_id="c1")
    case = dev.cases[0].model_copy(
        update={
            "assertions": (),
            "entities": dev.cases[0].entities if entity_only else (),
        }
    )
    dev = dev.model_copy(update={"cases": (case,)})
    holdout = dev.model_copy(update={"partition": AssertionGoldenPartition.HOLDOUT})
    with pytest.raises(ValueError, match="overlap"):
        _validate_partition_separation(dev, holdout)


def test_old_qualification_identity_does_not_authorize_source_bound_production() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()

    def legacy_report(report):
        return report.model_copy(
            update={
                "proposal_sources": tuple(
                    source.model_copy(
                        update={
                            "request_contract_id": None,
                            "output_contract_id": None,
                            "source_binding_contract_id": None,
                        }
                    )
                    for source in report.proposal_sources
                )
            }
        )

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=legacy_report(development_report),
        holdout_suite=holdout_suite,
        holdout_report=legacy_report(holdout_report),
        cascade_report=cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )

    assert report.pipeline_identity_gate.passed is False
    decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert AssertionAutoAdoptionReason.PIPELINE_IDENTITY_MISMATCH in decision.reasons


def test_unsupported_verifier_contract_cannot_authorize_source_bound_assertion() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    assert cascade.verifier_provenance is not None
    legacy_verifier = cascade.verifier_provenance.model_copy(
        update={
            "request_contract_id": None,
            "source_binding_contract_id": None,
        }
    )
    legacy_cascade = cascade.model_copy(update={"verifier_provenance": legacy_verifier})

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=legacy_cascade,
        efficient_proposal=efficient,
        escalation_proposal=escalation,
    )

    assert report.qualification_gate_passed is True
    decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert decision.reasons == (AssertionAutoAdoptionReason.UNSUPPORTED_SOURCE_CONTRACT,)


def test_incomplete_source_context_requires_review_even_with_exact_grounding() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    binding = efficient.context_source_bindings[0].model_copy(
        update={
            "selection_completeness": "incomplete",
            "selection_gap_codes": ("not_authorized",),
        }
    )
    degraded = efficient.model_copy(
        update={
            "context_source_bindings": (binding, *efficient.context_source_bindings[1:]),
        }
    )
    rebound_sources = tuple(
        source.model_copy(update={"proposal_hash": proposal_sha256(degraded)})
        if source.stage == "efficient"
        else source
        for source in cascade.proposal_sources
    )
    rebound_cascade = cascade.model_copy(update={"proposal_sources": rebound_sources})

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=rebound_cascade,
        efficient_proposal=degraded,
        escalation_proposal=escalation,
    )

    decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert decision.reasons == (AssertionAutoAdoptionReason.SOURCE_CONTEXT_INCOMPLETE,)


def test_cross_clause_evidence_requires_confirmed_reach_before_auto_adoption() -> None:
    development_suite, development_report, holdout_suite, holdout_report = _qualification_inputs()
    cascade, efficient, escalation = _production_inputs()
    foreign_anchor = efficient.evidence_anchors[0].model_copy(
        update={"source_clause_id": ClauseId(value="parent")}
    )
    contextual = efficient.model_copy(
        update={"evidence_anchors": (foreign_anchor, *efficient.evidence_anchors[1:])}
    )
    rebound_sources = tuple(
        source.model_copy(update={"proposal_hash": proposal_sha256(contextual)})
        if source.stage == "efficient"
        else source
        for source in cascade.proposal_sources
    )
    rebound_cascade = cascade.model_copy(update={"proposal_sources": rebound_sources})

    report = AssertionAutoAdoptionPolicyEvaluator().evaluate(
        policy=_policy(),
        development_suite=development_suite,
        development_report=development_report,
        holdout_suite=holdout_suite,
        holdout_report=holdout_report,
        cascade_report=rebound_cascade,
        efficient_proposal=contextual,
        escalation_proposal=escalation,
    )

    decision = next(item for item in report.decisions if item.assertion_id == "a1")
    assert decision.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
    assert decision.reasons == (AssertionAutoAdoptionReason.UNCONFIRMED_CONTEXT_REACH,)
