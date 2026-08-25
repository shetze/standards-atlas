from standards_atlas.application.semantic_extraction import (
    ExtractionEligibilityContext,
    SemanticExtractionService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseSemanticExtraction,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ExtractionProvenance,
    KnowledgeKind,
    StandardReference,
)


class _CapturingExtractor:
    def __init__(self) -> None:
        self.seen_clause: Clause | None = None

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
    ) -> ClauseSemanticExtraction:
        self.seen_clause = clause
        return ClauseSemanticExtraction(
            clause_id=clause.id.value,
            ontology_versions=ontology_versions,
            provenance=ExtractionProvenance(extractor="test", extractor_version="1"),
        )


def test_qualification_context_can_admit_unclassified_engineering_clause() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )
    extractor = _CapturingExtractor()

    extraction = SemanticExtractionService(extractor).extract_document(
        document,
        ontology_versions=("standards-atlas-core@1.1.0",),
        clause_ids=frozenset({"clause-1"}),
        eligibility_by_clause={
            "clause-1": ExtractionEligibilityContext(
                knowledge_kinds=(KnowledgeKind.PROCESS,),
            )
        },
    )

    assert [item.clause_id for item in extraction.clauses] == ["clause-1"]
    assert clause.semantic_classification.knowledge_kinds == ()
    assert extractor.seen_clause is not None
    assert extractor.seen_clause.semantic_classification.knowledge_kinds == (KnowledgeKind.PROCESS,)
