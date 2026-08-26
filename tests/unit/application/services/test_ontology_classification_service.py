from standards_atlas.application.ontology import (
    OntologyDimensionResult,
    OntologyProfile,
    OntologyReference,
)
from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.services import OntologyClassificationService
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
    TextBlock,
)


class _Documents:
    def __init__(self, document: EngineeringDocument) -> None:
        self.document = document
        self.saved = None

    def load(self, key: DocumentKey) -> EngineeringDocument:
        assert key == self.document.key
        return self.document

    def save(self, document: EngineeringDocument) -> None:
        self.saved = document


class _Engine:
    def classify(self, **_kwargs):
        return (OntologyDimensionResult(dimension="statement_functions", values=("requirement",)),)


class _FailingRoleSemantics:
    def classify(self, _context):
        raise LlmResponseError("invalid role semantics response", finish_reason="length")


def _document() -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(standard="TEST", year=2026, clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="text-1", text="The design shall be verified."),),
        structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST-2026"),
        title="Test standard",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_role_response_failure_does_not_abort_other_ontology_dimensions() -> None:
    document = _document()
    documents = _Documents(document)
    service = OntologyClassificationService(
        documents=documents,
        engine=_Engine(),
        profile=OntologyProfile(
            id="test",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
        role_semantics=_FailingRoleSemantics(),
    )

    result = service.classify(document.key.value)

    assert result.clauses_classified == 1
    assert result.role_semantics_failures == 1
    assert result.document.clauses[0].semantic_classification.statement_functions[0].value == (
        "requirement"
    )
    assert result.document.clauses[0].semantic_classification.role_semantics_present is False
    assert documents.saved == result.document


class _FailingEngine:
    def classify(self, **_kwargs):
        raise LlmResponseError("invalid ontology response", finish_reason="length")


class _SuccessfulRoleSemantics:
    def classify(self, _context):
        from standards_atlas.application.ontology import RoleSemanticsResult

        return RoleSemanticsResult(present=False)


def test_ontology_response_failure_isolated_to_clause_and_reported() -> None:
    document = _document()
    documents = _Documents(document)
    progress = []
    service = OntologyClassificationService(
        documents=documents,
        engine=_FailingEngine(),
        profile=OntologyProfile(
            id="test",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
        role_semantics=_SuccessfulRoleSemantics(),
        progress=progress.append,
    )

    result = service.classify(document.key.value)

    assert result.clauses_classified == 0
    assert result.ontology_classification_failures == 1
    assert result.role_semantics_failures == 0
    assert result.document.clauses[0].semantic_classification.statement_functions == ()
    assert [event.state for event in progress] == ["started", "partial"]
    assert progress[-1].clause_reference == "1"
    assert documents.saved == result.document
