"""Only address syntax changes: editions, object namespaces and groups stay strict."""

import pytest

from standards_atlas.application.context.scope_targets import ScopeTargetResolver
from standards_atlas.application.references.catalog import ReferenceDocumentCatalog
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


def document(part=1):
    records = [
        ("source", "1", ClauseType.CLAUSE),
        ("clause-8", "8", ClauseType.CLAUSE),
        ("numeric-A.1", "A.1", ClauseType.CLAUSE),
        ("numeric-ZZ.1", "ZZ.1", ClauseType.CLAUSE),
        ("table-A.1", "A.1", ClauseType.TABLE),
        ("table-A.2", "A.2", ClauseType.TABLE),
        ("table-A.3", "Table A.3", ClauseType.TABLE),
        ("table-ZZ.1", "ZZ.1", ClauseType.TABLE),
        ("table-ZZ.2", "Table ZZ.2", ClauseType.TABLE),
        ("figure-2", "Figure 2", ClauseType.MISC),
        ("figure-3", "Figure 3", ClauseType.MISC),
    ]
    return EngineeringDocument(
        key=DocumentKey(value=f"IEC99999-{part}"),
        title="Synthetic bounded syntax fixture",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"p{part}-{name}"),
                clause_type=kind,
                reference=StandardReference(
                    standard="IEC 99999", part=str(part), year=2026, clause=coordinate
                ),
            )
            for name, coordinate, kind in records
        ),
    )


@pytest.mark.parametrize(
    "citation,expected",
    [
        ("Table A.1 to Table A.3", ["table-A.1", "table-A.2", "table-A.3"]),
        ("Tables A.1 through TABLE A.3", ["table-A.1", "table-A.2", "table-A.3"]),
        ("Figures 2 to Figure 3", ["figure-2", "figure-3"]),
        ("Table ZZ.1", ["table-ZZ.1"]),
        ("Tables ZZ.1 to Table ZZ.2", ["table-ZZ.1", "table-ZZ.2"]),
        ("Table ZZ.1 and ZZ.2", ["table-ZZ.1", "table-ZZ.2"]),
        ("Table A.1 and Table ZZ.1", ["table-A.1", "table-ZZ.1"]),
        (
            "Table A.1 to Table A.3, Figure 2 and Table ZZ.1",
            ["table-A.1", "table-A.2", "table-A.3", "figure-2", "table-ZZ.1"],
        ),
        ("IEC 99999-1:2026, Clause 8", ["clause-8"]),
        ("IEC 99999-1:2026,Clause 8", ["clause-8"]),
    ],
)
def test_new_syntax_resolves_complete_exact_objects(citation, expected):
    result = DocumentReferenceIndex(document()).resolve_group(citation, "p1-source")
    assert result.status == "resolved"
    assert [clause.id.value for clause in result.targets] == [f"p1-{name}" for name in expected]


@pytest.mark.parametrize("descendants,kind", [(False, "clause"), (True, "subtree")])
def test_missing_table_range_stays_one_literal_scope_not_existing_endpoints(descendants, kind):
    doc = document()
    doc = doc.model_copy(
        update={"clauses": tuple(c for c in doc.clauses if c.id.value != "p1-table-A.2")}
    )
    reference = "Table A.1 to Table A.3"
    (reach,) = ScopeTargetResolver(doc).resolve(
        reference, include_descendants=descendants, source_clause_id="p1-source"
    )
    assert reach.reference == reference
    assert reach.kind.value == kind
    assert reach.clause_id is None
    assert reach.document_key == doc.key.value
    (target,) = ReferenceDocumentCatalog(doc).targets(reference, "p1-source")
    assert target.reference == reference and target.clause_id is None


def test_missing_multiletter_object_never_uses_equal_named_nonobject():
    doc = document()
    doc = doc.model_copy(
        update={"clauses": tuple(c for c in doc.clauses if c.id.value != "p1-table-ZZ.1")}
    )
    (reach,) = ScopeTargetResolver(doc).resolve(
        "Table ZZ.1", include_descendants=True, source_clause_id="p1-source"
    )
    assert reach.kind.value == "subtree" and reach.clause_id is None
    assert reach.reference == "Table ZZ.1"


@pytest.mark.parametrize(
    "citation",
    [
        "Table A.1 to Figure A.3",
        "Figure 2 to Table 3",
        "Clause 1 to Table 3",
        "Table A.1 to Annex A.3",
        "Table A.3 to Table A.1",
        "Table A.1 to Table B.3",
        "Table 1 to Table 203",
        "Clause ZZ.1",
        "ZZ.1",
        "IEC 99999-1:2025, Table A.1",
        "IEC 99999-1:2026; Table A.1",
        "IEC 99999-1, Table A.1",
    ],
)
def test_unsupported_forms_do_not_acquire_parseable_coordinates(citation):
    assert DocumentReferenceIndex(document()).coordinates(citation) == ()


def test_catalogue_and_scope_resolver_share_exact_edition_comma_handling():
    source, target = document(), document(2)
    citation = "IEC 99999-2:2026, Clause 8"
    (reach,) = ScopeTargetResolver(source, (target,)).resolve(
        citation, include_descendants=False, source_clause_id="p1-source"
    )
    (address,) = ReferenceDocumentCatalog(source, (target,)).targets(citation, "p1-source")
    assert reach.clause_id == address.clause_id == "p2-clause-8"
    assert reach.document_key == address.document_key == "IEC99999-2"
    assert DocumentReferenceIndex(target).resolve(citation, "p2-source").id.value == "p2-clause-8"
    with pytest.raises(ValueError, match="cannot identify scope target"):
        ScopeTargetResolver(source, (target,)).resolve(
            "IEC 99999-2:2025, Clause 8",
            include_descendants=False,
            source_clause_id="p1-source",
        )
    (address,) = ReferenceDocumentCatalog(source, (target,)).targets(
        "IEC 99999-2:2025, Clause 8", "p1-source"
    )
    assert address.clause_id is None


@pytest.mark.parametrize(
    "citation",
    [
        "Table ZZ.1",
        "Tables ZZ.1 to Table ZZ.2",
        "Table ZZ.1 and ZZ.2",
        "Table A.1 and Table ZZ.1",
        "IEC 99999-1:2026, Table ZZ.1",
        "Table ZZ.1 of IEC 99999-1:2026",
        "Table A.1 to Table A.3",
    ],
)
def test_extractor_keeps_whole_labelled_groups_and_exact_source_spans(citation):
    text = f"See {citation} for a synthetic example."
    (mention,) = extract_reference_mentions(text)
    assert mention.surface_text == citation
    assert text[mention.start_offset : mention.end_offset] == citation
    result = ReferenceDocumentCatalog(document()).targets(mention.reference, "p1-source")
    assert all(target.clause_id is not None for target in result)
    assert all("table" in target.clause_id for target in result)


def test_multiletter_coordinate_extraction_requires_an_object_label():
    for text in ("ZZ.1", "Clause ZZ.1", "IEC 99999-1:2026 ZZ.1", "Clause 8 and ZZ.1"):
        assert not any("ZZ.1" in (m.reference or "") for m in extract_reference_mentions(text))
