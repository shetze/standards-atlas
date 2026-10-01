from standards_atlas.application.context.context_selection import (
    ContextOmissionReason,
    ContextReachHint,
    ContextSelectionCompleteness,
    ContextSelectionProfile,
    ContextSelectionReason,
    select_structured_context,
)
from standards_atlas.application.context.source_surfaces import SourceSurfaceResolver
from standards_atlas.application.context.structured_candidates import (
    ContextCandidateReason,
    build_structured_context_candidates,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
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
        reference=StandardReference(standard="TEST", clause=reference),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"{clause_id}-text", text=text),) if text else (),
        reference_mentions=mentions,
    )


def _document(*clauses: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def _resolved_reference(surface: str, *, clause_id: str, reference: str) -> ReferenceMention:
    return ReferenceMention(
        kind=ReferenceMentionKind.CLAUSE,
        surface_text=surface,
        start_offset=0,
        end_offset=len(surface),
        reference=reference,
        status=ReferenceResolutionStatus.RESOLVED,
        targets=(ReferenceTarget(clause_id=clause_id, reference=reference),),
    )


def _selected_clause_ids(selection) -> list[str]:
    return [item.candidate.source_ref.clause_id for item in selection.selected]


def test_selection_is_deterministic_and_never_confirms_foreign_reach() -> None:
    parent = _clause("parent", "5", "Shared subject")
    intro = _clause("intro", "5.1", "Introduction", parent="parent", text="Common frame.")
    target = _clause("target", "5.2", "Detail", parent="parent", text="Target statement.")
    later = _clause("later", "5.3", "Detail", parent="parent", text="Same term, other subject.")
    document = _document(parent, intro, target, later)
    inventory = build_structured_context_candidates(document, target)
    profile = ContextSelectionProfile(character_budget=4_000, max_sequence_distance=4)

    first = select_structured_context(inventory, profile=profile)
    second = select_structured_context(inventory, profile=profile)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.profile.profile_id == "assertion-context-selection-v1"
    assert first.completeness in {
        ContextSelectionCompleteness.COMPLETE,
        ContextSelectionCompleteness.BOUNDED,
    }
    foreign = [item for item in first.selected if item.candidate.reach_status == "unconfirmed"]
    assert foreign
    assert all(item.semantic_reach_confirmed is False for item in foreign)
    intro_entries = [
        item for item in first.selected if item.candidate.source_ref.clause_id == "intro"
    ]
    assert intro_entries
    assert all(ContextReachHint.SAME_PARENT_SEQUENCE in item.reach_hints for item in intro_entries)
    assert any(
        ContextCandidateReason.FIRST_LEAF_CANDIDATE in item.candidate.reasons
        for item in intro_entries
    )


def test_reverse_reference_is_considered_before_unlinked_previous_context_under_budget() -> None:
    parent = _clause("parent", "5", "Group")
    intro = _clause(
        "intro",
        "5.1",
        "Introduction",
        parent="parent",
        text="I" * 500,
    )
    target = _clause("target", "5.2", "Target", parent="parent", text="Target.")
    later = _clause(
        "later",
        "5.3",
        "Exception",
        parent="parent",
        text="Later constraint.",
        mentions=(_resolved_reference("5.2", clause_id="target", reference="5.2"),),
    )
    document = _document(parent, intro, target, later)
    inventory = build_structured_context_candidates(document, target)
    profile = ContextSelectionProfile(
        character_budget=900,
        fixed_overhead_chars=100,
        per_surface_overhead_chars=40,
    )

    selection = select_structured_context(inventory, profile=profile)

    later_entries = [
        item for item in selection.selected if item.candidate.source_ref.clause_id == "later"
    ]
    assert later_entries
    assert all(
        item.selection_reason is ContextSelectionReason.EXPLICIT_REFERENCE for item in later_entries
    )
    assert any(
        ContextReachHint.REVERSE_REFERENCE_TO_TARGET_OR_SEQUENCE in item.reach_hints
        for item in later_entries
    )
    assert any(
        item.candidate.source_ref.clause_id == "intro"
        and item.reason is ContextOmissionReason.BUDGET_EXCEEDED
        for item in selection.omitted
    )
    assert selection.completeness is ContextSelectionCompleteness.INCOMPLETE


def test_target_content_over_budget_is_not_silently_truncated() -> None:
    target = _clause("target", "1", "Target heading", text="X" * 500)
    inventory = build_structured_context_candidates(_document(target), target)
    profile = ContextSelectionProfile(
        character_budget=300,
        fixed_overhead_chars=50,
        per_surface_overhead_chars=20,
    )

    selection = select_structured_context(inventory, profile=profile)

    assert selection.selected == ()
    assert selection.completeness is ContextSelectionCompleteness.INPUT_BUDGET_EXCEEDED
    assert selection.gaps[0].code == "input_budget_exceeded"
    assert selection.omitted
    assert all(
        item.reason is ContextOmissionReason.INPUT_BUDGET_EXCEEDED for item in selection.omitted
    )


def test_sequence_window_is_bounded_without_turning_first_leaf_into_scope_truth() -> None:
    parent = _clause("parent", "5", "Group")
    first = _clause("first", "5.1", "First", parent="parent", text="First.")
    second = _clause("second", "5.2", "Second", parent="parent", text="Second.")
    target = _clause("target", "5.3", "Target", parent="parent", text="Target.")
    fourth = _clause("fourth", "5.4", "Fourth", parent="parent", text="Fourth.")
    document = _document(parent, first, second, target, fourth)
    inventory = build_structured_context_candidates(document, target)
    profile = ContextSelectionProfile(character_budget=4_000, max_sequence_distance=1)

    selection = select_structured_context(inventory, profile=profile)

    first_omissions = [
        item for item in selection.omitted if item.candidate.source_ref.clause_id == "first"
    ]
    assert first_omissions
    assert all(
        item.reason is ContextOmissionReason.OUTSIDE_SEQUENCE_WINDOW for item in first_omissions
    )
    assert all(item.candidate.reach_status == "unconfirmed" for item in first_omissions)
    assert selection.completeness is ContextSelectionCompleteness.BOUNDED


def test_unresolved_reference_is_an_explicit_gap_not_a_guessed_source() -> None:
    unresolved = ReferenceMention(
        kind=ReferenceMentionKind.CLAUSE,
        surface_text="9.9",
        start_offset=0,
        end_offset=3,
        reference="9.9",
        status=ReferenceResolutionStatus.UNRESOLVED,
    )
    target = _clause(
        "target",
        "1",
        "Target",
        text="See 9.9.",
        mentions=(unresolved,),
    )
    inventory = build_structured_context_candidates(_document(target), target)

    selection = select_structured_context(inventory)

    assert selection.completeness is ContextSelectionCompleteness.INCOMPLETE
    assert any(gap.code == "unresolved_reference" for gap in selection.gaps)
    assert "9.9" not in _selected_clause_ids(selection)


def test_addressed_excerpt_offsets_survive_selection() -> None:
    target = _clause("target", "1", "Target", text="0123456789")
    context = _clause("context", "2", "Context", text="abcdefghij")
    document = _document(target, context)
    inventory = build_structured_context_candidates(document, target)

    # Inject a deterministic addressed excerpt as S05/S06 callers may do later.  Selection must
    # preserve the resolver's absolute offsets rather than pretending it is a full source surface.
    candidate = next(
        item
        for item in inventory.candidates
        if item.source_ref.clause_id == "target" and item.source_ref.source_kind.value == "body"
    )
    excerpt_resolution = SourceSurfaceResolver((document,)).resolve(
        candidate.source_ref, start_offset=2, end_offset=7
    )
    amended = inventory.model_copy(
        update={
            "candidates": tuple(
                item.model_copy(update={"resolution": excerpt_resolution})
                if item.candidate_id == candidate.candidate_id
                else item
                for item in inventory.candidates
            )
        }
    )

    selection = select_structured_context(amended)
    selected = next(
        item for item in selection.selected if item.candidate.candidate_id == candidate.candidate_id
    )
    assert selected.candidate.resolution.start_offset == 2
    assert selected.candidate.resolution.end_offset == 7
    assert selected.candidate.resolution.text == "23456"
