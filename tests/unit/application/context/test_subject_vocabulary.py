from standards_atlas.application.context import (
    SubjectCandidateVocabularyBuilder,
    normalize_subject_label,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def _clause(
    *,
    clause_id: str,
    document: str,
    reference: str,
    heading: str | None,
    clause_type: ClauseType = ClauseType.TERM,
    part: str | None = None,
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(
            standard=document,
            part=part,
            year=2025,
            clause=reference,
        ),
        clause_type=clause_type,
        heading=heading,
    )


def _document(key: str, *clauses: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def test_builder_uses_only_defined_term_headings() -> None:
    document = _document(
        "STD",
        _clause(
            clause_id="terms",
            document="STD",
            reference="3",
            heading="Terms and definitions",
        ),
        _clause(
            clause_id="system",
            document="STD",
            reference="3.1",
            heading="system under consideration",
        ),
        _clause(
            clause_id="body",
            document="STD",
            reference="4.1",
            heading="System requirements",
            clause_type=ClauseType.CLAUSE,
        ),
    )

    vocabulary = SubjectCandidateVocabularyBuilder().build((document,))

    assert [item.normalized_label for item in vocabulary.candidates] == [
        "system under consideration"
    ]
    assert vocabulary.analysis.term_clauses == 2
    assert vocabulary.analysis.accepted_term_clauses == 1
    assert vocabulary.analysis.ignored_term_containers == 1
    assert vocabulary.analysis.extraction_coverage == 1.0


def test_builder_merges_only_lexical_variants_and_preserves_provenance() -> None:
    first = _document(
        "A",
        _clause(
            clause_id="a-system",
            document="A",
            reference="3.1",
            heading="System   under Consideration",
        ),
    )
    second = _document(
        "B",
        _clause(
            clause_id="b-system",
            document="B",
            reference="3.4",
            heading="system under consideration",
            part="2",
        ),
        _clause(
            clause_id="b-system-short",
            document="B",
            reference="3.5",
            heading="system",
            part="2",
        ),
    )

    vocabulary = SubjectCandidateVocabularyBuilder().build((second, first))

    assert [item.normalized_label for item in vocabulary.candidates] == [
        "system",
        "system under consideration",
    ]
    candidate = vocabulary.find(" SYSTEM under consideration ")
    assert candidate is not None
    assert candidate.labels == (
        "system under consideration",
        "System under Consideration",
    )
    assert [item.document_key for item in candidate.provenance] == ["A", "B"]
    assert candidate.provenance[1].reference.part == "2"
    assert vocabulary.analysis.repeated_candidates == 1
    assert vocabulary.analysis.cross_document_candidates == 1


def test_builder_reports_missing_term_headings_without_inventing_candidates() -> None:
    document = _document(
        "STD",
        _clause(
            clause_id="missing",
            document="STD",
            reference="3.1",
            heading=None,
        ),
        _clause(
            clause_id="risk",
            document="STD",
            reference="3.2",
            heading="risk",
        ),
    )

    vocabulary = SubjectCandidateVocabularyBuilder().build((document,))

    assert [item.normalized_label for item in vocabulary.candidates] == ["risk"]
    assert vocabulary.analysis.missing_headings == 1
    assert vocabulary.analysis.extraction_coverage == 0.5


def test_normalization_is_lexical_not_semantic() -> None:
    assert normalize_subject_label("Safety\u2011related   system") == "safety-related system"
    assert normalize_subject_label("System") != normalize_subject_label(
        "system under consideration"
    )
