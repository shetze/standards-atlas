from standards_atlas.application.context.source_surfaces import (
    SourceAccessPolicy,
    SourceSurfaceAvailability,
    SourceSurfaceRef,
    SourceSurfaceResolver,
    source_document_binding,
)
from standards_atlas.application.context.structured_candidates import (
    ContextCandidateReason,
    ContextDiagnosticCode,
    ContextPathKind,
    build_structured_context_candidates,
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
        reference=StandardReference(standard="TEST", clause=reference),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"{clause_id}-text", text=text),) if text else (),
        reference_mentions=mentions,
    )


def _document(*clauses: Clause, key: str = "TEST") -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=f"{key} document",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def _resolved_reference(
    surface: str,
    *,
    clause_id: str,
    reference: str,
    document_key: str | None = None,
) -> ReferenceMention:
    return ReferenceMention(
        kind=ReferenceMentionKind.CLAUSE,
        surface_text=surface,
        start_offset=0,
        end_offset=len(surface),
        reference=reference,
        status=ReferenceResolutionStatus.RESOLVED,
        targets=(
            ReferenceTarget(
                document_key=document_key,
                clause_id=clause_id,
                reference=reference,
            ),
        ),
    )


def _candidate_for(inventory, clause_id: str, kind: EvidenceSourceKind):
    return next(
        item
        for item in inventory.candidates
        if item.source_ref.clause_id == clause_id and item.source_ref.source_kind is kind
    )


def test_candidates_preserve_textless_parent_and_two_sided_leaf_sequence() -> None:
    root = _clause("root", "0", "Document")
    group = _clause("group", "5", "Shared safety activity", parent="root")
    intro = _clause("intro", "5.1", "Purpose", parent="group", text="Common purpose.")
    target = _clause("target", "5.2", "Detail", parent="group", text="Target detail.")
    later = _clause("later", "5.3", "Restriction", parent="group", text="Later detail.")
    document = _document(root, group, intro, target, later)

    inventory = build_structured_context_candidates(document, target)

    assert [item.clause_id for item in inventory.ancestor_path] == ["group", "root"]
    assert inventory.ancestor_path[0].body_present is False
    assert inventory.ancestor_path[0].heading_present is True
    assert inventory.sequence_clause_ids == ("intro", "target", "later")

    parent_heading = _candidate_for(inventory, "group", EvidenceSourceKind.HEADING)
    assert ContextCandidateReason.ANCESTOR_HEADING in parent_heading.reasons
    assert parent_heading.reach_status == "unconfirmed"

    intro_body = _candidate_for(inventory, "intro", EvidenceSourceKind.BODY)
    later_body = _candidate_for(inventory, "later", EvidenceSourceKind.BODY)
    assert ContextCandidateReason.SEQUENCE_PREVIOUS in intro_body.reasons
    assert ContextCandidateReason.FIRST_LEAF_CANDIDATE in intro_body.reasons
    assert ContextCandidateReason.SEQUENCE_NEXT in later_body.reasons
    assert intro_body.reach_status == later_body.reach_status == "unconfirmed"
    assert {
        path.direction for path in later_body.paths if path.kind is ContextPathKind.SEQUENCE
    } == {"forward"}


def test_candidate_discovery_does_not_pull_another_branch_through_distant_ancestor() -> None:
    root = _clause("root", "1", "Root")
    left = _clause("left", "1.1", "Left", parent="root")
    left_intro = _clause("left-intro", "1.1.1", "Left intro", parent="left", text="Left.")
    right = _clause("right", "1.2", "Right", parent="root")
    target = _clause("target", "1.2.1", "Target", parent="right", text="Target.")
    document = _document(root, left, left_intro, right, target)

    inventory = build_structured_context_candidates(document, target)

    assert "left-intro" not in {item.source_ref.clause_id for item in inventory.candidates}
    assert [item.clause_id for item in inventory.ancestor_path] == ["right", "root"]


def test_direct_and_reverse_internal_references_are_reachable_without_scope_confirmation() -> None:
    direct_target = _clause("remote", "8.4", "Remote", text="Referenced detail.")
    target = _clause(
        "target",
        "5.2",
        "Target",
        text="See 8.4.",
        mentions=(_resolved_reference("8.4", clause_id="remote", reference="8.4"),),
        parent="group",
    )
    intro = _clause("intro", "5.1", "Intro", parent="group", text="Intro.")
    group = _clause("group", "5", "Group")
    later = _clause(
        "later",
        "5.3",
        "Later exception",
        parent="group",
        text="Exception to 5.2.",
        mentions=(_resolved_reference("5.2", clause_id="target", reference="5.2"),),
    )
    document = _document(group, intro, target, later, direct_target)

    inventory = build_structured_context_candidates(document, target)

    remote = _candidate_for(inventory, "remote", EvidenceSourceKind.BODY)
    exception = _candidate_for(inventory, "later", EvidenceSourceKind.BODY)
    assert ContextCandidateReason.DIRECT_INTERNAL_REFERENCE in remote.reasons
    assert ContextCandidateReason.REVERSE_INTERNAL_REFERENCE in exception.reasons
    assert exception.reach_status == "unconfirmed"
    assert any(path.kind is ContextPathKind.REVERSE_REFERENCE for path in exception.paths)


def test_cycles_missing_parents_and_unresolved_references_remain_visible() -> None:
    unresolved = ReferenceMention(
        kind=ReferenceMentionKind.CLAUSE,
        surface_text="9.9",
        start_offset=0,
        end_offset=3,
        reference="9.9",
        status=ReferenceResolutionStatus.UNRESOLVED,
    )
    first = _clause("first", "1.1", "First", parent="second", text="First.")
    second = _clause("second", "1.2", "Second", parent="first", text="Second.")
    first = first.with_baseline_updates(reference_mentions=(unresolved,))
    cycle_document = _document(first, second)

    cycle_inventory = build_structured_context_candidates(cycle_document, first)
    assert ContextDiagnosticCode.ANCESTOR_CYCLE in {
        item.code for item in cycle_inventory.diagnostics
    }
    assert ContextDiagnosticCode.UNRESOLVED_REFERENCE in {
        item.code for item in cycle_inventory.diagnostics
    }

    orphan = _clause("orphan", "2.1", "Orphan", parent="missing", text="Body.")
    orphan_inventory = build_structured_context_candidates(_document(orphan), orphan)
    assert ContextDiagnosticCode.MISSING_PARENT in {
        item.code for item in orphan_inventory.diagnostics
    }


def test_external_content_requires_explicit_revision_bound_authorized_binding() -> None:
    external = _clause("ext", "7.2", "External", text="External source text.")
    external_document = _document(external, key="EXT")
    target = _clause(
        "target",
        "2.1",
        "Target",
        text="See EXT 7.2.",
        mentions=(
            _resolved_reference(
                "EXT 7.2",
                clause_id="ext",
                reference="7.2",
                document_key="EXT",
            ),
        ),
    )
    document = _document(target)
    resolver = SourceSurfaceResolver((document, external_document))

    unbound = build_structured_context_candidates(document, target, resolver=resolver)
    assert "ext" not in {item.source_ref.clause_id for item in unbound.candidates}
    assert ContextDiagnosticCode.EXTERNAL_REFERENCE_UNBOUND in {
        item.code for item in unbound.diagnostics
    }

    unversioned_ref = SourceSurfaceRef(
        document_key="EXT",
        clause_id="ext",
        source_kind=EvidenceSourceKind.BODY,
    )
    unversioned = build_structured_context_candidates(
        document,
        target,
        resolver=resolver,
        external_source_refs=(unversioned_ref,),
    )
    assert ContextDiagnosticCode.EXTERNAL_BINDING_UNVERSIONED in {
        item.code for item in unversioned.diagnostics
    }

    revision = source_document_binding(external_document).source_revision
    external_ref = unversioned_ref.model_copy(update={"document_revision": revision})
    bound = build_structured_context_candidates(
        document,
        target,
        resolver=resolver,
        external_source_refs=(external_ref,),
    )
    external_candidate = next(
        item for item in bound.candidates if item.source_ref.document_key == "EXT"
    )
    assert external_candidate.resolution.availability is SourceSurfaceAvailability.AVAILABLE
    assert ContextCandidateReason.EXPLICIT_EXTERNAL_REFERENCE in external_candidate.reasons

    denied_resolver = SourceSurfaceResolver(
        (document, external_document),
        access_policy=SourceAccessPolicy(allowed_document_keys=("TEST",)),
    )
    denied = build_structured_context_candidates(
        document,
        target,
        resolver=denied_resolver,
        external_source_refs=(external_ref,),
    )
    denied_candidate = next(
        item for item in denied.candidates if item.source_ref.document_key == "EXT"
    )
    assert denied_candidate.resolution.availability is SourceSurfaceAvailability.NOT_AUTHORIZED
    assert denied_candidate.resolution.text is None
