from standards_atlas.application.formal_semantics import SemanticExtractionProjectionAugmenter
from standards_atlas.domain.model import (
    ClauseSemanticExtraction,
    DocumentSemanticExtraction,
    ExtractedEntity,
    ExtractionProvenance,
    FormalSemanticProjection,
    SemanticResource,
)


def test_augmenter_adds_entity_assertions_and_epistemic_context() -> None:
    base = FormalSemanticProjection(source_document_key="IEC61508")
    entity = ExtractedEntity(
        id=SemanticResource.stat("entity/test"),
        class_iri=SemanticResource.stat("VerificationActivity"),
        label="verification",
        confidence=0.91,
        evidence="the clause establishes a verification activity",
    )
    extraction = DocumentSemanticExtraction(
        source_document_key="IEC61508",
        clauses=(
            ClauseSemanticExtraction(
                clause_id="C1",
                ontology_versions=("functional-safety@1.1.0",),
                entities=(entity,),
                provenance=ExtractionProvenance(
                    extractor="test",
                    extractor_version="1",
                    model="model-x",
                ),
            ),
        ),
    )
    result = SemanticExtractionProjectionAugmenter().augment(base, extraction)
    assert any(a.subject == entity.id and a.object == entity.class_iri for a in result.assertions)
    assert any(
        facet.predicate == SemanticResource.stat("confidence")
        for context in result.contexts
        for facet in context.facets
    )
