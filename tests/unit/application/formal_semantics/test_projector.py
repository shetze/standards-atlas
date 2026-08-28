from __future__ import annotations

from standards_atlas.application.formal_semantics import DeterministicFormalSemanticProjector
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    DomainFunctionClassification,
    EngineeringDocument,
    NormativeStatus,
    RelationScope,
    SemanticBox,
    SemanticClassification,
    SemanticRelation,
    SemanticRelationKind,
    StandardReference,
    StatementFunction,
    StructuralContext,
    StructuralNodeKind,
    StructuralSiblingContext,
)


def _document() -> EngineeringDocument:
    first = Clause(
        id=ClauseId(value="clause:1"),
        reference=StandardReference(standard="EXAMPLE", year=2026, clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        semantic_classification=SemanticClassification(
            statement_functions=(StatementFunction.REQUIREMENT,),
            applicability_present=True,
            applicability_functions=(ApplicabilityFunction.APPLICABILITY_CONDITION,),
            normative_status=NormativeStatus.NORMATIVE,
            domain_functions=(
                DomainFunctionClassification(
                    knowledge_domain="functional-safety",
                    taxonomy_version="2.0.0",
                    functions=("verification",),
                ),
            ),
        ),
        reference_relations=(
            SemanticRelation(
                kind=SemanticRelationKind.REFINES,
                scope=RelationScope.INTERNAL,
                target_reference="2",
                target_clause_id="clause:2",
            ),
        ),
        structural_context=StructuralContext(
            node_kind=StructuralNodeKind.LEAF,
            sibling=StructuralSiblingContext(
                index=0,
                count=2,
                is_first=True,
                is_last=False,
                next_clause_id="clause:2",
            ),
        ),
    )
    second = Clause(
        id=ClauseId(value="clause:2"),
        reference=StandardReference(standard="EXAMPLE", year=2026, clause="2"),
        clause_type=ClauseType.CLAUSE,
        parent_id=ClauseId(value="clause:1"),
        structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
    )
    return EngineeringDocument(
        key=DocumentKey(value="EXAMPLE-2026"),
        title="Example standard",
        document_type=DocumentType.STANDARD,
        year=2026,
        clauses=(first, second),
    )


def test_projector_creates_deterministic_abox_and_cbox_projection() -> None:
    projector = DeterministicFormalSemanticProjector()
    first = projector.project(_document(), knowledge_domains=("functional-safety",))
    second = projector.project(_document(), knowledge_domains=("functional-safety",))

    assert first == second
    assert first.projection_version == "1.0.0"
    assert first.ontology_versions == (
        "standards-atlas-core@1.1.0",
        "functional-safety@1.1.0",
    )
    assert first.contexts
    assert all(assertion.box is SemanticBox.ABOX for assertion in first.assertions)


def test_projector_preserves_structure_relations_without_clause_text() -> None:
    projection = DeterministicFormalSemanticProjector().project(_document())
    predicates = {assertion.predicate.iri.rsplit("#", 1)[-1] for assertion in projection.assertions}

    assert "containsClause" in predicates
    assert "hasParentClause" in predicates
    assert "precedesClause" in predicates
    assert "refines" in predicates
    payload = projection.model_dump_json()
    assert "Example standard" in payload
    assert "protected clause text" not in payload


def test_context_projects_taxonomy_and_structural_information() -> None:
    projection = DeterministicFormalSemanticProjector().project(_document())
    first = projection.contexts[0]
    values = {
        (facet.predicate.iri.rsplit("#", 1)[-1], getattr(facet.value, "value", None))
        for facet in first.facets
    }
    assert ("statementFunction", "requirement") in values
    assert ("applicabilityPresent", True) in values
    assert ("normativeStatus", "normative") in values
    assert ("nodeKind", "leaf") in values
    assert ("taxonomyVersion", "functional-safety@2.0.0") in values
