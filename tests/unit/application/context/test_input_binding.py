import json
import os
import subprocess
import sys
import textwrap

from standards_atlas.application.context import (
    ContextReuseReason,
    ContextSelectionProfile,
    build_context_source_package,
    build_structured_context_candidates,
    check_context_source_package_reuse,
    context_source_package_binding,
    select_structured_context,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentKnowledge,
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


def _document(*clauses: Clause, knowledge: DocumentKnowledge | None = None) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test document",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
        knowledge=knowledge or DocumentKnowledge(),
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


def _package(document: EngineeringDocument, target_id: str, profile=None):
    target = next(clause for clause in document.clauses if clause.id.value == target_id)
    inventory = build_structured_context_candidates(document, target)
    selection = select_structured_context(inventory, profile=profile)
    return build_context_source_package(document, inventory, selection)


def test_package_separates_source_candidate_selection_and_actual_input_fingerprints() -> None:
    parent = _clause("parent", "5", "Shared subject")
    intro = _clause("intro", "5.1", "Introduction", parent="parent", text="Common frame.")
    target = _clause("target", "5.2", "Detail", parent="parent", text="Target statement.")
    package = _package(_document(parent, intro, target), "target")

    fingerprints = package.fingerprints.model_dump(mode="json")
    assert set(fingerprints) == {
        "source_state_sha256",
        "candidate_space_sha256",
        "selection_decision_sha256",
        "actual_input_sha256",
    }
    assert len(set(fingerprints.values())) == 4
    assert package.input_surfaces
    assert all(surface.text for surface in package.input_surfaces)
    assert package.selection.profile.profile_id == "assertion-context-selection-v1"


def test_parent_heading_change_invalidates_reuse_even_when_target_body_is_unchanged() -> None:
    first_parent = _clause("parent", "5", "Original shared subject")
    target = _clause("target", "5.1", "Detail", parent="parent", text="Target statement.")
    before = _package(_document(first_parent, target), "target")

    changed_parent = _clause("parent", "5", "Changed shared subject")
    after = _package(_document(changed_parent, target), "target")

    check = check_context_source_package_reuse(context_source_package_binding(before), after)

    assert before.target_clause_id == after.target_clause_id == "target"
    assert next(
        surface.text
        for surface in before.input_surfaces
        if surface.source_ref.clause_id == "target"
        and surface.source_ref.source_kind.value == "body"
    ) == next(
        surface.text
        for surface in after.input_surfaces
        if surface.source_ref.clause_id == "target"
        and surface.source_ref.source_kind.value == "body"
    )
    assert check.reusable is False
    assert ContextReuseReason.SOURCE_STATE_CHANGED in check.reasons
    assert ContextReuseReason.CANDIDATE_SPACE_CHANGED in check.reasons
    assert ContextReuseReason.ACTUAL_INPUT_CHANGED in check.reasons


def test_new_unselected_later_exception_invalidates_previous_binding() -> None:
    parent = _clause("parent", "5", "Group")
    intro = _clause("intro", "5.1", "Introduction", parent="parent", text="Common frame.")
    target = _clause("target", "5.2", "Target", parent="parent", text="Target statement.")
    before_document = _document(parent, intro, target)
    profile = ContextSelectionProfile(character_budget=480, max_sequence_distance=0)
    before = _package(before_document, "target", profile)
    before_binding = context_source_package_binding(before)

    later_exception = _clause(
        "later",
        "5.3",
        "Exception",
        parent="parent",
        text="Exception text that is outside the configured sequence window.",
        mentions=(_resolved_reference("5.2", clause_id="target", reference="5.2"),),
    )
    after_document = _document(parent, intro, target, later_exception)
    after = _package(after_document, "target", profile)

    check = check_context_source_package_reuse(before_binding, after)

    assert [
        (item.source_ref.clause_id, item.source_ref.source_kind) for item in before.input_surfaces
    ] == [(item.source_ref.clause_id, item.source_ref.source_kind) for item in after.input_surfaces]
    assert any(item.candidate.source_ref.clause_id == "later" for item in after.selection.omitted)
    assert check.reusable is False
    assert ContextReuseReason.SOURCE_STATE_CHANGED in check.reasons
    assert ContextReuseReason.CANDIDATE_SPACE_CHANGED in check.reasons


def test_policy_change_invalidates_selection_without_redefining_source_state() -> None:
    parent = _clause("parent", "5", "Group")
    target = _clause("target", "5.1", "Target", parent="parent", text="Target statement.")
    document = _document(parent, target)
    first = _package(document, "target", ContextSelectionProfile(character_budget=2_000))
    second = _package(document, "target", ContextSelectionProfile(character_budget=2_001))

    check = check_context_source_package_reuse(context_source_package_binding(first), second)

    assert check.reusable is False
    assert check.reasons == (ContextReuseReason.SELECTION_CHANGED,)
    assert first.fingerprints.source_state_sha256 == second.fingerprints.source_state_sha256
    assert first.fingerprints.candidate_space_sha256 == second.fingerprints.candidate_space_sha256
    assert first.fingerprints.actual_input_sha256 == second.fingerprints.actual_input_sha256


def test_knowledge_and_report_like_state_are_not_part_of_source_fingerprints() -> None:
    target = _clause("target", "1", "Target", text="Source text.")
    first_document = _document(target)
    second_document = _document(
        target,
        knowledge=DocumentKnowledge(ontology_versions=("example@1",)),
    )

    first = _package(first_document, "target")
    second = _package(second_document, "target")

    assert first.fingerprints == second.fingerprints
    assert check_context_source_package_reuse(
        context_source_package_binding(first), second
    ).reusable


def test_deterministic_package_core_is_stable_across_fresh_processes() -> None:
    script = textwrap.dedent(
        """
        import json
        from standards_atlas.application.context import (
            build_context_source_package,
            build_structured_context_candidates,
            select_structured_context,
        )
        from standards_atlas.domain.model import (
            Clause, ClauseId, ClauseType, DocumentKey, DocumentType,
            EngineeringDocument, StandardReference, TextBlock,
        )
        target = Clause(
            id=ClauseId(value="target"),
            reference=StandardReference(standard="TEST", clause="1"),
            clause_type=ClauseType.CLAUSE,
            heading="Target α😀",
            content=(TextBlock(id="t", text="Line 1\\r\\nLine 2 α😀"),),
        )
        document = EngineeringDocument(
            key=DocumentKey(value="TEST"),
            title="Test document",
            document_type=DocumentType.STANDARD,
            clauses=(target,),
        )
        inventory = build_structured_context_candidates(document, target)
        selection = select_structured_context(inventory)
        package = build_context_source_package(document, inventory, selection)
        print(json.dumps(package.fingerprints.model_dump(mode="json"), sort_keys=True))
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    first = subprocess.check_output([sys.executable, "-c", script], text=True, env=env).strip()
    second = subprocess.check_output([sys.executable, "-c", script], text=True, env=env).strip()

    assert json.loads(first) == json.loads(second)
