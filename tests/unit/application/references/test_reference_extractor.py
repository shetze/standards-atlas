from standards_atlas.application.references import extract_reference_mentions
from standards_atlas.domain.model import ReferenceMentionKind, ReferenceResolutionStatus


def test_preserves_explicit_and_contextual_clause_mentions():
    mentions = extract_reference_mentions(
        "This clause applies before the following clauses and Clause 7.4."
    )
    assert [m.kind for m in mentions] == [
        ReferenceMentionKind.CONTEXTUAL_CLAUSE,
        ReferenceMentionKind.CONTEXTUAL_CLAUSE,
        ReferenceMentionKind.CLAUSE,
    ]
    assert mentions[0].direction_hint == "self"
    assert mentions[1].direction_hint == "forward"
    assert mentions[2].reference == "7.4"
    assert mentions[2].status is ReferenceResolutionStatus.UNRESOLVED


def test_preserves_clause_ranges_as_unresolved_evidence():
    mentions = extract_reference_mentions("See clauses 7.2 to 7.5 for details.")
    assert len(mentions) == 1
    assert mentions[0].kind is ReferenceMentionKind.CLAUSE_RANGE
    assert mentions[0].range_start == "7.2"
    assert mentions[0].range_end == "7.5"


def test_resolves_unique_same_document_reference():
    from standards_atlas.application.references import resolve_document_reference_mentions
    from standards_atlas.domain.model import (
        Clause,
        ClauseId,
        ClauseType,
        DocumentKey,
        DocumentType,
        EngineeringDocument,
        StandardReference,
        TextBlock,
    )

    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="X", clause="7.4"),
        clause_type=ClauseType.CLAUSE,
    )
    source = Clause(
        id=ClauseId(value="source"),
        reference=StandardReference(standard="X", clause="8"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="t1", text="See Clause 7.4."),),
        reference_mentions=extract_reference_mentions("See Clause 7.4."),
    )
    doc = EngineeringDocument(
        key=DocumentKey(value="x"),
        title="X",
        document_type=DocumentType.STANDARD,
        clauses=(target, source),
    )
    mention = resolve_document_reference_mentions(doc).clauses[1].reference_mentions[0]
    assert mention.status is ReferenceResolutionStatus.RESOLVED
    assert mention.targets[0].clause_id == "target"
