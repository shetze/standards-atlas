"""Deterministic entity, assertion, normative-force and grounding matching for Slice 7A."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from standards_atlas.application.assertion_qualification.models import (
    AccuracyMetrics,
    AssertionGoldenCase,
    AssertionQualificationCaseReport,
    CountMetrics,
    GoldenEvidenceSpan,
    GoldenNormativeAssertion,
)
from standards_atlas.domain.model import (
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    LiteralAssertionObject,
    NormativeAssertionProposal,
)

_Signature = tuple[Hashable, ...]


@dataclass(frozen=True)
class _AssertionRecord:
    id: str
    endpoint: _Signature
    relation: _Signature
    normative_force: str
    grounding: _Signature


@dataclass(frozen=True)
class CaseMatchResult:
    report: AssertionQualificationCaseReport


def evaluate_case(
    golden: AssertionGoldenCase,
    proposal: DocumentKnowledgeProposal | None,
    *,
    proposal_hash: str | None,
) -> CaseMatchResult:
    golden_entities = {entity.id: entity for entity in golden.entities}
    proposal_entities = (
        {entity.id: entity for entity in proposal.entity_proposals} if proposal is not None else {}
    )

    golden_entity_signatures = {
        entity_id: _entity_signature(entity.normalized_label, entity.class_iri)
        for entity_id, entity in golden_entities.items()
    }
    proposal_entity_signatures = {
        entity_id: _entity_signature(entity.normalized_label, entity.class_iri)
        for entity_id, entity in proposal_entities.items()
    }

    entity_metrics = _count_metrics(
        Counter(golden_entity_signatures.values()),
        Counter(proposal_entity_signatures.values()),
    )
    entity_fp = _unmatched_ids(proposal_entity_signatures, golden_entity_signatures)
    entity_fn = _unmatched_ids(golden_entity_signatures, proposal_entity_signatures)

    golden_assertions = tuple(
        _golden_assertion_record(assertion, golden_entity_signatures)
        for assertion in golden.assertions
    )
    proposal_assertions = tuple(
        _proposal_assertion_record(
            assertion,
            proposal_entity_signatures,
            proposal.evidence_anchors,
        )
        for assertion in (proposal.assertion_proposals if proposal is not None else ())
    )

    golden_relation_counts = Counter(item.relation for item in golden_assertions)
    proposal_relation_counts = Counter(item.relation for item in proposal_assertions)
    assertion_metrics = _count_metrics(golden_relation_counts, proposal_relation_counts)
    assertion_fp = _unmatched_record_ids(proposal_assertions, golden_assertions, key="relation")
    assertion_fn = _unmatched_record_ids(golden_assertions, proposal_assertions, key="relation")

    predicate_accuracy = _bucket_accuracy(
        golden_assertions,
        proposal_assertions,
        bucket="endpoint",
        value=lambda item: item.relation[-1],
    )
    normative_force_accuracy = _bucket_accuracy(
        golden_assertions,
        proposal_assertions,
        bucket="relation",
        value=lambda item: item.normative_force,
    )
    grounding_accuracy = _bucket_accuracy(
        golden_assertions,
        proposal_assertions,
        bucket="relation",
        value=lambda item: item.grounding,
    )
    exact_assertion_accuracy = _bucket_accuracy(
        golden_assertions,
        proposal_assertions,
        bucket="relation",
        value=lambda item: (item.normative_force, item.grounding),
    )

    return CaseMatchResult(
        report=AssertionQualificationCaseReport(
            source_document_key=golden.source_document_key,
            proposal_run_id=proposal.proposal_run_id if proposal is not None else None,
            proposal_hash=proposal_hash,
            entities=entity_metrics,
            assertions=assertion_metrics,
            predicate_accuracy=predicate_accuracy,
            normative_force_accuracy=normative_force_accuracy,
            grounding_accuracy=grounding_accuracy,
            exact_assertion_accuracy=exact_assertion_accuracy,
            entity_false_positive_ids=entity_fp,
            entity_false_negative_ids=entity_fn,
            assertion_false_positive_ids=assertion_fp,
            assertion_false_negative_ids=assertion_fn,
            proposal_violations=len(proposal.violations) if proposal is not None else 0,
            proposal_failures=len(proposal.failures) if proposal is not None else 0,
        )
    )


def aggregate_case_reports(
    reports: Sequence[AssertionQualificationCaseReport],
):
    from standards_atlas.application.assertion_qualification.models import (
        AssertionQualificationAggregate,
    )

    return AssertionQualificationAggregate(
        documents=len(reports),
        entities=_sum_count_metrics(report.entities for report in reports),
        assertions=_sum_count_metrics(report.assertions for report in reports),
        predicate_accuracy=_sum_accuracy(report.predicate_accuracy for report in reports),
        normative_force_accuracy=_sum_accuracy(
            report.normative_force_accuracy for report in reports
        ),
        grounding_accuracy=_sum_accuracy(report.grounding_accuracy for report in reports),
        exact_assertion_accuracy=_sum_accuracy(
            report.exact_assertion_accuracy for report in reports
        ),
    )


def _entity_signature(normalized_label: str, class_iri: str) -> _Signature:
    normalized = unicodedata.normalize("NFKC", normalized_label).strip().casefold()
    label = re.sub(r"\s+", " ", normalized)
    return (label, class_iri)


def _golden_assertion_record(
    assertion: GoldenNormativeAssertion,
    entity_signatures: Mapping[str, _Signature],
) -> _AssertionRecord:
    endpoint = _assertion_endpoint(
        source_clause_id=assertion.source_clause_id.value,
        subject=entity_signatures[assertion.subject_id],
        object_=_object_signature(assertion.object, entity_signatures),
    )
    relation = (*endpoint, assertion.predicate)
    return _AssertionRecord(
        id=assertion.id,
        endpoint=endpoint,
        relation=relation,
        normative_force=assertion.normative_force.value,
        grounding=_golden_grounding_signature(assertion.evidence),
    )


def _proposal_assertion_record(
    assertion: NormativeAssertionProposal,
    entity_signatures: Mapping[str, _Signature],
    anchors: Sequence[EvidenceAnchor],
) -> _AssertionRecord:
    anchor_by_id = {anchor.id: anchor for anchor in anchors}
    endpoint = _assertion_endpoint(
        source_clause_id=assertion.source_clause_id.value,
        subject=entity_signatures[assertion.subject_id],
        object_=_object_signature(assertion.object, entity_signatures),
    )
    relation = (*endpoint, assertion.predicate)
    return _AssertionRecord(
        id=assertion.id,
        endpoint=endpoint,
        relation=relation,
        normative_force=assertion.normative_force.value,
        grounding=tuple(
            sorted(
                _evidence_anchor_signature(anchor_by_id[anchor_id])
                for anchor_id in assertion.evidence_anchor_ids
            )
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
        return ("entity", entity_signatures[object_.entity_id])
    payload = json.dumps(
        object_.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ("literal", payload)


def _golden_grounding_signature(spans: Sequence[GoldenEvidenceSpan]) -> _Signature:
    return tuple(
        sorted(
            (
                span.clause_id.value,
                span.start_offset,
                span.end_offset,
                span.content_hash,
            )
            for span in spans
        )
    )


def _evidence_anchor_signature(anchor: EvidenceAnchor) -> tuple[Hashable, ...]:
    return (
        anchor.clause_id.value,
        anchor.start_offset,
        anchor.end_offset,
        anchor.content_hash,
    )


def _count_metrics(expected: Counter[_Signature], predicted: Counter[_Signature]) -> CountMetrics:
    true_positive = sum((expected & predicted).values())
    expected_total = sum(expected.values())
    predicted_total = sum(predicted.values())
    false_positive = predicted_total - true_positive
    false_negative = expected_total - true_positive
    precision = true_positive / predicted_total if predicted_total else float(expected_total == 0)
    recall = true_positive / expected_total if expected_total else float(predicted_total == 0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CountMetrics(
        expected=expected_total,
        predicted=predicted_total,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
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


def _bucket_accuracy(
    expected: Sequence[_AssertionRecord],
    predicted: Sequence[_AssertionRecord],
    *,
    bucket: str,
    value,
) -> AccuracyMetrics:
    expected_buckets: dict[_Signature, list[_AssertionRecord]] = defaultdict(list)
    predicted_buckets: dict[_Signature, list[_AssertionRecord]] = defaultdict(list)
    for item in expected:
        expected_buckets[getattr(item, bucket)].append(item)
    for item in predicted:
        predicted_buckets[getattr(item, bucket)].append(item)

    evaluated = 0
    correct = 0
    for signature in set(expected_buckets) | set(predicted_buckets):
        expected_items = expected_buckets.get(signature, ())
        predicted_items = predicted_buckets.get(signature, ())
        aligned = min(len(expected_items), len(predicted_items))
        evaluated += aligned
        if not aligned:
            continue
        expected_values = Counter(value(item) for item in expected_items)
        predicted_values = Counter(value(item) for item in predicted_items)
        correct += min(aligned, sum((expected_values & predicted_values).values()))
    return AccuracyMetrics(
        evaluated=evaluated,
        correct=correct,
        accuracy=(correct / evaluated if evaluated else None),
    )


def _sum_count_metrics(metrics: Iterable[CountMetrics]) -> CountMetrics:
    items = tuple(metrics)
    expected = sum(item.expected for item in items)
    predicted = sum(item.predicted for item in items)
    true_positive = sum(item.true_positive for item in items)
    false_positive = sum(item.false_positive for item in items)
    false_negative = sum(item.false_negative for item in items)
    precision = true_positive / predicted if predicted else float(expected == 0)
    recall = true_positive / expected if expected else float(predicted == 0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CountMetrics(
        expected=expected,
        predicted=predicted,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _sum_accuracy(metrics: Iterable[AccuracyMetrics]) -> AccuracyMetrics:
    items = tuple(metrics)
    evaluated = sum(item.evaluated for item in items)
    correct = sum(item.correct for item in items)
    return AccuracyMetrics(
        evaluated=evaluated,
        correct=correct,
        accuracy=(correct / evaluated if evaluated else None),
    )
