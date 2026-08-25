from __future__ import annotations

import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import (
    FORMAL_SEMANTIC_NAMESPACE,
    ContextFacet,
    ContextFrame,
    ContextKind,
    FormalAssertion,
    FormalSemanticProjection,
    SemanticBox,
    SemanticLiteral,
    SemanticResource,
)


def test_stat_resource_uses_stable_namespace() -> None:
    resource = SemanticResource.stat("Clause")
    assert resource.iri == f"{FORMAL_SEMANTIC_NAMESPACE}Clause"
    assert FORMAL_SEMANTIC_NAMESPACE == "http://lunetix.org/standards-atlas#"


def test_context_frame_can_combine_semantic_structural_and_epistemic_facets() -> None:
    context = ContextFrame(
        id=SemanticResource.stat("context/clause-1"),
        facets=(
            ContextFacet(
                kind=ContextKind.SEMANTIC,
                predicate=SemanticResource.stat("knowledgeDomain"),
                value=SemanticResource.stat("FunctionalSafety"),
                source="knowledge-domain",
            ),
            ContextFacet(
                kind=ContextKind.STRUCTURAL,
                predicate=SemanticResource.stat("nodeKind"),
                value=SemanticLiteral(value="leaf"),
                source="structural-taxonomy",
            ),
            ContextFacet(
                kind=ContextKind.EPISTEMIC,
                predicate=SemanticResource.stat("taxonomyVersion"),
                value=SemanticLiteral(value="1.0.0"),
                source="taxonomy",
            ),
        ),
    )
    assert {facet.kind for facet in context.facets} == set(ContextKind)


def test_tbox_and_rbox_axioms_cannot_depend_on_instance_context() -> None:
    with pytest.raises(ValidationError, match="TBox/RBox"):
        FormalAssertion(
            id=SemanticResource.stat("axiom/1"),
            box=SemanticBox.TBOX,
            subject=SemanticResource.stat("VerificationActivity"),
            predicate=SemanticResource.stat("subClassOf"),
            object=SemanticResource.stat("AssuranceActivity"),
            context_ids=(SemanticResource.stat("context/1"),),
        )


def test_projection_rejects_unknown_context_references() -> None:
    assertion = FormalAssertion(
        id=SemanticResource.stat("assertion/1"),
        box=SemanticBox.ABOX,
        subject=SemanticResource.stat("clause/1"),
        predicate=SemanticResource.stat("appliesTo"),
        object=SemanticResource.stat("SIL2"),
        context_ids=(SemanticResource.stat("context/missing"),),
    )
    with pytest.raises(ValidationError, match="unknown contexts"):
        FormalSemanticProjection(source_document_key="IEC61508", assertions=(assertion,))
