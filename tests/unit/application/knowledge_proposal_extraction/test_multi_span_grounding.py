import pytest

from standards_atlas.application.context import (
    ContextSelectionProfile,
    SourceSurfaceResolver,
    build_context_source_package,
    build_structured_context_candidates,
    select_structured_context,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    CanonicalOffsetSelector,
    EvidenceContribution,
    EvidenceGroundingFailureCode,
    EvidenceGroundingOwnerKind,
    EvidenceGroundingRequest,
    EvidenceUse,
    QuoteOccurrenceSelector,
    ground_evidence_request,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EvidenceSourceKind,
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
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="TEST", clause=reference),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"{clause_id}-text", text=text),) if text else (),
    )


def _document(*clauses: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def _package(document: EngineeringDocument, target_id: str, *, excerpt=None):
    target = next(clause for clause in document.clauses if clause.id.value == target_id)
    inventory = build_structured_context_candidates(document, target)
    if excerpt is not None:
        start, end = excerpt
        body = next(
            candidate
            for candidate in inventory.candidates
            if candidate.source_ref.clause_id == target_id
            and candidate.source_ref.source_kind is EvidenceSourceKind.BODY
        )
        resolution = SourceSurfaceResolver((document,)).resolve(
            body.source_ref, start_offset=start, end_offset=end
        )
        inventory = inventory.model_copy(
            update={
                "candidates": tuple(
                    candidate.model_copy(update={"resolution": resolution})
                    if candidate.candidate_id == body.candidate_id
                    else candidate
                    for candidate in inventory.candidates
                )
            }
        )
    selection = select_structured_context(
        inventory,
        profile=ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8),
    )
    return build_context_source_package(document, inventory, selection)


def _source_ref(package, clause_id: str, source_kind: EvidenceSourceKind) -> str:
    return next(
        surface.package_source_ref
        for surface in package.input_surfaces
        if surface.source_ref.clause_id == clause_id
        and surface.source_ref.source_kind is source_kind
    )


@pytest.mark.parametrize(
    "owner_kind",
    [EvidenceGroundingOwnerKind.ENTITY, EvidenceGroundingOwnerKind.ASSERTION],
)
def test_common_grounding_core_supports_heading_body_and_foreign_context(owner_kind) -> None:
    parent = _clause("parent", "5", "Safety plan confirmation review")
    target = _clause(
        "target",
        "5.1",
        "Evaluation",
        parent="parent",
        text="The evaluation shall assess the plan.",
    )
    package = _package(_document(parent, target), "target")
    request = EvidenceGroundingRequest(
        owner_kind=owner_kind,
        owner_id="item-1",
        evidence=(
            EvidenceUse(
                source_ref=_source_ref(package, "parent", EvidenceSourceKind.HEADING),
                exact_quote="Safety plan confirmation review",
                contribution=EvidenceContribution.SUBJECT_FRAME,
            ),
            EvidenceUse(
                source_ref=_source_ref(package, "target", EvidenceSourceKind.BODY),
                exact_quote="evaluation shall assess the plan",
                contribution=EvidenceContribution.DIRECT_STATEMENT,
            ),
        ),
    )

    result = ground_evidence_request(package, request)

    assert result.complete
    assert len(result.anchors) == 2
    assert {anchor.source_clause_id.value for anchor in result.anchors} == {"parent", "target"}
    assert all(item.semantic_status == "unassessed" for item in result.grounded_uses)


def test_repeated_quote_requires_and_validates_selector() -> None:
    text = "Repeat then Repeat then Repeat."
    target = _clause("target", "1", "Target", text=text)
    package = _package(_document(target), "target")
    source_ref = _source_ref(package, "target", EvidenceSourceKind.BODY)

    ambiguous = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(EvidenceUse(source_ref=source_ref, exact_quote="Repeat"),),
        ),
    )
    selected = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="Repeat",
                    selector=QuoteOccurrenceSelector(occurrence_index=1),
                ),
            ),
        ),
    )

    assert not ambiguous.complete
    assert ambiguous.failures[0].code is EvidenceGroundingFailureCode.AMBIGUOUS_QUOTE
    assert selected.complete
    assert selected.anchors[0].start_offset == text.index("Repeat", text.index("Repeat") + 1)


def test_declared_source_never_silently_switches_to_another_surface() -> None:
    target = _clause("target", "1", "Target", text="No matching evidence here.")
    sibling = _clause("sibling", "2", "Sibling", text="Exact evidence is here.")
    # Give both clauses the same parent so the sibling is a selected sequential source.
    parent = _clause("parent", "0", "Group")
    target = target.model_copy(
        update={"baseline": target.baseline.model_copy(update={"parent_id": parent.id})}
    )
    sibling = sibling.model_copy(
        update={"baseline": sibling.baseline.model_copy(update={"parent_id": parent.id})}
    )
    package = _package(_document(parent, target, sibling), "target")

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ENTITY,
            owner_id="e1",
            evidence=(
                EvidenceUse(
                    source_ref=_source_ref(package, "target", EvidenceSourceKind.BODY),
                    exact_quote="Exact evidence is here",
                ),
            ),
        ),
    )

    assert not result.complete
    assert result.failures[0].code is EvidenceGroundingFailureCode.QUOTE_NOT_FOUND
    assert result.anchors == ()


def test_excerpt_grounding_projects_unicode_crlf_to_canonical_character_offsets() -> None:
    text = "outside α😀\r\ninside α😀\r\nend"
    target = _clause("target", "1", "Target", text=text)
    start = text.index("inside")
    end = text.index("end")
    package = _package(_document(target), "target", excerpt=(start, end))
    source_ref = _source_ref(package, "target", EvidenceSourceKind.BODY)

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ENTITY,
            owner_id="e1",
            evidence=(EvidenceUse(source_ref=source_ref, exact_quote="α😀"),),
        ),
    )

    assert result.complete
    assert result.anchors[0].start_offset == text.index("α😀", start)
    assert result.anchors[0].end_offset == text.index("α😀", start) + len("α😀")


def test_canonical_offset_selector_must_match_quote_and_delivered_excerpt() -> None:
    text = "prefix selected text suffix"
    target = _clause("target", "1", "Target", text=text)
    start = text.index("selected")
    end = start + len("selected text")
    package = _package(_document(target), "target", excerpt=(start, end))
    source_ref = _source_ref(package, "target", EvidenceSourceKind.BODY)

    valid = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="selected",
                    selector=CanonicalOffsetSelector(
                        start_offset=start,
                        end_offset=start + len("selected"),
                    ),
                ),
            ),
        ),
    )
    mismatch = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="text",
                    selector=CanonicalOffsetSelector(
                        start_offset=start,
                        end_offset=start + len("selected"),
                    ),
                ),
            ),
        ),
    )
    outside = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="prefix",
                    selector=CanonicalOffsetSelector(start_offset=0, end_offset=len("prefix")),
                ),
            ),
        ),
    )

    assert valid.complete
    assert valid.anchors[0].start_offset == start
    assert mismatch.failures[0].code is EvidenceGroundingFailureCode.SELECTOR_MISMATCH
    assert (
        outside.failures[0].code is EvidenceGroundingFailureCode.OFFSETS_OUTSIDE_DELIVERED_EXCERPT
    )


def test_quote_in_document_but_outside_delivered_excerpt_does_not_ground() -> None:
    text = "outside evidence -- delivered evidence"
    target = _clause("target", "1", "Target", text=text)
    start = text.index("delivered")
    package = _package(_document(target), "target", excerpt=(start, len(text)))

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ENTITY,
            owner_id="e1",
            evidence=(
                EvidenceUse(
                    source_ref=_source_ref(package, "target", EvidenceSourceKind.BODY),
                    exact_quote="outside evidence",
                ),
            ),
        ),
    )

    assert not result.complete
    assert result.failures[0].code is EvidenceGroundingFailureCode.QUOTE_NOT_FOUND


def test_failed_required_span_keeps_result_incomplete_instead_of_silent_partial_success() -> None:
    target = _clause("target", "1", "Target", text="First span. Second span.")
    package = _package(_document(target), "target")
    source_ref = _source_ref(package, "target", EvidenceSourceKind.BODY)

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(source_ref=source_ref, exact_quote="First span"),
                EvidenceUse(source_ref=source_ref, exact_quote="missing span"),
            ),
        ),
    )

    assert not result.complete
    assert len(result.anchors) == 1
    assert len(result.grounded_uses) == 1
    assert result.failures[0].use_index == 1
    assert result.failures[0].code is EvidenceGroundingFailureCode.QUOTE_NOT_FOUND


def test_same_anchor_can_have_distinct_use_contributions_without_changing_anchor_identity() -> None:
    target = _clause("target", "1", "Target", text="Shared evidence.")
    package = _package(_document(target), "target")
    source_ref = _source_ref(package, "target", EvidenceSourceKind.BODY)

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
            owner_id="a1",
            evidence=(
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="Shared evidence",
                    contribution=EvidenceContribution.SUBJECT_FRAME,
                ),
                EvidenceUse(
                    source_ref=source_ref,
                    exact_quote="Shared evidence",
                    contribution=EvidenceContribution.CONDITION_OR_EXCEPTION,
                ),
            ),
        ),
    )

    assert result.complete
    assert len(result.anchors) == 1
    assert len(result.grounded_uses) == 2
    assert result.grounded_uses[0].anchor_id == result.grounded_uses[1].anchor_id
    assert result.grounded_uses[0].contribution != result.grounded_uses[1].contribution


def test_table_omission_marker_is_never_accepted_as_evidence() -> None:
    target = _clause("target", "1", "Target", text="[Table omitted: Table A]")
    package = _package(_document(target), "target")

    result = ground_evidence_request(
        package,
        EvidenceGroundingRequest(
            owner_kind=EvidenceGroundingOwnerKind.ENTITY,
            owner_id="e1",
            evidence=(
                EvidenceUse(
                    source_ref=_source_ref(package, "target", EvidenceSourceKind.BODY),
                    exact_quote="[Table omitted: Table A]",
                ),
            ),
        ),
    )

    assert not result.complete
    assert result.failures[0].code is EvidenceGroundingFailureCode.UNQUOTEABLE_PROJECTION_MARKER
