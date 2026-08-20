from standards_atlas.application.routing import (
    AlwaysMatcher,
    RoutingContract,
    RoutingDisposition,
    RoutingRule,
    RoutingTaskReference,
)
from standards_atlas.application.services.semantic_routing_service import SemanticRoutingService
from standards_atlas.application.services.structural_taxonomy_service import (
    StructuralTaxonomyService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


class _DocumentRepository:
    def __init__(self, document: EngineeringDocument) -> None:
        self.document = document

    def load(self, key: DocumentKey) -> EngineeringDocument:
        return self.document

    def save(self, document: EngineeringDocument) -> None:
        self.document = document


class _ContractRepository:
    def load(self, contract_id: str, version: str) -> RoutingContract:
        assert (contract_id, version) == ("test-routing", "1.0.0")
        return RoutingContract(
            id=contract_id,
            version=version,
            tasks=(RoutingTaskReference(id="semantic-profile-classification", version="2.2.0"),),
            rules=(
                RoutingRule(
                    id="required",
                    task="semantic-profile-classification",
                    effect=RoutingDisposition.REQUIRED,
                    when=AlwaysMatcher(),
                ),
            ),
        )


class _ArtifactRepository:
    def __init__(self) -> None:
        self.artifact = None

    def save(self, artifact) -> None:
        self.artifact = artifact

    def load(self, document_key: str, contract_id: str, contract_version: str):
        return self.artifact


def _document() -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        title="Scope",
        content=(TextBlock(id="text-1", text="This document specifies requirements."),),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_routes_taxonomy_signals_and_persists_separate_artifact() -> None:
    documents = _DocumentRepository(_document())
    StructuralTaxonomyService(documents).classify("TEST")
    artifacts = _ArtifactRepository()
    service = SemanticRoutingService(
        documents=documents,
        contracts=_ContractRepository(),
        artifacts=artifacts,
    )

    result = service.route(
        "TEST",
        contract_id="test-routing",
        contract_version="1.0.0",
    )

    assert result.clauses_routed == 1
    assert result.task_decisions == 1
    record = result.artifact.clauses[0]
    assert record.signals.canonical_section == "scope"
    assert record.signals.node_kind == "leaf"
    assert record.signals.content_profile == "text_dominant"
    assert record.plan.decisions[0].disposition is RoutingDisposition.REQUIRED
    assert artifacts.artifact == result.artifact
    assert documents.document.clauses[0].semantic_classification.role_relation_types == ()


def test_requires_structural_taxonomy_before_routing() -> None:
    documents = _DocumentRepository(_document())
    service = SemanticRoutingService(
        documents=documents,
        contracts=_ContractRepository(),
        artifacts=_ArtifactRepository(),
    )

    try:
        service.route("TEST", contract_id="test-routing", contract_version="1.0.0")
    except ValueError as exc:
        assert "run classify-taxonomy first" in str(exc)
    else:
        raise AssertionError("routing without taxonomy must fail")
