"""Deterministic strict matching and diagnostic alignment for AP01 Series B."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from standards_atlas.application.assertion_qualification.models import (
    AccuracyMetrics,
    AssertionGoldenCase,
    AssertionQualificationAggregate,
    AssertionQualificationCaseReport,
    CaseExactMatch,
    CaseExactMatchStatus,
    ClauseExactMatchAggregate,
    ComparisonAlignmentRecord,
    ComparisonAlignmentStatus,
    CountMetrics,
    EvidenceIntegrityFinding,
    EvidenceIntegrityMetrics,
    EvidenceIntegrityStatus,
    GoldenEvidenceSpan,
    GoldenNormativeAssertion,
    MetricStatus,
    RatioMetric,
    SemanticEvidenceMetrics,
)
from standards_atlas.application.assertion_qualification.projection import ClauseEvaluationCandidate
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionProposalAssertionSnapshot,
    AssertionProposalEvidenceSnapshot,
)
from standards_atlas.application.assertion_qualification.source_resolution import (
    FrozenSourceResolver,
)
from standards_atlas.domain.model import EntityAssertionObject, LiteralAssertionObject

_Signature = tuple[Hashable, ...]


@dataclass(frozen=True)
class _AssertionRecord:
    id: str
    endpoint: _Signature
    relation: _Signature
    normative_force: str
    evidence: _Signature


@dataclass(frozen=True)
class _AlignmentSummary:
    records: tuple[ComparisonAlignmentRecord, ...]
    pairs: tuple[tuple[str, str], ...]
    ambiguous_expected: int
    ambiguous_predicted: int
    unmatched_expected: int
    unmatched_predicted: int


@dataclass(frozen=True)
class CaseMatchResult:
    report: AssertionQualificationCaseReport


def evaluate_case(
    golden: AssertionGoldenCase,
    proposal: ClauseEvaluationCandidate | None,
    *,
    source_resolver: FrozenSourceResolver | None = None,
) -> CaseMatchResult:
    """Evaluate one case without semantic guessing or best-fit attribute pairing."""
    golden_entities = {entity.id: entity for entity in golden.entities}
    proposal_entities = (
        {entity.id: entity for entity in proposal.entities} if proposal is not None else {}
    )

    golden_entity_identity = {
        item_id: (_normalize_label(item.normalized_label),)
        for item_id, item in golden_entities.items()
    }
    proposal_entity_identity = {
        item_id: (_normalize_label(item.normalized_label),)
        for item_id, item in proposal_entities.items()
    }
    golden_typed_identity = {
        item_id: (*golden_entity_identity[item_id], item.class_iri)
        for item_id, item in golden_entities.items()
    }
    proposal_typed_identity = {
        item_id: (*proposal_entity_identity[item_id], item.class_iri)
        for item_id, item in proposal_entities.items()
    }

    entity_metrics = _count_metrics(
        Counter(golden_entity_identity.values()), Counter(proposal_entity_identity.values())
    )
    typed_entity_metrics = _count_metrics(
        Counter(golden_typed_identity.values()), Counter(proposal_typed_identity.values())
    )
    entity_alignment = _alignment(
        source_document_key=golden.source_document_key,
        clause_id=golden.clause_id,
        rule="entity_label_identity",
        expected=golden_entity_identity,
        predicted=proposal_entity_identity,
    )
    entity_class_accuracy = _attribute_accuracy(
        entity_alignment,
        expected_values={item_id: item.class_iri for item_id, item in golden_entities.items()},
        predicted_values={item_id: item.class_iri for item_id, item in proposal_entities.items()},
    )

    golden_assertions = tuple(
        _golden_assertion_record(assertion, golden_entity_identity)
        for assertion in golden.assertions
    )
    proposal_assertions = tuple(
        _proposal_assertion_record(
            assertion,
            proposal_entity_identity,
            source_clause_id=golden.clause_id.value,
            source_document_key=golden.source_document_key,
        )
        for assertion in (proposal.assertions if proposal is not None else ())
    )
    golden_relation_counts = Counter(item.relation for item in golden_assertions)
    proposal_relation_counts = Counter(item.relation for item in proposal_assertions)
    assertion_metrics = _count_metrics(golden_relation_counts, proposal_relation_counts)

    endpoint_alignment = _alignment(
        source_document_key=golden.source_document_key,
        clause_id=golden.clause_id,
        rule="assertion_endpoint_identity",
        expected={item.id: item.endpoint for item in golden_assertions},
        predicted={item.id: item.endpoint for item in proposal_assertions},
    )
    relation_alignment = _alignment(
        source_document_key=golden.source_document_key,
        clause_id=golden.clause_id,
        rule="assertion_relation_identity",
        expected={item.id: item.relation for item in golden_assertions},
        predicted={item.id: item.relation for item in proposal_assertions},
    )

    predicate_accuracy = _attribute_accuracy(
        endpoint_alignment,
        expected_values={item.id: item.relation[-1] for item in golden_assertions},
        predicted_values={item.id: item.relation[-1] for item in proposal_assertions},
    )
    normative_force_accuracy = _attribute_accuracy(
        relation_alignment,
        expected_values={item.id: item.normative_force for item in golden_assertions},
        predicted_values={item.id: item.normative_force for item in proposal_assertions},
    )
    evidence_span_exact_match = _attribute_accuracy(
        relation_alignment,
        expected_values={item.id: item.evidence for item in golden_assertions},
        predicted_values={item.id: item.evidence for item in proposal_assertions},
    )
    exact_assertion_accuracy = _attribute_accuracy(
        relation_alignment,
        expected_values={
            item.id: (item.normative_force, item.evidence) for item in golden_assertions
        },
        predicted_values={
            item.id: (item.normative_force, item.evidence) for item in proposal_assertions
        },
    )

    evidence_findings = _evidence_integrity_findings(
        golden.source_document_key,
        proposal,
        source_resolver=source_resolver,
    )
    evidence_integrity = _evidence_integrity_metrics(evidence_findings)

    clause_exact_match = _case_exact_match(
        proposal=proposal,
        golden_typed_entities=golden_typed_identity,
        proposal_typed_entities=proposal_typed_identity,
        golden_assertions=golden_assertions,
        proposal_assertions=proposal_assertions,
    )

    return CaseMatchResult(
        report=AssertionQualificationCaseReport(
            source_document_key=golden.source_document_key,
            clause_id=golden.clause_id,
            reference=golden.reference,
            source_sha256=golden.source_sha256,
            candidate_status="present" if proposal is not None else "missing",
            candidate_sha256=proposal.candidate_sha256 if proposal is not None else None,
            provenance=proposal.provenance if proposal is not None else None,
            entities=entity_metrics,
            typed_entities=typed_entity_metrics,
            entity_class_accuracy=entity_class_accuracy,
            assertions=assertion_metrics,
            predicate_accuracy=predicate_accuracy,
            normative_force_accuracy=normative_force_accuracy,
            evidence_integrity=evidence_integrity,
            evidence_span_exact_match=evidence_span_exact_match,
            semantic_evidence=SemanticEvidenceMetrics(),
            exact_assertion_accuracy=exact_assertion_accuracy,
            clause_exact_match=clause_exact_match,
            entity_alignment=entity_alignment.records,
            assertion_endpoint_alignment=endpoint_alignment.records,
            assertion_relation_alignment=relation_alignment.records,
            evidence_integrity_findings=evidence_findings,
            entity_false_positive_ids=_unmatched_ids(
                proposal_entity_identity, golden_entity_identity
            ),
            entity_false_negative_ids=_unmatched_ids(
                golden_entity_identity, proposal_entity_identity
            ),
            assertion_false_positive_ids=_unmatched_record_ids(
                proposal_assertions, golden_assertions, key="relation"
            ),
            assertion_false_negative_ids=_unmatched_record_ids(
                golden_assertions, proposal_assertions, key="relation"
            ),
            proposal_violations=len(proposal.violations) if proposal is not None else 0,
            proposal_failures=len(proposal.failures) if proposal is not None else 0,
            violation_details=proposal.violations if proposal is not None else (),
            failure_details=proposal.failures if proposal is not None else (),
        )
    )


def aggregate_case_reports(
    reports: Sequence[AssertionQualificationCaseReport],
) -> AssertionQualificationAggregate:
    if not reports:
        raise ValueError("assertion qualification requires at least one case report")
    return AssertionQualificationAggregate(
        documents=len({report.source_document_key for report in reports}),
        clauses=len(reports),
        candidate_clauses=sum(report.candidate_status == "present" for report in reports),
        entities=_sum_count_metrics(report.entities for report in reports),
        typed_entities=_sum_count_metrics(report.typed_entities for report in reports),
        entity_class_accuracy=_sum_accuracy(report.entity_class_accuracy for report in reports),
        assertions=_sum_count_metrics(report.assertions for report in reports),
        predicate_accuracy=_sum_accuracy(report.predicate_accuracy for report in reports),
        normative_force_accuracy=_sum_accuracy(
            report.normative_force_accuracy for report in reports
        ),
        evidence_integrity=_sum_evidence_integrity(report.evidence_integrity for report in reports),
        evidence_span_exact_match=_sum_accuracy(
            report.evidence_span_exact_match for report in reports
        ),
        semantic_evidence=SemanticEvidenceMetrics(),
        exact_assertion_accuracy=_sum_accuracy(
            report.exact_assertion_accuracy for report in reports
        ),
        clause_exact_match=_aggregate_clause_exact_match(reports),
    )


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _golden_assertion_record(
    assertion: GoldenNormativeAssertion,
    entity_signatures: Mapping[str, _Signature],
) -> _AssertionRecord:
    endpoint = _assertion_endpoint(
        source_clause_id=assertion.source_clause_id.value,
        subject=entity_signatures[assertion.subject_id],
        object_=_object_signature(assertion.object, entity_signatures),
    )
    return _AssertionRecord(
        id=assertion.id,
        endpoint=endpoint,
        relation=(*endpoint, assertion.predicate),
        normative_force=assertion.normative_force.value,
        evidence=_golden_evidence_signature(assertion.evidence),
    )


def _proposal_assertion_record(
    assertion: AssertionProposalAssertionSnapshot,
    entity_signatures: Mapping[str, _Signature],
    *,
    source_clause_id: str,
    source_document_key: str,
) -> _AssertionRecord:
    endpoint = _assertion_endpoint(
        source_clause_id=source_clause_id,
        subject=entity_signatures.get(assertion.subject_id, ("unresolved", assertion.subject_id)),
        object_=_object_signature(assertion.object, entity_signatures),
    )
    return _AssertionRecord(
        id=assertion.id,
        endpoint=endpoint,
        relation=(*endpoint, assertion.predicate),
        normative_force=assertion.normative_force.value,
        evidence=_proposal_evidence_signature(
            assertion.evidence, source_document_key=source_document_key
        ),
    )


def _assertion_endpoint(
    *, source_clause_id: str, subject: _Signature, object_: _Signature
) -> _Signature:
    return (source_clause_id, subject, object_)


def _object_signature(
    object_: EntityAssertionObject | LiteralAssertionObject,
    entity_signatures: Mapping[str, _Signature],
) -> _Signature:
    if isinstance(object_, EntityAssertionObject):
        return (
            "entity",
            entity_signatures.get(object_.entity_id, ("unresolved", object_.entity_id)),
        )
    return (
        "literal",
        type(object_.value).__name__,
        object_.value,
        object_.datatype_iri,
        object_.language,
    )


def _golden_evidence_signature(spans: Sequence[GoldenEvidenceSpan]) -> _Signature:
    return tuple(
        sorted(
            (
                (
                    span.source_document_key,
                    span.clause_id.value,
                    span.source_kind.value,
                    span.start_offset,
                    span.end_offset,
                    span.content_hash,
                )
                for span in spans
            ),
            key=repr,
        )
    )


def _proposal_evidence_signature(
    anchors: Sequence[AssertionProposalEvidenceSnapshot],
    *,
    source_document_key: str,
) -> _Signature:
    return tuple(
        sorted(
            (
                (
                    source_document_key,
                    anchor.source_clause_id,
                    anchor.source_kind.value,
                    anchor.start_offset,
                    anchor.end_offset,
                    anchor.content_hash,
                )
                for anchor in anchors
            ),
            key=repr,
        )
    )


def _alignment(
    *,
    source_document_key: str,
    clause_id,
    rule: str,
    expected: Mapping[str, _Signature],
    predicted: Mapping[str, _Signature],
) -> _AlignmentSummary:
    expected_buckets: dict[_Signature, list[str]] = defaultdict(list)
    predicted_buckets: dict[_Signature, list[str]] = defaultdict(list)
    for item_id, signature in expected.items():
        expected_buckets[signature].append(item_id)
    for item_id, signature in predicted.items():
        predicted_buckets[signature].append(item_id)

    records: list[ComparisonAlignmentRecord] = []
    pairs: list[tuple[str, str]] = []
    ambiguous_expected = ambiguous_predicted = 0
    unmatched_expected = unmatched_predicted = 0
    for signature in sorted(set(expected_buckets) | set(predicted_buckets), key=repr):
        golden_ids = tuple(sorted(expected_buckets.get(signature, ())))
        candidate_ids = tuple(sorted(predicted_buckets.get(signature, ())))
        if len(golden_ids) == len(candidate_ids) == 1:
            status = ComparisonAlignmentStatus.MATCHED
            pairs.append((golden_ids[0], candidate_ids[0]))
        elif golden_ids and candidate_ids:
            status = ComparisonAlignmentStatus.AMBIGUOUS
            ambiguous_expected += len(golden_ids)
            ambiguous_predicted += len(candidate_ids)
        elif golden_ids:
            status = ComparisonAlignmentStatus.EXPECTED_ONLY
            unmatched_expected += len(golden_ids)
        else:
            status = ComparisonAlignmentStatus.CANDIDATE_ONLY
            unmatched_predicted += len(candidate_ids)
        records.append(
            ComparisonAlignmentRecord(
                source_document_key=source_document_key,
                clause_id=clause_id,
                rule=rule,
                status=status,
                golden_ids=golden_ids,
                candidate_ids=candidate_ids,
            )
        )
    return _AlignmentSummary(
        records=tuple(records),
        pairs=tuple(pairs),
        ambiguous_expected=ambiguous_expected,
        ambiguous_predicted=ambiguous_predicted,
        unmatched_expected=unmatched_expected,
        unmatched_predicted=unmatched_predicted,
    )


def _attribute_accuracy(
    alignment: _AlignmentSummary,
    *,
    expected_values: Mapping[str, Hashable],
    predicted_values: Mapping[str, Hashable],
) -> AccuracyMetrics:
    evaluated = len(alignment.pairs)
    correct = sum(
        expected_values[golden_id] == predicted_values[candidate_id]
        for golden_id, candidate_id in alignment.pairs
    )
    support_expected = evaluated + alignment.ambiguous_expected + alignment.unmatched_expected
    support_predicted = evaluated + alignment.ambiguous_predicted + alignment.unmatched_predicted
    return AccuracyMetrics(
        support_expected=support_expected,
        support_predicted=support_predicted,
        evaluated=evaluated,
        correct=correct,
        ambiguous_expected=alignment.ambiguous_expected,
        ambiguous_predicted=alignment.ambiguous_predicted,
        unmatched_expected=alignment.unmatched_expected,
        unmatched_predicted=alignment.unmatched_predicted,
        accuracy=_ratio(
            correct,
            evaluated,
            empty_status=(
                MetricStatus.NOT_EVALUABLE
                if support_expected or support_predicted
                else MetricStatus.NOT_APPLICABLE
            ),
        ),
        alignment_coverage=_ratio(
            evaluated,
            support_expected,
            empty_status=MetricStatus.NOT_APPLICABLE,
        ),
    )


def _count_metrics(expected: Counter[_Signature], predicted: Counter[_Signature]) -> CountMetrics:
    true_positive = sum((expected & predicted).values())
    expected_total = sum(expected.values())
    predicted_total = sum(predicted.values())
    false_positive = predicted_total - true_positive
    false_negative = expected_total - true_positive
    return CountMetrics(
        expected=expected_total,
        predicted=predicted_total,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=_ratio(true_positive, predicted_total, empty_status=MetricStatus.NOT_APPLICABLE),
        recall=_ratio(true_positive, expected_total, empty_status=MetricStatus.NOT_APPLICABLE),
        f1=_ratio(
            2 * true_positive,
            expected_total + predicted_total,
            empty_status=MetricStatus.NOT_APPLICABLE,
        ),
        over_extraction=_ratio(
            false_positive, predicted_total, empty_status=MetricStatus.NOT_APPLICABLE
        ),
        under_extraction=_ratio(
            false_negative, expected_total, empty_status=MetricStatus.NOT_APPLICABLE
        ),
    )


def _ratio(
    numerator: int,
    denominator: int,
    *,
    empty_status: MetricStatus,
    partial: bool = False,
) -> RatioMetric:
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=(numerator / denominator if denominator else None),
        status=(MetricStatus.PARTIAL if denominator and partial else MetricStatus.OK)
        if denominator
        else empty_status,
    )


def _unmatched_ids(
    primary: Mapping[str, _Signature], reference: Mapping[str, _Signature]
) -> tuple[str, ...]:
    reference_counts = Counter(reference.values())
    by_signature: dict[_Signature, list[str]] = defaultdict(list)
    for item_id, signature in primary.items():
        by_signature[signature].append(item_id)
    unmatched: list[str] = []
    for signature in sorted(by_signature, key=repr):
        ids = sorted(by_signature[signature])
        matched = min(len(ids), reference_counts[signature])
        unmatched.extend(ids[matched:])
    return tuple(sorted(unmatched))


def _unmatched_record_ids(
    primary: Sequence[_AssertionRecord],
    reference: Sequence[_AssertionRecord],
    *,
    key: str,
) -> tuple[str, ...]:
    reference_counts = Counter(getattr(item, key) for item in reference)
    by_signature: dict[_Signature, list[str]] = defaultdict(list)
    for item in primary:
        by_signature[getattr(item, key)].append(item.id)
    unmatched: list[str] = []
    for signature in sorted(by_signature, key=repr):
        ids = sorted(by_signature[signature])
        matched = min(len(ids), reference_counts[signature])
        unmatched.extend(ids[matched:])
    return tuple(sorted(unmatched))


def _evidence_integrity_findings(
    source_document_key: str,
    proposal: ClauseEvaluationCandidate | None,
    *,
    source_resolver: FrozenSourceResolver | None,
) -> tuple[EvidenceIntegrityFinding, ...]:
    if proposal is None:
        return ()
    findings: list[EvidenceIntegrityFinding] = []
    owners = [
        *(("entity", item.id, anchor) for item in proposal.entities for anchor in item.evidence),
        *(
            ("assertion", item.id, anchor)
            for item in proposal.assertions
            for anchor in item.evidence
        ),
    ]
    for owner_kind, owner_id, anchor in owners:
        if source_resolver is None:
            status = EvidenceIntegrityStatus.UNAVAILABLE
            reason = "no frozen review source audit was supplied for integrity checking"
        else:
            resolution = source_resolver.resolve(
                source_document_key=source_document_key,
                anchor=anchor,
            )
            status = EvidenceIntegrityStatus(resolution.status.value)
            reason = resolution.reason
        findings.append(
            EvidenceIntegrityFinding(
                owner_kind=owner_kind,
                owner_id=owner_id,
                anchor_id=anchor.anchor_id,
                source_document_key=source_document_key,
                source_clause_id=anchor.source_clause_id,
                source_kind=anchor.source_kind,
                status=status,
                reason=reason,
            )
        )
    return tuple(findings)


def _evidence_integrity_metrics(
    findings: Sequence[EvidenceIntegrityFinding],
) -> EvidenceIntegrityMetrics:
    counts = Counter(item.status for item in findings)
    valid = counts[EvidenceIntegrityStatus.VALID]
    invalid = counts[EvidenceIntegrityStatus.INVALID]
    unavailable = counts[EvidenceIntegrityStatus.UNAVAILABLE]
    conflicting = counts[EvidenceIntegrityStatus.CONFLICTING]
    checked = valid + invalid
    total = len(findings)
    return EvidenceIntegrityMetrics(
        total=total,
        checked=checked,
        valid=valid,
        invalid=invalid,
        unavailable=unavailable,
        conflicting=conflicting,
        validity=_ratio(
            valid,
            checked,
            empty_status=(MetricStatus.NOT_EVALUABLE if total else MetricStatus.NOT_APPLICABLE),
            partial=bool(unavailable or conflicting),
        ),
    )


def _case_exact_match(
    *,
    proposal: ClauseEvaluationCandidate | None,
    golden_typed_entities: Mapping[str, _Signature],
    proposal_typed_entities: Mapping[str, _Signature],
    golden_assertions: Sequence[_AssertionRecord],
    proposal_assertions: Sequence[_AssertionRecord],
) -> CaseExactMatch:
    if proposal is None:
        return CaseExactMatch(value=None, status=CaseExactMatchStatus.MISSING_CANDIDATE)
    entities_equal = Counter(golden_typed_entities.values()) == Counter(
        proposal_typed_entities.values()
    )
    golden_full = Counter(
        (item.relation, item.normative_force, item.evidence) for item in golden_assertions
    )
    proposal_full = Counter(
        (item.relation, item.normative_force, item.evidence) for item in proposal_assertions
    )
    exact = entities_equal and golden_full == proposal_full
    return CaseExactMatch(
        value=exact,
        status=CaseExactMatchStatus.EXACT if exact else CaseExactMatchStatus.MISMATCH,
    )


def _sum_count_metrics(metrics: Iterable[CountMetrics]) -> CountMetrics:
    items = tuple(metrics)
    expected = sum(item.expected for item in items)
    predicted = sum(item.predicted for item in items)
    true_positive = sum(item.true_positive for item in items)
    false_positive = predicted - true_positive
    false_negative = expected - true_positive
    return CountMetrics(
        expected=expected,
        predicted=predicted,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=_ratio(true_positive, predicted, empty_status=MetricStatus.NOT_APPLICABLE),
        recall=_ratio(true_positive, expected, empty_status=MetricStatus.NOT_APPLICABLE),
        f1=_ratio(
            2 * true_positive,
            expected + predicted,
            empty_status=MetricStatus.NOT_APPLICABLE,
        ),
        over_extraction=_ratio(false_positive, predicted, empty_status=MetricStatus.NOT_APPLICABLE),
        under_extraction=_ratio(false_negative, expected, empty_status=MetricStatus.NOT_APPLICABLE),
    )


def _sum_accuracy(metrics: Iterable[AccuracyMetrics]) -> AccuracyMetrics:
    items = tuple(metrics)
    support_expected = sum(item.support_expected for item in items)
    support_predicted = sum(item.support_predicted for item in items)
    evaluated = sum(item.evaluated for item in items)
    correct = sum(item.correct for item in items)
    ambiguous_expected = sum(item.ambiguous_expected for item in items)
    ambiguous_predicted = sum(item.ambiguous_predicted for item in items)
    unmatched_expected = sum(item.unmatched_expected for item in items)
    unmatched_predicted = sum(item.unmatched_predicted for item in items)
    return AccuracyMetrics(
        support_expected=support_expected,
        support_predicted=support_predicted,
        evaluated=evaluated,
        correct=correct,
        ambiguous_expected=ambiguous_expected,
        ambiguous_predicted=ambiguous_predicted,
        unmatched_expected=unmatched_expected,
        unmatched_predicted=unmatched_predicted,
        accuracy=_ratio(
            correct,
            evaluated,
            empty_status=(
                MetricStatus.NOT_EVALUABLE
                if support_expected or support_predicted
                else MetricStatus.NOT_APPLICABLE
            ),
        ),
        alignment_coverage=_ratio(
            evaluated,
            support_expected,
            empty_status=MetricStatus.NOT_APPLICABLE,
        ),
    )


def _sum_evidence_integrity(
    metrics: Iterable[EvidenceIntegrityMetrics],
) -> EvidenceIntegrityMetrics:
    items = tuple(metrics)
    total = sum(item.total for item in items)
    checked = sum(item.checked for item in items)
    valid = sum(item.valid for item in items)
    invalid = sum(item.invalid for item in items)
    unavailable = sum(item.unavailable for item in items)
    conflicting = sum(item.conflicting for item in items)
    return EvidenceIntegrityMetrics(
        total=total,
        checked=checked,
        valid=valid,
        invalid=invalid,
        unavailable=unavailable,
        conflicting=conflicting,
        validity=_ratio(
            valid,
            checked,
            empty_status=(MetricStatus.NOT_EVALUABLE if total else MetricStatus.NOT_APPLICABLE),
            partial=bool(unavailable or conflicting),
        ),
    )


def _aggregate_clause_exact_match(
    reports: Sequence[AssertionQualificationCaseReport],
) -> ClauseExactMatchAggregate:
    cases = len(reports)
    candidate_cases = sum(item.candidate_status == "present" for item in reports)
    matched = sum(item.clause_exact_match.value is True for item in reports)
    missing = cases - candidate_cases
    return ClauseExactMatchAggregate(
        cases=cases,
        candidate_cases=candidate_cases,
        matched=matched,
        missing_candidates=missing,
        accuracy=_ratio(matched, cases, empty_status=MetricStatus.NOT_APPLICABLE),
    )
