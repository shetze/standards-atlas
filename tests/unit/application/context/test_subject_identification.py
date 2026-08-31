from standards_atlas.application.context import (
    DeterministicSubjectIdentifier,
    SubjectCandidateVocabularyBuilder,
    SubjectEvidenceKind,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    StructuralContext,
    StructuralNodeKind,
    StructuralScopeEdge,
    TextBlock,
)


def _clause(
    clause_id: str,
    reference: str,
    *,
    heading: str | None = None,
    text: str = "",
    clause_type: ClauseType = ClauseType.CLAUSE,
    parent_id: str | None = None,
    structural_context: StructuralContext | None = None,
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="STD", year=2026, clause=reference),
        clause_type=clause_type,
        heading=heading,
        content=(TextBlock(id=f"{clause_id}-text", text=text),) if text else (),
        parent_id=ClauseId(value=parent_id) if parent_id else None,
        structural_context=structural_context,
    )


def _document(*clauses: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="STD"),
        title="STD",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def _vocabulary() -> object:
    definitions = _document(
        _clause("term-system", "3.1", heading="system", clause_type=ClauseType.TERM),
        _clause(
            "term-system-under-consideration",
            "3.2",
            heading="system under consideration",
            clause_type=ClauseType.TERM,
        ),
        _clause("term-risk", "3.3", heading="risk", clause_type=ClauseType.TERM),
        _clause("term-software", "3.4", heading="software", clause_type=ClauseType.TERM),
    )
    return SubjectCandidateVocabularyBuilder().build((definitions,))


def test_identifier_prefers_specific_explicit_term_match() -> None:
    clause = _clause(
        "c1",
        "4.1",
        text="The system under consideration shall define its interfaces.",
    )
    report = DeterministicSubjectIdentifier().identify((_document(clause),), _vocabulary())

    subject = report.results[0].primary_subject
    assert subject is not None
    assert subject.normalized_label == "system under consideration"
    assert subject.evidence.kind is SubjectEvidenceKind.CLAUSE_TEXT
    assert subject.confidence == 0.95


def test_identifier_prefers_clause_heading_over_body_text() -> None:
    clause = _clause(
        "c1",
        "4.1",
        heading="Software requirements",
        text="The risk shall be assessed.",
    )
    report = DeterministicSubjectIdentifier().identify((_document(clause),), _vocabulary())

    subject = report.results[0].primary_subject
    assert subject is not None
    assert subject.normalized_label == "software"
    assert subject.evidence.kind is SubjectEvidenceKind.CLAUSE_HEADING
    assert subject.confidence == 1.0


def test_identifier_inherits_nearest_matching_ancestor_heading() -> None:
    parent = _clause("parent", "5", heading="Software development")
    child = _clause("child", "5.1", text="It shall be verified.", parent_id="parent")
    report = DeterministicSubjectIdentifier().identify(
        (_document(parent, child),),
        _vocabulary(),
    )

    subject = report.results[1].primary_subject
    assert subject is not None
    assert subject.normalized_label == "software"
    assert subject.evidence.kind is SubjectEvidenceKind.ANCESTOR_HEADING
    assert subject.evidence.source_clause_id == "parent"
    assert subject.evidence.ancestor_distance == 1


def test_identifier_uses_resolved_inbound_scope_as_last_deterministic_source() -> None:
    scope = _clause(
        "scope",
        "1",
        text="This document applies to the system under consideration.",
        clause_type=ClauseType.SCOPE,
        structural_context=StructuralContext(
            node_kind=StructuralNodeKind.NODE,
            scopes=(
                StructuralScopeEdge(
                    source_clause_id="scope",
                    target_clause_id="target",
                    direction="forward",
                    status="resolved",
                    surface_text="applies to the system under consideration",
                ),
            ),
        ),
    )
    target = _clause("target", "4.1", text="The requirements shall be verified.")
    report = DeterministicSubjectIdentifier().identify(
        (_document(scope, target),),
        _vocabulary(),
    )

    subject = report.results[1].primary_subject
    assert subject is not None
    assert subject.normalized_label == "system under consideration"
    assert subject.evidence.kind is SubjectEvidenceKind.SCOPE_CONTEXT
    assert subject.confidence == 0.75


def test_identifier_keeps_unresolved_clauses_explicit_and_reports_coverage() -> None:
    resolved = _clause("resolved", "4.1", text="Software shall be tested.")
    unresolved = _clause("unresolved", "4.2", text="It shall be tested.")
    report = DeterministicSubjectIdentifier().identify(
        (_document(resolved, unresolved),),
        _vocabulary(),
    )

    assert report.results[1].primary_subject is None
    assert report.analysis.clauses == 2
    assert report.analysis.resolved_clauses == 1
    assert report.analysis.unresolved_clauses == 1
    assert report.analysis.resolution_coverage == 0.5
    assert report.analysis.clause_text_matches == 1


def test_identifier_does_not_break_equally_specific_matches_lexically() -> None:
    clause = _clause(
        "c1",
        "4.1",
        heading="Software risk",
        text="It shall be controlled.",
    )
    report = DeterministicSubjectIdentifier().identify((_document(clause),), _vocabulary())

    result = report.results[0]
    assert result.primary_subject is None
    assert result.ambiguous_candidates == ("risk", "software")
    assert report.analysis.ambiguous_clauses == 1
