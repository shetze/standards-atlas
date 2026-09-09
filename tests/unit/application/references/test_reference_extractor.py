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


def test_standard_part_numbers_are_never_clause_ranges():
    for text in (
        "Annex A of IEC 61508-5",
        "Clause 7 of IEC 61508-1",
        "IEC 61508-3:2010 Clause 7",
        "Table A.1 of ISO 26262-6:2018",
    ):
        (mention,) = extract_reference_mentions(text)
        assert mention.kind == ReferenceMentionKind.CLAUSE
        assert mention.cardinality_hint == "one"
        assert mention.range_start is mention.range_end is None
        assert text[mention.start_offset : mention.end_offset] == mention.surface_text


def test_coordinate_lists_remain_lists_not_ranges():
    for text in ("Clauses 6 and 8 of IEC 61508-1", "Figure 2 and Table 1 of IEC 61508-2"):
        (mention,) = extract_reference_mentions(text)
        assert mention.kind == ReferenceMentionKind.CLAUSE
        assert mention.cardinality_hint == "multiple"
        assert mention.range_start is mention.range_end is None


def test_actual_range_ignores_standard_identity_in_either_position():
    for text in ("Clauses 7.2 to 7.5 of IEC 61508-3", "IEC 61508-3:2010 Clauses 7.2-7.5"):
        (mention,) = extract_reference_mentions(text)
        assert mention.kind == ReferenceMentionKind.CLAUSE_RANGE
        assert (mention.range_start, mention.range_end) == ("7.2", "7.5")


def test_shared_coordinate_has_all_named_documents_and_exact_evidence_span():
    text = "See Clause 7 of IEC 61508-2 and IEC 61508-3 respectively."
    mentions = extract_reference_mentions(text)
    assert [m.reference for m in mentions] == ["IEC 61508-2 Clause 7", "IEC 61508-3 Clause 7"]
    assert all(m.cardinality_hint == "one" and m.range_start is None for m in mentions)
    assert len({(m.start_offset, m.end_offset) for m in mentions}) == 1
    assert all(text[m.start_offset : m.end_offset] == m.surface_text for m in mentions)
    assert all("IEC 61508-2 and IEC 61508-3" in m.surface_text for m in mentions)


def test_shared_coordinate_supports_three_explicit_designations_and_editions():
    text = "Clauses 6 and 8 of IEC 61508-1:2010, IEC 61508-2:2010 and IEC 61508-3:2010."
    mentions = extract_reference_mentions(text)
    assert [m.reference for m in mentions] == [
        f"IEC 61508-{part}:2010 Clauses 6 and 8" for part in (1, 2, 3)
    ]
    assert all(m.range_start is None and m.cardinality_hint == "multiple" for m in mentions)


def test_different_coordinate_groups_are_not_merged_across_standards():
    text = "Figure 2 of IEC 61508-2 and Figure 3 of IEC 61508-3; see Clause 8 of IEC 61508-1."
    assert [m.reference for m in extract_reference_mentions(text)] == [
        "IEC 61508-2 Figure 2",
        "IEC 61508-3 Figure 3",
        "IEC 61508-1 Clause 8",
    ]
