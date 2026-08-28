from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.semantic_classification import (
    SemanticDimensionResult,
    SemanticProfile,
)
from standards_atlas.application.semantic_ontology import OntologyReference
from standards_atlas.application.services import SemanticEnrichmentService
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    KnowledgeKind,
    NormativeStatus,
    ProcessFunction,
    RoleRelation,
    RoleRelationType,
    SemanticClassification,
    StandardReference,
    StatementFunction,
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
        return (SemanticDimensionResult(dimension="statement_functions", values=("requirement",)),)


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
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_Engine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
        role_semantics=_FailingRoleSemantics(),
    )

    result = service.enrich(document.key.value)

    assert result.clauses_enriched == 1
    assert result.role_semantics_failures == 1
    assert result.document.clauses[0].semantic_classification.statement_functions[0].value == (
        "requirement"
    )
    clause = result.document.clauses[0]
    assert clause.semantic_classification.role_semantics_present is False
    generated = {item.path: item for item in clause.provenance.generated_attributes}
    statement = generated["enrichments.semantic.statement_functions"]
    assert statement.method.value == "llm"
    assert statement.generator
    assert documents.saved == result.document


class _FailingEngine:
    def classify(self, **_kwargs):
        raise LlmResponseError("invalid ontology response", finish_reason="length")


class _SuccessfulRoleSemantics:
    def classify(self, _context):
        from standards_atlas.application.semantic_ontology import RoleSemanticsResult

        return RoleSemanticsResult(present=False)


def test_ontology_response_failure_isolated_to_clause_and_reported() -> None:
    document = _document()
    documents = _Documents(document)
    progress = []
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_FailingEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
        role_semantics=_SuccessfulRoleSemantics(),
        progress=progress.append,
    )

    result = service.enrich(document.key.value)

    assert result.clauses_enriched == 0
    assert result.semantic_classification_failures == 1
    assert result.role_semantics_failures == 0
    assert result.document.clauses[0].semantic_classification.statement_functions == ()
    assert [event.state for event in progress] == ["started", "partial"]
    assert progress[-1].clause_reference == "1"
    assert documents.saved == result.document


class _ApplicabilityEngine:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = values

    def classify(self, **_kwargs):
        return (
            SemanticDimensionResult(
                dimension="applicability_functions",
                values=self._values,
            ),
        )


def _document_with_semantic(semantic: SemanticClassification) -> EngineeringDocument:
    document = _document()
    clause = document.clauses[0].with_semantic_classification(semantic)
    return document.model_copy(update={"clauses": (clause,)})


def test_applicability_dimension_is_replaced_atomically_when_present() -> None:
    document = _document_with_semantic(SemanticClassification())
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_ApplicabilityEngine(("inclusion",)),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "applicability_functions": OntologyReference(
                    id="applicability-functions", version="2.0.0"
                )
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.applicability_present is True
    assert semantic.applicability_functions == (ApplicabilityFunction.INCLUSION,)


def test_applicability_dimension_is_replaced_atomically_when_absent() -> None:
    document = _document_with_semantic(
        SemanticClassification(
            applicability_present=True,
            applicability_functions=(ApplicabilityFunction.INCLUSION,),
        )
    )
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_ApplicabilityEngine(()),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "applicability_functions": OntologyReference(
                    id="applicability-functions", version="2.0.0"
                )
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.applicability_present is False
    assert semantic.applicability_functions == ()


def test_fail_soft_ontology_failure_preserves_complete_applicability_dimension() -> None:
    initial = SemanticClassification(
        applicability_present=True,
        applicability_functions=(ApplicabilityFunction.INCLUSION,),
    )
    document = _document_with_semantic(initial)
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_FailingEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "applicability_functions": OntologyReference(
                    id="applicability-functions", version="2.0.0"
                )
            },
        ),
    )

    result = service.enrich(document.key.value)

    assert result.document.clauses[0].semantic_classification == initial


class _AbsentRoleSemantics:
    def classify(self, _context):
        from standards_atlas.application.semantic_ontology import RoleSemanticsResult

        return RoleSemanticsResult(present=False)


def test_role_dimension_is_replaced_atomically_when_presence_turns_false() -> None:
    relation = RoleRelation(
        actor="Verifier",
        relation_class="performance",
        target="verification",
    )
    initial = SemanticClassification(
        role_semantics_present=True,
        role_relation_types=(RoleRelationType.VERIFIES,),
        role_relations=(relation,),
    )
    document = _document_with_semantic(initial)
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_Engine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
        role_semantics=_AbsentRoleSemantics(),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.role_semantics_present is False
    assert semantic.role_relation_types == ()
    assert semantic.role_relations == ()


class _PresenceOnlyApplicabilityEngine:
    def classify(self, **_kwargs):
        return (
            SemanticDimensionResult(
                dimension="applicability_functions",
                values=(),
                presence=True,
            ),
        )


def test_applicability_presence_is_persisted_independently_from_subtype() -> None:
    document = _document()
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_PresenceOnlyApplicabilityEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "applicability_functions": OntologyReference(
                    id="applicability-functions", version="1.2.0"
                )
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.applicability_present is True
    assert semantic.applicability_functions == ()


class _DuplicateDimensionsEngine:
    def classify(self, **_kwargs):
        return (
            SemanticDimensionResult(
                dimension="statement_functions",
                values=("requirement", "requirement"),
            ),
            SemanticDimensionResult(
                dimension="knowledge_kinds",
                values=("process", "process"),
            ),
            SemanticDimensionResult(
                dimension="process_functions",
                values=("activity", "activity", "decision"),
            ),
            SemanticDimensionResult(
                dimension="applicability_functions",
                values=("inclusion", "inclusion"),
            ),
        )


def test_set_like_semantic_dimensions_are_deduplicated_before_validation() -> None:
    document = _document()
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_DuplicateDimensionsEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.statement_functions == (StatementFunction.REQUIREMENT,)
    assert semantic.knowledge_kinds == (KnowledgeKind.PROCESS,)
    assert semantic.process_functions == (
        ProcessFunction.ACTIVITY,
        ProcessFunction.DECISION,
    )
    assert semantic.applicability_functions == (ApplicabilityFunction.INCLUSION,)
    assert semantic.applicability_present is True


def test_existing_duplicate_semantic_values_are_canonicalized_during_merge() -> None:
    existing = SemanticClassification.model_construct(
        statement_functions=(StatementFunction.REQUIREMENT, StatementFunction.REQUIREMENT),
        knowledge_kinds=(),
        process_functions=(ProcessFunction.ACTIVITY, ProcessFunction.ACTIVITY),
        applicability_present=False,
        applicability_functions=(),
        role_semantics_present=False,
        role_relation_types=(),
        role_relations=(),
        document_structure=None,
        normative_status=NormativeStatus.UNSPECIFIED,
        domain_functions=(),
        relations=(),
    )
    document = _document_with_semantic(existing)
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_FailingEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert result.semantic_classification_failures == 1
    assert semantic.statement_functions == (StatementFunction.REQUIREMENT,)
    assert semantic.process_functions == (ProcessFunction.ACTIVITY,)


def test_existing_duplicate_role_relations_are_canonicalized_during_merge() -> None:
    relation = RoleRelation(
        actor="Verifier",
        relation_class="performance",
        target="verification",
    )
    existing = SemanticClassification.model_construct(
        statement_functions=(),
        knowledge_kinds=(),
        process_functions=(),
        applicability_present=False,
        applicability_functions=(),
        role_semantics_present=True,
        role_relation_types=(RoleRelationType.VERIFIES, RoleRelationType.VERIFIES),
        role_relations=(relation, relation),
        document_structure=None,
        normative_status=NormativeStatus.UNSPECIFIED,
        domain_functions=(),
        relations=(),
    )
    document = _document_with_semantic(existing)
    documents = _Documents(document)
    service = SemanticEnrichmentService(
        documents=documents,
        engine=_FailingEngine(),
        profile=SemanticProfile(
            id="test",
            version="1.0.0",
            dimensions={
                "statement_functions": OntologyReference(id="statement-functions", version="2.0.0")
            },
        ),
    )

    result = service.enrich(document.key.value)
    semantic = result.document.clauses[0].semantic_classification

    assert semantic.role_relation_types == (RoleRelationType.VERIFIES,)
    assert len(semantic.role_relations) == 1
    assert semantic.role_relations[0].actor == relation.actor
    assert semantic.role_relations[0].relation_class == relation.relation_class
    assert semantic.role_relations[0].target == relation.target
