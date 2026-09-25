"""Slice-7C Development/Holdout gates and assertion auto-adoption eligibility."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCascadeRoute,
    AssertionQualificationCascadeReport,
    AssertionVerificationDisposition,
)
from standards_atlas.application.assertion_qualification.evaluation import (
    golden_suite_sha256,
    proposal_sha256,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationAggregate,
    AssertionQualificationProposalSource,
    AssertionQualificationReport,
)
from standards_atlas.application.assertion_qualification.policy_models import (
    AssertionAutoAdoptionDecision,
    AssertionAutoAdoptionDisposition,
    AssertionAutoAdoptionPolicy,
    AssertionAutoAdoptionReason,
    AssertionAutoAdoptionReport,
    AssertionPartitionQualityGate,
    AssertionPipelineIdentityGate,
    AssertionProposalRuntimeIdentity,
    AssertionQualityGateCheck,
    AssertionQualityGateOperator,
    AssertionQualityThresholds,
)
from standards_atlas.domain.model import (
    DocumentKnowledgeProposal,
    EvidenceSourceKind,
    NormativeAssertionProposal,
)


class AssertionAutoAdoptionPolicyEvaluator:
    """Evaluate qualification gates and mark effective assertions as eligible or review-only.

    Slice 7C deliberately stops before canonical adoption. Only verifier-supported efficient-stage
    assertions may become auto-adoption eligible. Escalation output is retained as review material
    because Slice 7B does not independently re-verify the escalation stage.
    """

    def evaluate(
        self,
        *,
        policy: AssertionAutoAdoptionPolicy,
        development_suite: AssertionGoldenSuite,
        development_report: AssertionQualificationReport,
        holdout_suite: AssertionGoldenSuite,
        holdout_report: AssertionQualificationReport,
        cascade_report: AssertionQualificationCascadeReport,
        efficient_proposal: DocumentKnowledgeProposal,
        escalation_proposal: DocumentKnowledgeProposal | None = None,
    ) -> AssertionAutoAdoptionReport:
        _validate_partition_binding(
            suite=development_suite,
            report=development_report,
            expected=AssertionGoldenPartition.DEVELOPMENT,
            policy=policy,
        )
        _validate_partition_binding(
            suite=holdout_suite,
            report=holdout_report,
            expected=AssertionGoldenPartition.HOLDOUT,
            policy=policy,
        )
        _validate_partition_separation(development_suite, holdout_suite)
        _validate_cascade_inputs(
            policy=policy,
            cascade=cascade_report,
            efficient=efficient_proposal,
            escalation=escalation_proposal,
        )

        development_gate = _partition_gate(
            development_report,
            development_suite,
            policy.development,
        )
        holdout_gate = _partition_gate(
            holdout_report,
            holdout_suite,
            policy.holdout,
        )
        pipeline_gate = _pipeline_identity_gate(
            development_report,
            holdout_report,
            efficient_proposal,
        )
        qualification_passed = (
            development_gate.passed and holdout_gate.passed and pipeline_gate.passed
        )
        global_reasons = _global_failure_reasons(
            development_gate=development_gate,
            holdout_gate=holdout_gate,
            pipeline_gate=pipeline_gate,
        )

        decisions = _assertion_decisions(
            cascade=cascade_report,
            efficient=efficient_proposal,
            escalation=escalation_proposal,
            qualification_passed=qualification_passed,
            global_reasons=global_reasons,
        )
        cascade_sources = {source.stage: source for source in cascade_report.proposal_sources}
        efficient_source = cascade_sources["efficient"]
        escalation_source = cascade_sources.get("escalation")
        return AssertionAutoAdoptionReport(
            policy_id=policy.id,
            policy_version=policy.version,
            policy_hash=auto_adoption_policy_sha256(policy),
            ontology_versions=policy.ontology_versions,
            development_gate=development_gate,
            holdout_gate=holdout_gate,
            pipeline_identity_gate=pipeline_gate,
            qualification_gate_passed=qualification_passed,
            cascade_run_id=cascade_report.cascade_run_id,
            cascade_report_hash=cascade_report_sha256(cascade_report),
            source_document_key=cascade_report.source_document_key,
            efficient_proposal_run_id=efficient_source.proposal_run_id,
            efficient_proposal_hash=efficient_source.proposal_hash,
            escalation_proposal_run_id=(
                escalation_source.proposal_run_id if escalation_source is not None else None
            ),
            escalation_proposal_hash=(
                escalation_source.proposal_hash if escalation_source is not None else None
            ),
            decisions=decisions,
            auto_adoption_eligible_assertions=sum(
                item.disposition is AssertionAutoAdoptionDisposition.AUTO_ADOPTION_ELIGIBLE
                for item in decisions
            ),
            review_required_assertions=sum(
                item.disposition is AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
                for item in decisions
            ),
            efficient_accepted_clauses=cascade_report.efficient_accepted_clauses,
            escalated_clauses=cascade_report.escalated_clauses,
        )


def auto_adoption_policy_sha256(policy: AssertionAutoAdoptionPolicy) -> str:
    return _model_sha256(policy.model_dump(mode="json"))


def qualification_report_sha256(report: AssertionQualificationReport) -> str:
    return _model_sha256(report.model_dump(mode="json"))


def cascade_report_sha256(report: AssertionQualificationCascadeReport) -> str:
    return _model_sha256(report.model_dump(mode="json"))


def _validate_partition_binding(
    *,
    suite: AssertionGoldenSuite,
    report: AssertionQualificationReport,
    expected: AssertionGoldenPartition,
    policy: AssertionAutoAdoptionPolicy,
) -> None:
    if suite.partition is not expected or report.golden_partition is not expected:
        raise ValueError(f"assertion auto-adoption requires a {expected.value} golden partition")
    if tuple(suite.ontology_versions) != tuple(policy.ontology_versions):
        raise ValueError(f"{expected.value} golden suite ontology versions differ from policy")
    if tuple(report.ontology_versions) != tuple(policy.ontology_versions):
        raise ValueError(f"{expected.value} qualification ontology versions differ from policy")
    expected_identity = (suite.id, suite.version, golden_suite_sha256(suite))
    actual_identity = (
        report.golden_suite_id,
        report.golden_suite_version,
        report.golden_suite_hash,
    )
    if actual_identity != expected_identity:
        raise ValueError(f"{expected.value} qualification report does not bind the supplied suite")


def _validate_partition_separation(
    development: AssertionGoldenSuite,
    holdout: AssertionGoldenSuite,
) -> None:
    development_clauses = _golden_assertion_clauses(development)
    holdout_clauses = _golden_assertion_clauses(holdout)
    overlap = development_clauses & holdout_clauses
    if overlap:
        preview = sorted(overlap)[:5]
        raise ValueError(
            f"development and holdout assertion suites overlap on source clauses: {preview!r}"
        )


def _golden_assertion_clauses(suite: AssertionGoldenSuite) -> set[tuple[str, str]]:
    return {
        (case.source_document_key, assertion.source_clause_id.value)
        for case in suite.cases
        for assertion in case.assertions
    }


def _validate_cascade_inputs(
    *,
    policy: AssertionAutoAdoptionPolicy,
    cascade: AssertionQualificationCascadeReport,
    efficient: DocumentKnowledgeProposal,
    escalation: DocumentKnowledgeProposal | None,
) -> None:
    if tuple(cascade.ontology_versions) != tuple(policy.ontology_versions):
        raise ValueError("cascade ontology versions differ from auto-adoption policy")
    if efficient.source_document_key != cascade.source_document_key:
        raise ValueError("efficient proposal belongs to a different source document")
    if tuple(efficient.ontology_versions) != tuple(policy.ontology_versions):
        raise ValueError("efficient proposal ontology versions differ from auto-adoption policy")
    sources = {source.stage: source for source in cascade.proposal_sources}
    _validate_proposal_source(sources["efficient"], efficient)

    escalation_source = sources.get("escalation")
    if escalation_source is None:
        if escalation is not None:
            raise ValueError("escalation proposal supplied for a cascade without escalation")
    else:
        if escalation is None:
            raise ValueError("escalated cascade requires its exact escalation proposal artifact")
        if escalation.source_document_key != cascade.source_document_key:
            raise ValueError("escalation proposal belongs to a different source document")
        if tuple(escalation.ontology_versions) != tuple(policy.ontology_versions):
            raise ValueError(
                "escalation proposal ontology versions differ from auto-adoption policy"
            )
        _validate_proposal_source(escalation_source, escalation)

    clause_ids = {clause.clause_id.value for clause in cascade.clauses}
    efficient_metadata_clause_ids = {
        item.clause_id.value for item in (*efficient.violations, *efficient.failures)
    }
    if not efficient_metadata_clause_ids <= clause_ids:
        raise ValueError("efficient proposal diagnostics fall outside the cascade clause set")
    efficient_clause_ids = {
        assertion.source_clause_id.value for assertion in efficient.assertion_proposals
    }
    if not efficient_clause_ids <= clause_ids:
        raise ValueError("efficient proposal contains assertions outside the cascade clause set")
    if escalation is not None:
        escalated_clause_ids = {
            clause.clause_id.value
            for clause in cascade.clauses
            if clause.route is AssertionCascadeRoute.ESCALATED
        }
        escalation_clause_ids = {
            assertion.source_clause_id.value for assertion in escalation.assertion_proposals
        }
        escalation_metadata_clause_ids = {
            item.clause_id.value for item in (*escalation.violations, *escalation.failures)
        }
        if not escalation_clause_ids <= escalated_clause_ids:
            raise ValueError("escalation proposal contains assertions for non-escalated clauses")
        if not escalation_metadata_clause_ids <= escalated_clause_ids:
            raise ValueError("escalation proposal diagnostics belong to non-escalated clauses")

    for clause in cascade.clauses:
        clause_id = clause.clause_id.value
        efficient_violations = sum(
            item.clause_id.value == clause_id for item in efficient.violations
        )
        efficient_failures = sum(item.clause_id.value == clause_id for item in efficient.failures)
        if (clause.efficient_violations, clause.efficient_failures) != (
            efficient_violations,
            efficient_failures,
        ):
            raise ValueError("cascade efficient diagnostic counts differ from proposal artifact")
        if escalation is not None and clause.route is AssertionCascadeRoute.ESCALATED:
            escalation_violations = sum(
                item.clause_id.value == clause_id for item in escalation.violations
            )
            escalation_failures = sum(
                item.clause_id.value == clause_id for item in escalation.failures
            )
            if (clause.escalation_violations, clause.escalation_failures) != (
                escalation_violations,
                escalation_failures,
            ):
                raise ValueError(
                    "cascade escalation diagnostic counts differ from proposal artifact"
                )


def _validate_proposal_source(source, proposal: DocumentKnowledgeProposal) -> None:
    if source.proposal_run_id != proposal.proposal_run_id:
        raise ValueError(f"{source.stage} proposal run id differs from cascade report")
    if source.proposal_hash != proposal_sha256(proposal):
        raise ValueError(f"{source.stage} proposal hash differs from cascade report")
    provenance = proposal.proposal_provenance
    expected = (
        provenance.extractor,
        provenance.extractor_version,
        provenance.model,
        provenance.provider,
    )
    actual = (
        source.extractor,
        source.extractor_version,
        source.model,
        source.provider,
    )
    if actual != expected:
        raise ValueError(f"{source.stage} proposal provenance differs from cascade report")


def _partition_gate(
    report: AssertionQualificationReport,
    suite: AssertionGoldenSuite,
    thresholds: AssertionQualityThresholds,
) -> AssertionPartitionQualityGate:
    aggregate = report.aggregate
    violations = sum(case.proposal_violations for case in report.cases)
    failures = sum(case.proposal_failures for case in report.cases)
    checks = (
        _ge("expected_entities", aggregate.entities.expected, thresholds.min_expected_entities),
        _ge(
            "expected_assertions",
            aggregate.assertions.expected,
            thresholds.min_expected_assertions,
        ),
        _ge("entity_precision", aggregate.entities.precision, thresholds.min_entity_precision),
        _ge("entity_recall", aggregate.entities.recall, thresholds.min_entity_recall),
        _ge(
            "assertion_precision",
            aggregate.assertions.precision,
            thresholds.min_assertion_precision,
        ),
        _ge(
            "assertion_recall",
            aggregate.assertions.recall,
            thresholds.min_assertion_recall,
        ),
        _ge(
            "predicate_accuracy",
            aggregate.predicate_accuracy.accuracy,
            thresholds.min_predicate_accuracy,
        ),
        _ge(
            "normative_force_accuracy",
            aggregate.normative_force_accuracy.accuracy,
            thresholds.min_normative_force_accuracy,
        ),
        _ge(
            "grounding_accuracy",
            aggregate.grounding_accuracy.accuracy,
            thresholds.min_grounding_accuracy,
        ),
        _ge(
            "exact_assertion_accuracy",
            aggregate.exact_assertion_accuracy.accuracy,
            thresholds.min_exact_assertion_accuracy,
        ),
        *_optional_max_checks(aggregate, thresholds),
        _le("proposal_violations", violations, thresholds.max_proposal_violations),
        _le("proposal_failures", failures, thresholds.max_proposal_failures),
    )
    return AssertionPartitionQualityGate(
        partition=report.golden_partition,
        golden_suite_id=suite.id,
        golden_suite_version=suite.version,
        golden_suite_hash=golden_suite_sha256(suite),
        qualification_report_hash=qualification_report_sha256(report),
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def _optional_max_checks(
    aggregate: AssertionQualificationAggregate,
    thresholds: AssertionQualityThresholds,
) -> tuple[AssertionQualityGateCheck, ...]:
    values = (
        (
            "entity_false_positives",
            aggregate.entities.false_positive,
            thresholds.max_entity_false_positives,
        ),
        (
            "entity_false_negatives",
            aggregate.entities.false_negative,
            thresholds.max_entity_false_negatives,
        ),
        (
            "assertion_false_positives",
            aggregate.assertions.false_positive,
            thresholds.max_assertion_false_positives,
        ),
        (
            "assertion_false_negatives",
            aggregate.assertions.false_negative,
            thresholds.max_assertion_false_negatives,
        ),
    )
    return tuple(
        _le(name, observed, limit) for name, observed, limit in values if limit is not None
    )


def _pipeline_identity_gate(
    development: AssertionQualificationReport,
    holdout: AssertionQualificationReport,
    efficient: DocumentKnowledgeProposal,
) -> AssertionPipelineIdentityGate:
    development_identity = _qualified_runtime_identity(development.proposal_sources)
    holdout_identity = _qualified_runtime_identity(holdout.proposal_sources)
    provenance = efficient.proposal_provenance
    production_identity = AssertionProposalRuntimeIdentity(
        extractor=provenance.extractor,
        extractor_version=provenance.extractor_version,
        model=provenance.model,
        provider=provenance.provider,
        prompt_version=provenance.prompt_version,
    )
    passed = (
        development_identity is not None
        and holdout_identity is not None
        and development_identity == holdout_identity == production_identity
    )
    reason = (
        None if passed else "qualified efficient-stage runtime identity differs from production"
    )
    return AssertionPipelineIdentityGate(
        development=development_identity,
        holdout=holdout_identity,
        production=production_identity,
        passed=passed,
        reason=reason,
    )


def _qualified_runtime_identity(
    sources: Iterable[AssertionQualificationProposalSource],
) -> AssertionProposalRuntimeIdentity | None:
    identities = {
        AssertionProposalRuntimeIdentity(
            extractor=source.extractor,
            extractor_version=source.extractor_version,
            model=source.model,
            provider=source.provider,
            prompt_version=source.prompt_version,
        )
        for source in sources
    }
    return next(iter(identities)) if len(identities) == 1 else None


def _global_failure_reasons(
    *,
    development_gate: AssertionPartitionQualityGate,
    holdout_gate: AssertionPartitionQualityGate,
    pipeline_gate: AssertionPipelineIdentityGate,
) -> tuple[AssertionAutoAdoptionReason, ...]:
    reasons: list[AssertionAutoAdoptionReason] = []
    if not development_gate.passed:
        reasons.append(AssertionAutoAdoptionReason.DEVELOPMENT_GATE_FAILED)
    if not holdout_gate.passed:
        reasons.append(AssertionAutoAdoptionReason.HOLDOUT_GATE_FAILED)
    if not pipeline_gate.passed:
        reasons.append(AssertionAutoAdoptionReason.PIPELINE_IDENTITY_MISMATCH)
    return tuple(reasons)


def _assertion_decisions(
    *,
    cascade: AssertionQualificationCascadeReport,
    efficient: DocumentKnowledgeProposal,
    escalation: DocumentKnowledgeProposal | None,
    qualification_passed: bool,
    global_reasons: tuple[AssertionAutoAdoptionReason, ...],
) -> tuple[AssertionAutoAdoptionDecision, ...]:
    efficient_by_clause = _assertions_by_clause(efficient.assertion_proposals)
    escalation_by_clause = (
        _assertions_by_clause(escalation.assertion_proposals) if escalation is not None else {}
    )
    decisions: list[AssertionAutoAdoptionDecision] = []
    for clause in cascade.clauses:
        clause_id = clause.clause_id.value
        if clause.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED:
            assertions = efficient_by_clause.get(clause_id, ())
            _validate_supported_efficient_assertions(clause, assertions, efficient)
            for assertion in assertions:
                local_reasons = _production_assertion_reasons(efficient, assertion)
                reasons = tuple(dict.fromkeys((*global_reasons, *local_reasons)))
                disposition = (
                    AssertionAutoAdoptionDisposition.AUTO_ADOPTION_ELIGIBLE
                    if qualification_passed and not local_reasons
                    else AssertionAutoAdoptionDisposition.REVIEW_REQUIRED
                )
                decisions.append(
                    _decision(
                        stage="efficient",
                        proposal=efficient,
                        assertion=assertion,
                        disposition=disposition,
                        reasons=reasons,
                    )
                )
            continue

        assertions = escalation_by_clause.get(clause_id, ())
        reasons = tuple(
            dict.fromkeys(
                (
                    *global_reasons,
                    AssertionAutoAdoptionReason.ESCALATED_CLAUSE,
                    AssertionAutoAdoptionReason.ESCALATION_NOT_REVERIFIED,
                )
            )
        )
        if escalation is not None:
            for assertion in assertions:
                decisions.append(
                    _decision(
                        stage="escalation",
                        proposal=escalation,
                        assertion=assertion,
                        disposition=AssertionAutoAdoptionDisposition.REVIEW_REQUIRED,
                        reasons=reasons,
                    )
                )
    return tuple(decisions)


def _validate_supported_efficient_assertions(
    clause,
    assertions: tuple[NormativeAssertionProposal, ...],
    proposal: DocumentKnowledgeProposal,
) -> None:
    if clause.verification is None:
        raise ValueError("efficient-accepted clause has no verifier evidence")
    assertion_reviews = {
        review.candidate_id: review for review in clause.verification.assertion_reviews
    }
    entity_reviews = {review.candidate_id: review for review in clause.verification.entity_reviews}
    for assertion in assertions:
        review = assertion_reviews.get(assertion.id)
        if review is None or review.disposition is not AssertionVerificationDisposition.SUPPORTED:
            raise ValueError("efficient assertion lacks a supported verifier decision")
        for entity_id in _required_entity_ids(assertion):
            entity_review = entity_reviews.get(entity_id)
            if entity_review is None or (
                entity_review.disposition is not AssertionVerificationDisposition.SUPPORTED
            ):
                raise ValueError("efficient assertion depends on an unsupported entity candidate")
    proposal_entity_ids = {entity.id for entity in proposal.entity_proposals}
    if any(
        entity_id not in proposal_entity_ids
        for item in assertions
        for entity_id in _required_entity_ids(item)
    ):
        raise ValueError("efficient assertion references an entity missing from its proposal")


def _production_assertion_reasons(
    proposal: DocumentKnowledgeProposal,
    assertion: NormativeAssertionProposal,
) -> tuple[AssertionAutoAdoptionReason, ...]:
    anchor_by_id = {anchor.id: anchor for anchor in proposal.evidence_anchors}
    entity_by_id = {entity.id: entity for entity in proposal.entity_proposals}
    assertion_anchors = tuple(
        anchor_by_id[anchor_id] for anchor_id in assertion.evidence_anchor_ids
    )
    if any(
        anchor.source_clause_id != assertion.source_clause_id
        or anchor.source_kind is not EvidenceSourceKind.BODY
        or not _anchor_is_exact(anchor)
        for anchor in assertion_anchors
    ):
        return (AssertionAutoAdoptionReason.NON_EXACT_GROUNDING,)
    for entity_id in _required_entity_ids(assertion):
        entity = entity_by_id[entity_id]
        if any(
            not _anchor_is_exact(anchor_by_id[anchor_id]) for anchor_id in entity.source_anchor_ids
        ):
            return (AssertionAutoAdoptionReason.NON_EXACT_GROUNDING,)
    return ()


def _anchor_is_exact(anchor) -> bool:
    return (
        anchor.start_offset is not None
        and anchor.end_offset is not None
        and anchor.content_hash is not None
    )


def _decision(
    *,
    stage: str,
    proposal: DocumentKnowledgeProposal,
    assertion: NormativeAssertionProposal,
    disposition: AssertionAutoAdoptionDisposition,
    reasons: tuple[AssertionAutoAdoptionReason, ...],
) -> AssertionAutoAdoptionDecision:
    return AssertionAutoAdoptionDecision(
        source_stage=stage,
        proposal_run_id=proposal.proposal_run_id,
        assertion_id=assertion.id,
        source_clause_id=assertion.source_clause_id,
        predicate=assertion.predicate,
        normative_force=assertion.normative_force,
        required_entity_ids=_required_entity_ids(assertion),
        evidence_anchor_ids=assertion.evidence_anchor_ids,
        disposition=disposition,
        reasons=reasons,
    )


def _required_entity_ids(assertion: NormativeAssertionProposal) -> tuple[str, ...]:
    if assertion.object.kind == "entity":
        return tuple(dict.fromkeys((assertion.subject_id, assertion.object.entity_id)))
    return (assertion.subject_id,)


def _assertions_by_clause(
    assertions: Iterable[NormativeAssertionProposal],
) -> dict[str, tuple[NormativeAssertionProposal, ...]]:
    grouped: dict[str, list[NormativeAssertionProposal]] = {}
    for assertion in assertions:
        grouped.setdefault(assertion.source_clause_id.value, []).append(assertion)
    return {key: tuple(value) for key, value in grouped.items()}


def _ge(
    metric: str,
    observed: int | float | None,
    threshold: int | float,
) -> AssertionQualityGateCheck:
    value = None if observed is None else float(observed)
    return AssertionQualityGateCheck(
        metric=metric,
        operator=AssertionQualityGateOperator.GREATER_OR_EQUAL,
        observed=value,
        threshold=float(threshold),
        passed=value is not None and value >= float(threshold),
    )


def _le(
    metric: str,
    observed: int | float | None,
    threshold: int | float,
) -> AssertionQualityGateCheck:
    value = None if observed is None else float(observed)
    return AssertionQualityGateCheck(
        metric=metric,
        operator=AssertionQualityGateOperator.LESS_OR_EQUAL,
        observed=value,
        threshold=float(threshold),
        passed=value is not None and value <= float(threshold),
    )


def _model_sha256(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
