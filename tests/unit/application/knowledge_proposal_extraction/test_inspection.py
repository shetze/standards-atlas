import json

from standards_atlas.application.context import ContextSelectionProfile
from standards_atlas.application.knowledge_proposal_extraction import (
    EvidenceContribution,
    EvidenceGroundingOwnerKind,
    EvidenceGroundingRequest,
    EvidenceUse,
    assertion_context_source_package,
    inspect_context_evidence,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EvidenceSourceKind,
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
    ReferenceTarget,
    StandardReference,
    TextBlock,
)


def _clause(
    clause_id: str,
    reference: str,
    heading: str | None,
    *,
    parent: str | None = None,
    text: str = "",
    mentions: tuple[ReferenceMention, ...] = (),
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="AP02-SYNTH", year=2026, clause=reference),
        clause_type=ClauseType.REQUIREMENT,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"text:{clause_id}", text=text),) if text else (),
        reference_mentions=mentions,
    )


def _document() -> EngineeringDocument:
    parent = _clause("parent", "5", "Safety plan confirmation review")
    intro = _clause(
        "intro",
        "5.1",
        "Purpose",
        parent="parent",
        text="The review checks whether the safety plan is adequate.",
    )
    target = _clause(
        "target",
        "5.2",
        "Evaluation activities",
        parent="parent",
        text="The evaluation shall assess the verification criteria and record the result.",
    )
    later = _clause(
        "later",
        "5.3",
        "Exception",
        parent="parent",
        text="For test-only prototypes, the record requirement does not apply to clause 5.2.",
        mentions=(
            ReferenceMention(
                kind=ReferenceMentionKind.CLAUSE,
                surface_text="5.2",
                start_offset=74,
                end_offset=77,
                reference="5.2",
                status=ReferenceResolutionStatus.RESOLVED,
                targets=(ReferenceTarget(clause_id="target", reference="5.2"),),
            ),
        ),
    )
    return EngineeringDocument(
        key=DocumentKey(value="AP02-SYNTH"),
        title="Synthetic AP02 reference document",
        document_type=DocumentType.STANDARD,
        clauses=(parent, intro, target, later),
    )


def _surface_ref(package, clause_id: str, kind: EvidenceSourceKind) -> str:
    return next(
        item.package_source_ref
        for item in package.input_surfaces
        if item.source_ref.clause_id == clause_id and item.source_ref.source_kind is kind
    )


def test_inspection_reports_selection_fingerprints_and_separate_grounding_without_source_text() -> (
    None
):
    document = _document()
    target = next(item for item in document.clauses if item.id.value == "target")
    profile = ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8)
    package = assertion_context_source_package(document, target, profile=profile)
    parent_ref = _surface_ref(package, "parent", EvidenceSourceKind.HEADING)
    target_ref = _surface_ref(package, "target", EvidenceSourceKind.BODY)
    later_ref = _surface_ref(package, "later", EvidenceSourceKind.BODY)
    requests = (
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ENTITY,
            owner_id="review-activity",
            evidence=(
                EvidenceUse(
                    source_ref=parent_ref,
                    exact_quote="Safety plan confirmation review",
                    contribution=EvidenceContribution.SUBJECT_FRAME,
                ),
            ),
        ),
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="assessment",
            evidence=(
                EvidenceUse(
                    source_ref=target_ref,
                    exact_quote="shall assess the verification criteria",
                ),
                EvidenceUse(
                    source_ref=later_ref,
                    exact_quote="does not apply to clause 5.2",
                    contribution=EvidenceContribution.CONDITION_OR_EXCEPTION,
                ),
            ),
        ),
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="bad-span",
            evidence=(
                EvidenceUse(source_ref=target_ref, exact_quote="not in the delivered source"),
            ),
        ),
    )

    report = inspect_context_evidence(
        document,
        target,
        profile=profile,
        grounding_requests=requests,
    )

    assert report.model_execution is False
    assert report.semantic_quality_assessed is False
    assert report.selection_completeness == "bounded"
    assert report.budget["used_chars"] > 0
    assert report.package_sha256.startswith("sha256:")
    assert set(report.fingerprints) == {
        "source_state_sha256",
        "candidate_space_sha256",
        "selection_decision_sha256",
        "actual_input_sha256",
    }
    assert any(item["clause_id"] == "parent" for item in report.selected_sources)
    assert any(item["clause_id"] == "later" for item in report.selected_sources)
    assert [item.complete for item in report.grounding_results] == [True, True, False]
    assert len(report.grounding_results[1].anchors) == 2
    assert report.grounding_results[2].failures[0].code.value == "quote_not_found"

    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert "The evaluation shall assess" not in payload
    assert "For test-only prototypes" not in payload
    assert "not in the delivered source" not in payload


def test_inspection_is_deterministic_for_same_document_profile_and_requests() -> None:
    document = _document()
    target = next(item for item in document.clauses if item.id.value == "target")
    profile = ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8)

    first = inspect_context_evidence(document, target, profile=profile)
    second = inspect_context_evidence(document, target, profile=profile)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
