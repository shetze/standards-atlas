from collections.abc import Mapping

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
        self.semantic_context: Mapping[str, object] | None = None

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        semantic_context: Mapping[str, object] | None = None,
    ) -> ClauseSemanticExtraction:
        self.seen_clause = clause
        self.semantic_context = semantic_context
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
    assert extractor.seen_clause is clause
    assert extractor.semantic_context is not None
    assert extractor.semantic_context["knowledge_kinds"] == [KnowledgeKind.PROCESS.value]


def test_llm_timeout_is_recorded_and_next_clause_continues() -> None:
    from standards_atlas.application.ports.llm_gateway import LlmTimeoutError
    from standards_atlas.application.semantic_extraction import ExtractionProgress

    clauses = tuple(
        Clause(
            id=ClauseId(value=f"clause-{index}"),
            reference=StandardReference(standard="TEST", year=2026, clause=str(index)),
            clause_type=ClauseType.CLAUSE,
            heading=f"Clause {index}",
        )
        for index in (1, 2)
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )

    class _TimeoutThenSuccessExtractor:
        def extract(
            self,
            clause: Clause,
            *,
            document_key: str,
            ontology_versions: tuple[str, ...],
            semantic_context: Mapping[str, object] | None = None,
        ) -> ClauseSemanticExtraction:
            if clause.id.value == "clause-1":
                raise LlmTimeoutError("timed out")
            return ClauseSemanticExtraction(
                clause_id=clause.id.value,
                ontology_versions=ontology_versions,
                provenance=ExtractionProvenance(extractor="test", extractor_version="1"),
            )

    events: list[ExtractionProgress] = []
    extraction = SemanticExtractionService(_TimeoutThenSuccessExtractor()).extract_document(
        document,
        ontology_versions=("standards-atlas-core@1.1.0",),
        clause_ids=frozenset({"clause-1", "clause-2"}),
        eligibility_by_clause={
            clause.id.value: ExtractionEligibilityContext(
                knowledge_kinds=(KnowledgeKind.PROCESS,),
            )
            for clause in clauses
        },
        progress=events.append,
    )

    assert [item.clause_id for item in extraction.clauses] == ["clause-2"]
    assert len(extraction.failures) == 1
    assert extraction.failures[0].clause_id == "clause-1"
    assert extraction.failures[0].kind == "timeout"
    assert extraction.failures[0].clause_reference == "TEST:2026 1"
    assert extraction.failures[0].clause_title == "Clause 1"
    assert [(item.clause_id, item.phase, item.status) for item in events] == [
        ("clause-1", "started", None),
        ("clause-1", "finished", "timeout"),
        ("clause-2", "started", None),
        ("clause-2", "finished", "ok"),
    ]
    assert {item.clause_reference for item in events} == {"TEST:2026 1", "TEST:2026 2"}
