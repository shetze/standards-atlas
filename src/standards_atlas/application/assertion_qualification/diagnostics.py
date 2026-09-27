"""Conservative, deterministic AP01 diagnostics layered over strict comparison results."""

from __future__ import annotations

import re
from collections.abc import Sequence

from standards_atlas.application.formal_semantics import FormalClassHierarchy
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE

from .models import (
    AssertionDiagnosticCode,
    AssertionDiagnosticOrigin,
    AssertionDiagnosticStatus,
    AssertionGoldenCase,
    AssertionQualificationFinding,
    ComparisonAlignmentRecord,
    ComparisonAlignmentStatus,
    EvidenceIntegrityFinding,
    EvidenceIntegrityStatus,
)
from .projection import ClauseEvaluationCandidate

_WORK_PRODUCT = f"{FORMAL_SEMANTIC_NAMESPACE}WorkProduct"


def build_diagnostic_findings(
    *,
    golden: AssertionGoldenCase,
    proposal: ClauseEvaluationCandidate | None,
    hierarchy: FormalClassHierarchy,
    entity_alignment: Sequence[ComparisonAlignmentRecord],
    endpoint_alignment: Sequence[ComparisonAlignmentRecord],
    relation_alignment: Sequence[ComparisonAlignmentRecord],
    evidence_findings: Sequence[EvidenceIntegrityFinding],
) -> tuple[AssertionQualificationFinding, ...]:
    """Describe observable differences without upgrading ambiguity to semantic fact."""
    findings: list[AssertionQualificationFinding] = []
    golden_entities = {item.id: item for item in golden.entities}
    proposal_entities = (
        {item.id: item for item in proposal.entities} if proposal is not None else {}
    )
    golden_assertions = {item.id: item for item in golden.assertions}
    proposal_assertions = (
        {item.id: item for item in proposal.assertions} if proposal is not None else {}
    )

    for alignment in entity_alignment:
        if alignment.status is ComparisonAlignmentStatus.MATCHED:
            golden_id = alignment.golden_ids[0]
            candidate_id = alignment.candidate_ids[0]
            expected = golden_entities[golden_id]
            actual = proposal_entities[candidate_id]
            if expected.class_iri != actual.class_iri:
                findings.append(
                    _finding(
                        golden,
                        codes=(AssertionDiagnosticCode.WRONG_ENTITY_CLASS,),
                        golden_ids=(golden_id,),
                        candidate_ids=(candidate_id,),
                        observed=(
                            f"entity class differs: expected {expected.class_iri!r}, "
                            f"candidate {actual.class_iri!r}"
                        ),
                        rule="unique normalized-label identity with unequal concrete class",
                        status=AssertionDiagnosticStatus.RULE_BASED,
                    )
                )
        elif alignment.status is ComparisonAlignmentStatus.EXPECTED_ONLY:
            for golden_id in alignment.golden_ids:
                expected = golden_entities[golden_id]
                family_note = (
                    " (golden entity is in the WorkProduct family)"
                    if hierarchy.is_ancestor_or_same(_WORK_PRODUCT, expected.class_iri)
                    else ""
                )
                findings.append(
                    _finding(
                        golden,
                        codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                        golden_ids=(golden_id,),
                        observed=(
                            "golden entity has no strict normalized-label candidate match"
                            + family_note
                        ),
                        rule=(
                            "strict entity identity mismatch does not prove semantic absence; "
                            "fachliche review required"
                        ),
                        status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                    )
                )
        elif alignment.status is ComparisonAlignmentStatus.CANDIDATE_ONLY:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                    candidate_ids=alignment.candidate_ids,
                    observed="candidate entity has no strict normalized-label golden match",
                    rule="extra strict entity identity is not automatically over-extraction",
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )
        elif alignment.status is ComparisonAlignmentStatus.AMBIGUOUS:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                    golden_ids=alignment.golden_ids,
                    candidate_ids=alignment.candidate_ids,
                    observed="entity identity is ambiguous under the strict comparison rule",
                    rule="ambiguous strict identity requires fachliche review",
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )

    for alignment in endpoint_alignment:
        if alignment.status is ComparisonAlignmentStatus.MATCHED:
            golden_id = alignment.golden_ids[0]
            candidate_id = alignment.candidate_ids[0]
            expected = golden_assertions[golden_id]
            actual = proposal_assertions[candidate_id]
            if expected.predicate != actual.predicate:
                findings.append(
                    _finding(
                        golden,
                        codes=(AssertionDiagnosticCode.WRONG_PREDICATE,),
                        golden_ids=(golden_id,),
                        candidate_ids=(candidate_id,),
                        observed=(
                            f"predicate differs: expected {expected.predicate!r}, "
                            f"candidate {actual.predicate!r}"
                        ),
                        rule="unique directed endpoint identity with unequal predicate",
                        status=AssertionDiagnosticStatus.RULE_BASED,
                    )
                )
        elif alignment.status is ComparisonAlignmentStatus.EXPECTED_ONLY:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                    golden_ids=alignment.golden_ids,
                    observed="golden assertion endpoints have no strict candidate endpoint match",
                    rule=(
                        "strict endpoint mismatch does not prove semantic assertion absence; "
                        "fachliche review required"
                    ),
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )
        elif alignment.status is ComparisonAlignmentStatus.CANDIDATE_ONLY:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                    candidate_ids=alignment.candidate_ids,
                    observed="candidate assertion endpoints have no strict golden endpoint match",
                    rule="additional assertion is not automatically invented",
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )
        elif alignment.status is ComparisonAlignmentStatus.AMBIGUOUS:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH,),
                    golden_ids=alignment.golden_ids,
                    candidate_ids=alignment.candidate_ids,
                    observed="assertion endpoint identity is ambiguous under the strict rule",
                    rule="ambiguous endpoint identity requires fachliche review",
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )

    for alignment in relation_alignment:
        if alignment.status is not ComparisonAlignmentStatus.MATCHED:
            continue
        golden_id = alignment.golden_ids[0]
        candidate_id = alignment.candidate_ids[0]
        expected = golden_assertions[golden_id]
        actual = proposal_assertions[candidate_id]
        if expected.normative_force != actual.normative_force:
            findings.append(
                _finding(
                    golden,
                    codes=(AssertionDiagnosticCode.WRONG_NORMATIVE_FORCE,),
                    golden_ids=(golden_id,),
                    candidate_ids=(candidate_id,),
                    observed=(
                        f"normative force differs: expected {expected.normative_force.value!r}, "
                        f"candidate {actual.normative_force.value!r}"
                    ),
                    rule="unique strict relation identity with unequal normative force",
                    status=AssertionDiagnosticStatus.RULE_BASED,
                )
            )

    for evidence in evidence_findings:
        if evidence.status not in {
            EvidenceIntegrityStatus.INVALID,
            EvidenceIntegrityStatus.CONFLICTING,
        }:
            continue
        findings.append(
            _finding(
                golden,
                codes=(AssertionDiagnosticCode.GROUNDING_FAILURE,),
                candidate_ids=(evidence.owner_id,),
                observed=f"evidence {evidence.anchor_id}: {evidence.reason}",
                rule=f"technical frozen-source resolution status={evidence.status.value}",
                origin=AssertionDiagnosticOrigin.EVIDENCE_INTEGRITY,
                status=(
                    AssertionDiagnosticStatus.RULE_BASED
                    if evidence.status is EvidenceIntegrityStatus.INVALID
                    else AssertionDiagnosticStatus.NEEDS_REVIEW
                ),
            )
        )

    if proposal is not None:
        for index, message in enumerate(proposal.violations):
            codes = _suggested_codes(message)
            if not codes:
                continue
            findings.append(
                _finding(
                    golden,
                    codes=codes,
                    violation_reference=f"violation[{index}]",
                    observed=message,
                    rule="retained proposal diagnostic keyword mapping; not human-confirmed",
                    origin=AssertionDiagnosticOrigin.PROPOSAL_DIAGNOSTIC,
                    status=AssertionDiagnosticStatus.NEEDS_REVIEW,
                )
            )

    return tuple(findings)


def _suggested_codes(message: str) -> tuple[AssertionDiagnosticCode, ...]:
    text = re.sub(r"\s+", " ", message.casefold())
    codes: list[AssertionDiagnosticCode] = []
    mappings = (
        (
            ("missing work product", "missing work-product"),
            AssertionDiagnosticCode.MISSING_WORK_PRODUCT,
        ),
        (
            ("over-extract", "over extract", "overly detailed"),
            AssertionDiagnosticCode.OVER_EXTRACTED_DETAIL,
        ),
        (("note over", "note-over"), AssertionDiagnosticCode.NOTE_OVER_EXTRACTION),
        (("list over", "over-atom", "over atom"), AssertionDiagnosticCode.LIST_OVER_ATOMIZATION),
        (("missing assertion",), AssertionDiagnosticCode.MISSING_ASSERTION),
        (("invented assertion",), AssertionDiagnosticCode.INVENTED_ASSERTION),
        (("wrong predicate",), AssertionDiagnosticCode.WRONG_PREDICATE),
        (("wrong normative force",), AssertionDiagnosticCode.WRONG_NORMATIVE_FORCE),
        (("wrong context", "context misuse"), AssertionDiagnosticCode.WRONG_CONTEXT_USE),
        (("grounding failure",), AssertionDiagnosticCode.GROUNDING_FAILURE),
        (
            ("conditional", "condition loss", "unless", "only if"),
            AssertionDiagnosticCode.CONDITIONAL_SEMANTICS_LOSS,
        ),
    )
    for needles, code in mappings:
        if any(needle in text for needle in needles):
            codes.append(code)
    return tuple(codes)


def _finding(
    case: AssertionGoldenCase,
    *,
    codes: tuple[AssertionDiagnosticCode, ...],
    observed: str,
    rule: str,
    status: AssertionDiagnosticStatus,
    origin: AssertionDiagnosticOrigin = AssertionDiagnosticOrigin.STRICT_COMPARISON,
    golden_ids: tuple[str, ...] = (),
    candidate_ids: tuple[str, ...] = (),
    violation_reference: str | None = None,
) -> AssertionQualificationFinding:
    return AssertionQualificationFinding(
        source_document_key=case.source_document_key,
        clause_id=case.clause_id,
        codes=codes,
        golden_ids=golden_ids,
        candidate_ids=candidate_ids,
        violation_reference=violation_reference,
        observed_difference=observed,
        rule=rule,
        origin=origin,
        status=status,
    )
