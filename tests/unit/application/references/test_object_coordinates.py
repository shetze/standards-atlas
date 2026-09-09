"""Labelled figure/table addresses must never collapse into numeric clauses."""

import pytest

from standards_atlas.application.references.extractor import extract_reference_mentions
from standards_atlas.application.references.resolution import DocumentReferenceIndex
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def indexed_document():
    coordinates = [
        ("numeric-1", "1", ClauseType.CLAUSE),
        ("numeric-2", "2", ClauseType.CLAUSE),
        ("figure-2", "Figure 2", ClauseType.MISC),
        ("figure-3", "Figure 3", ClauseType.MISC),
        ("table-1", "1", ClauseType.TABLE),
        ("table-3", "Table 3", ClauseType.TABLE),
    ]
    return EngineeringDocument(
        key=DocumentKey(value="IEC61508-2"),
        title="Synthetic labelled objects",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=identifier),
                clause_type=kind,
                reference=StandardReference(
                    standard="IEC 61508", part="2", year=2010, clause=coordinate
                ),
            )
            for identifier, coordinate, kind in coordinates
        ),
    )


@pytest.mark.parametrize(
    "citation,expected",
    [
        ("Figure 2 and Table 1", ("figure-2", "table-1")),
        ("IEC 61508-2 Figure 2 and Table 1", ("figure-2", "table-1")),
        ("Figure 2, Table 1 and 3", ("figure-2", "table-1", "table-3")),
        ("Table 1 and Figure 2 and 3", ("table-1", "figure-2", "figure-3")),
        ("Figures 2 to 3", ("figure-2", "figure-3")),
        ("Fig. 2", ("figure-2",)),
        ("Figures 2 and 3", ("figure-2", "figure-3")),
        ("1 and 2", ("numeric-1", "numeric-2")),
    ],
)
def test_exact_labelled_objects_are_distinct_from_numeric_clauses(citation, expected):
    index = DocumentReferenceIndex(indexed_document())
    result = index.resolve_group(citation, "numeric-1")
    assert result.status == "resolved"
    assert tuple(clause.id.value for clause in result.targets) == expected


def test_explicit_figure_never_uses_equal_numbered_clause_or_table():
    document = indexed_document()
    document = document.model_copy(
        update={"clauses": tuple(c for c in document.clauses if c.id.value != "figure-2")}
    )
    index = DocumentReferenceIndex(document)
    assert index.resolve_group("Figure 2", "numeric-1").status == "unresolved"
    assert index.resolve("Figure 2", "numeric-1") is None
    result = index.resolve_group("Figure 2 and Table 1", "numeric-1")
    assert result.status == "partially_resolved"
    assert [c.id.value for c in result.targets] == ["table-1"]


@pytest.mark.parametrize(
    "text",
    [
        "See IEC 61508-2 Figure 2 and Table 1.",
        "See Figure 2 and Table 1 of IEC 61508-2.",
        "See Fig. 2 and Table 1 of IEC 61508-2.",
    ],
)
def test_extraction_and_resolution_accept_the_same_mixed_object_citation(text):
    (mention,) = extract_reference_mentions(text)
    assert text[mention.start_offset : mention.end_offset] == mention.surface_text
    result = DocumentReferenceIndex(indexed_document()).resolve_group(
        mention.reference, "numeric-1"
    )
    assert result.status == "resolved"
    assert [c.id.value for c in result.targets] == ["figure-2", "table-1"]


def test_range_cannot_cross_from_a_figure_to_a_table():
    index = DocumentReferenceIndex(indexed_document())
    assert index.coordinates("Figure 2 to Table 3") == ()
