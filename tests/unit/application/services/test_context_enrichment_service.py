from dataclasses import replace
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

    def list(self) -> tuple[EngineeringDocument, ...]:
        return (self.document,)


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
                                "clause_id": "clause-1",
                                "reference": "2.1",
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
    term = Clause(
        id=ClauseId(value="term-software"),
        reference=StandardReference(standard="TEST", year=2026, clause="3.1"),
        clause_type=ClauseType.TERM,
        heading="software",
        content=(TextBlock(id="text-3", text="programs and associated data"),),
        structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST-2026"),
        title="Test standard",
        document_type=DocumentType.STANDARD,
        clauses=(candidate, ordinary, term),
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
    assert result.clauses_enriched == 2
    assert result.subject_clauses == 3
    assert result.subjects_identified == 2
    assert result.subjects_ambiguous == 0
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
    assert clause.context_routing.scopes[0].reaches[0].reference == "TEST:2026 2.1"
    assert clause.context_routing.references[0].target.reference == "TEST:2026 2.1"
    assert clause.context_routing.references[0].role.value == "provides_procedure"
    assert clause.primary_subject is not None
    assert clause.primary_subject.normalized_label == "software"
    assert clause.primary_subject.evidence.kind == "clause_text"
    assert result.document.clauses[1].baseline == document.clauses[1].baseline
    assert result.document.clauses[1].enrichments == document.clauses[1].enrichments
    assert (
        result.document.clauses[1].provenance.availability("enrichments.subject_context") == "known"
    )
    generated = {item.path: item for item in clause.provenance.generated_attributes}
    assert generated["enrichments.subject_context"].method.value == "deterministic"
    assert generated["enrichments.context_routing"].generator == (
        "context-routing-enrichment/context-routing-v1@test-model"
    )
    assert documents.saved == result.document


def test_context_routing_retries_semantically_invalid_structured_response() -> None:
    class InvalidThenValidGateway(_Gateway):
        def generate_structured(self, request):
            result = super().generate_structured(request)
            if len(self.requests) != 1:
                return result
            value = dict(result.value)
            value["scope_declarations"] = [
                {
                    "reaches": [
                        {
                            "kind": "document",
                            "document_key": "TEST-2026",
                            "part": None,
                            "clause_id": None,
                            "reference": "2.1",
                        }
                    ],
                    "conditions": [],
                    "exclusions": [],
                    "qualifications": [],
                    "evidence": ["The following clauses apply to software elements."],
                }
            ]
            return replace(result, value=value)

    gateway = InvalidThenValidGateway()
    document = _document()
    routing = LlmContextRoutingEnricher(
        gateway, prompt=_prompt(), model="test-model", retry_max_tokens=777
    ).enrich(clause=document.clauses[0], document=document)

    assert routing.scopes
    assert len(gateway.requests) == 2
    assert gateway.requests[1].max_tokens == 777
    assert gateway.requests[1].metadata["corrective_retry"] == "routing-invariants-v1"
    assert "previous structured response was unusable" in (
        gateway.requests[1].system_prompt.lower()
    )


def test_context_enrichment_fresh_bypasses_generated_routing_reuse() -> None:
    documents = _Documents(_document())
    gateway = _Gateway()
    first = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="test-model"),
    ).enrich(documents.document.key.value)
    documents.document = first.document

    second = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="test-model"),
        fresh=True,
    ).enrich(documents.document.key.value)

    assert second.routing_reused == 0
    assert len(gateway.requests) == 2


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


def test_context_service_preserves_explicitly_confirmed_empty_results() -> None:
    document = _document()
    clause = document.clauses[0].confirm_authoritative(
        "enrichments.subject_context",
        "enrichments.context_routing",
    )
    document = document.model_copy(update={"clauses": (clause, *document.clauses[1:])})
    result = ContextEnrichmentService(
        documents=_Documents(document),
        enricher=LlmContextRoutingEnricher(_Gateway(), prompt=_prompt(), model="test-model"),
    ).enrich(document.key.value)
    updated = result.document.clauses[0]
    assert updated.enrichments == clause.enrichments
    assert updated.provenance.confirmed_attributes == clause.provenance.confirmed_attributes
    # Refreshing unconfirmed syntactic inputs is independent of protecting the
    # explicitly confirmed (empty) semantic outputs.
    assert updated.reference_mentions != clause.reference_mentions


def test_context_enrichment_reuses_restored_input_identity_without_llm(tmp_path):
    from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
    from standards_atlas.domain.model import Standard

    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    document = Standard.model_validate({**_document().model_dump(), "name": "Test"})
    repository.save(document)
    gateway = _Gateway()
    first = ContextEnrichmentService(
        documents=repository,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="test-model"),
    ).enrich(document.key.value)
    assert len(gateway.requests) == 1
    assert first.routing_reused == 0
    before = {path: path.read_bytes() for path in (tmp_path / "documents").glob("*.json")}
    # Discard all service/repository instances, just as after a restart or import.
    fresh_repository = FileSystemEngineeringDocumentRepository(tmp_path)
    second = ContextEnrichmentService(
        documents=fresh_repository,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="test-model"),
    ).enrich(document.key.value)
    assert second.routing_reused == 1
    assert len(gateway.requests) == 1
    assert second.document == first.document
    assert before == {path: path.read_bytes() for path in before}


def test_changed_routing_model_invalidates_generated_result():
    documents = _Documents(_document())
    gateway = _Gateway()
    first = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="model-a"),
    ).enrich(documents.document.key.value)
    documents.document = first.document
    second = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="model-b"),
    ).enrich(documents.document.key.value)
    assert second.routing_reused == 0
    assert len(gateway.requests) == 2


def test_confirmed_routing_does_not_call_a_model():
    documents = _Documents(_document())
    clause = documents.document.clauses[0].confirm_authoritative("enrichments.context_routing")
    documents.document = documents.document.model_copy(
        update={"clauses": (clause, *documents.document.clauses[1:])}
    )
    gateway = _Gateway()
    result = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="model-a"),
    ).enrich(documents.document.key.value)
    assert result.routing_reused == 1
    assert not gateway.requests
    assert result.document.clauses[0].context_routing == clause.context_routing


def test_llm_annex_reference_is_not_normalized_into_a_self_reference():
    from dataclasses import replace

    class WrongTargetGateway(_Gateway):
        def generate_structured(self, request):
            response = super().generate_structured(request)
            value = dict(response.value)
            value["reference_routings"] = [
                {
                    "target": {
                        "document_key": "TEST-2026",
                        "clause_id": "clause-1",
                        "reference": text,
                        "title": None,
                    },
                    "role": role,
                    "evidence": [evidence],
                }
                for text, role, evidence in (
                    ("this clause", "defines", "Synthetic self reference."),
                    ("Annex G", "provides_exception", "Synthetic Annex G exception."),
                )
            ]
            return replace(response, value=value)

    document = _document()
    annex = Clause(
        id=ClauseId(value="annex-g"),
        reference=StandardReference(standard="TEST", year=2026, clause="G"),
        clause_type=ClauseType.CLAUSE,
    )
    document = document.model_copy(update={"clauses": (*document.clauses, annex)})
    routing = LlmContextRoutingEnricher(WrongTargetGateway(), prompt=_prompt()).enrich(
        clause=document.clauses[0], document=document
    )
    self_edge, annex_edge = routing.references
    assert self_edge.target.clause_id == "clause-1"
    assert self_edge.target.reference == "TEST:2026 1"
    assert annex_edge.source_clause_id == "clause-1"
    assert annex_edge.target.clause_id == "annex-g"
    assert annex_edge.target.reference == "TEST:2026 G"
    assert annex_edge.role.value == "provides_exception"
    assert annex_edge.evidence == ("Synthetic Annex G exception.",)


def test_reused_routing_repairs_wrong_self_id_without_llm_or_provenance_changes():
    documents = _Documents(_document())
    gateway = _Gateway()
    service = ContextEnrichmentService(
        documents=documents,
        enricher=LlmContextRoutingEnricher(gateway, prompt=_prompt(), model="test-model"),
    )
    first = service.enrich(documents.document.key.value)
    source = first.document.clauses[0]
    reference = source.context_routing.references[0]
    broken = source.with_context_routing(
        source.context_routing.model_copy(
            update={
                "references": (
                    reference.model_copy(
                        update={
                            "target": ReferenceTarget(
                                document_key=first.document.key.value,
                                clause_id=source.id.value,
                                reference="2.1",
                            )
                        }
                    ),
                )
            }
        )
    )
    documents.document = first.document.model_copy(
        update={"clauses": (broken, *first.document.clauses[1:])}
    )
    second = service.enrich(documents.document.key.value)
    assert second.routing_reused == 1
    assert len(gateway.requests) == 1
    assert second.document == first.document
    assert second.document.clauses[0].provenance == broken.provenance

    documents.document = second.document
    third = service.enrich(documents.document.key.value)
    assert third.document == second.document
    assert third.routing_reused == 1
    assert len(gateway.requests) == 1


def test_v2_prompt_supplies_deterministic_annex_targets_and_forbids_model_ids():
    from jsonschema import Draft202012Validator

    from standards_atlas.application.services.context_enrichment_service import (
        _is_context_candidate,
    )

    source, other, term = _document().clauses
    source = source.with_baseline_updates(
        content=(TextBlock(id="source", text="See Annex G for this synthetic exception."),),
        reference_mentions=(),
        structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
    )
    annex = other.model_copy(
        update={"reference": other.reference.model_copy(update={"clause": "G"})}
    )
    doc = _document().model_copy(update={"clauses": (source, annex, term)})
    resources = (
        Path(__file__).resolve().parents[4] / "src/standards_atlas/resources/semantic/prompts"
    )
    prompt = PromptRepository(resources).load("context-routing-enrichment", "context-routing-v2")
    enricher = LlmContextRoutingEnricher(_Gateway(), prompt=prompt, model="test")
    request = enricher._request(clause=source, document=doc)
    assert _is_context_candidate(source)
    assert '"source_clause_id": "clause-1"' in request.user_prompt
    assert '"clause_id": "clause-2"' in request.user_prompt
    assert '"reference": "TEST:2026 G"' in request.user_prompt
    answer = {
        "scope_declarations": [],
        "reference_routings": [
            {
                "target": {
                    "document_key": None,
                    "clause_id": None,
                    "reference": "Annex G",
                    "title": None,
                },
                "role": "provides_exception",
                "evidence": ["See Annex G for this synthetic exception."],
            }
        ],
    }
    validator = Draft202012Validator(request.output_schema)
    assert not list(validator.iter_errors(answer))
    answer["reference_routings"][0]["target"]["clause_id"] = "clause-1"
    assert list(validator.iter_errors(answer))

    invalid_document_scope = {
        "scope_declarations": [
            {
                "reaches": [
                    {
                        "kind": "document",
                        "document_key": "TEST-2026",
                        "part": None,
                        "clause_id": None,
                        "reference": "2.1",
                    }
                ],
                "conditions": [],
                "exclusions": [],
                "qualifications": [],
                "evidence": [],
            }
        ],
        "reference_routings": [],
    }
    assert list(validator.iter_errors(invalid_document_scope))

    valid_document_scope = invalid_document_scope.copy()
    valid_document_scope["scope_declarations"] = [
        {
            **invalid_document_scope["scope_declarations"][0],
            "reaches": [
                {
                    "kind": "document",
                    "document_key": "TEST-2026",
                    "part": None,
                    "clause_id": None,
                    "reference": None,
                }
            ],
        }
    ]
    assert not list(validator.iter_errors(valid_document_scope))
