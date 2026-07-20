from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.domain.model import ClauseType


def test_iec27000_atlasdata_contains_complete_public_structure() -> None:
    document = AtlasDataImporter().import_document(Path("data/IEC27000"))

    assert document.key.value == "IEC27000"
    assert document.title == "ISO/IEC 27000"
    assert len(document.clauses) == 128
    assert document.clauses[0].reference.clause == "0.1"
    assert document.clauses[-1].reference.clause == "5.5.6"

    terms = [clause for clause in document.clauses if clause.clause_type == ClauseType.TERM]
    term_entries = [clause for clause in terms if clause.reference.clause.startswith("3.")]
    assert len(terms) == 78
    assert len(term_entries) == 77
    assert term_entries[0].title == "access control"
    assert term_entries[-1].reference.clause == "3.77"
