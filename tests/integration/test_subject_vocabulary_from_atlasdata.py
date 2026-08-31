from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.application.context import SubjectCandidateVocabularyBuilder


def test_subject_vocabulary_is_derived_from_real_atlasdata_terms() -> None:
    documents = tuple(
        AtlasDataImporter().import_document(Path(path))
        for path in ("data/IEC27000", "data/ISO26262", "data/EN50126")
    )

    vocabulary = SubjectCandidateVocabularyBuilder().build(documents)

    assert vocabulary.analysis.accepted_term_clauses > 300
    assert vocabulary.analysis.extraction_coverage == 1.0
    assert vocabulary.find("risk") is not None
    assert vocabulary.find("software") is not None
    assert vocabulary.find("component") is not None
    assert vocabulary.find("system") is not None
    assert vocabulary.analysis.cross_document_candidates > 0
