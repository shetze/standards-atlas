from pathlib import Path

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.services.context_enrichment_service import (
    ContextEnrichmentService,
    LlmContextRoutingEnricher,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
    ReferenceTarget,
    ScopeReachKind,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    StructuralContext,
    StructuralNodeKind,
    StructuralScopeMention,
    TextBlock,
)


class _Documents:
    def __init__(self, document: EngineeringDocument) -> None:
        self.document = document
        self.saved: EngineeringDocument | None = None

    def load(self, key: DocumentKey) -> EngineeringDocument:
        assert key == self.document.key
        return self.document

    def save(self, document: EngineeringDocument) -> None:
        self.saved = document


class _Gateway:
    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        return StructuredGenerationResult(
            value={
                "scope_declarations": [
                    {
                        "reaches": [
                            {
                                "kind": "subtree",
                                "document_key": None,
                                "part": None,
                                "clause_id": None,
                                "reference": "2",
                            }
                        ],
                        "conditions": ["for software elements"],
                        "exclusions": [],
                        "qualifications": [],
                        "evidence": ["The following clauses apply to software elements."],
                    }
                ],
                "reference_routings": [
                    {
                        "target": {
                            "document_key": None,
                            "clause_id": "clause-2",
                            "reference": "2.1",
                            "title": None,
                        },
                        "role": "provides_procedure",
                        "evidence": ["in accordance with 2.1"],
                    }
                ],
            },
            model="test-model",
            provider="test",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="output",
            duration_ms=1,
        )


def _prompt():
    resources = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "standards_atlas"
        / "resources"
        / "semantic"
        / "prompts"
    )
    return PromptRepository(resources).load("context-routing-enrichment", "context-routing-v1")


def _document() -> EngineeringDocument:
    semantic = SemanticClassification(statement_functions=(StatementFunction.REQUIREMENT,))
    candidate = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(standard="TEST", year=2026, clause="1"),
        clause_type=ClauseType.SCOPE,
        content=(
            TextBlock(
                id="text-1",
                text=("The following clauses apply to software elements in accordance with 2.1."),
            ),
        ),
        structural_context=StructuralContext(
            node_kind=StructuralNodeKind.LEAF,
            scope_mentions=(
                StructuralScopeMention(
                    source="pattern",
                    surface_text="following clauses",
                    direction_hint="forward",
                    status="detected",
                ),
            ),
        ),
        reference_mentions=(
            ReferenceMention(
                kind=ReferenceMentionKind.CLAUSE,
                surface_text="2.1",
                start_offset=72,
                end_offset=75,
                reference="2.1",
                status=ReferenceResolutionStatus.RESOLVED,
                targets=(ReferenceTarget(clause_id="clause-2", reference="2.1"),),
            ),
        ),
        semantic_classification=semantic,
    )
    ordinary = Clause(
        id=ClauseId(value="clause-2"),
        reference=StandardReference(standard="TEST", year=2026, clause="2.1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="text-2", text="Perform the calculation."),),
        structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST-2026"),
        title="Test standard",
        document_type=DocumentType.STANDARD,
        clauses=(candidate, ordinary),
    )


def test_context_enrichment_only_analyzes_scope_or_reference_candidates() -> None:
    document = _document()
    documents = _Documents(document)
    gateway = _Gateway()
    service = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(
            gateway,
            prompt=_prompt(),
            model="test-model",
            max_tokens=321,
            retry_max_tokens=654,
        ),
    )

    result = service.enrich(document.key.value)

    assert result.candidates == 1
    assert result.clauses_enriched == 1
    assert result.context_enrichment_failures == 0
    assert len(gateway.requests) == 1
    assert gateway.requests[0].task == "context-routing-enrichment"
    assert gateway.requests[0].prompt_version == "context-routing-v1"
    assert gateway.requests[0].model == "test-model"
    assert gateway.requests[0].max_tokens == 321
    assert "statement function" in gateway.requests[0].system_prompt.lower()

    clause = result.document.clauses[0]
    assert clause.semantic_classification == document.clauses[0].semantic_classification
    assert clause.context_routing.scopes[0].reaches[0].kind == ScopeReachKind.SUBTREE
    assert clause.context_routing.references[0].role.value == "provides_procedure"
    assert result.document.clauses[1] == document.clauses[1]
    generated = {item.path: item for item in clause.provenance.generated_attributes}
    assert generated["enrichments.context_routing"].generator == (
        "context-routing-enrichment/context-routing-v1@test-model"
    )
    assert documents.saved == result.document


def test_context_prompt_contract_excludes_qualification_targets_from_schema() -> None:
    prompt = _prompt()
    schema_text = str(prompt.output_schema)

    assert "statement_functions" not in schema_text
    assert "knowledge_kinds" not in schema_text
    assert "applicability_functions" not in schema_text
    assert "role_relations" not in schema_text
    assert set(prompt.output_schema["properties"]) == {
        "scope_declarations",
        "reference_routings",
    }
