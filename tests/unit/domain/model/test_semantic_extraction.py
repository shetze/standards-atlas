import pytest

from standards_atlas.domain.model import (
    ClauseSemanticExtraction,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionProvenance,
    SemanticResource,
)


def _entity(local: str) -> ExtractedEntity:
    return ExtractedEntity(
        id=SemanticResource.stat(f"entity/{local}"),
        class_iri=SemanticResource.stat("Activity"),
        label=local,
        confidence=0.9,
        evidence="semantic rationale",
    )


def test_relations_must_reference_entities_from_same_extraction() -> None:
    entity = _entity("a")
    with pytest.raises(ValueError, match="unknown extracted entities"):
        ClauseSemanticExtraction(
            clause_id="C1",
            ontology_versions=("standards-atlas-core@1.1.0",),
            entities=(entity,),
            relations=(
                ExtractedRelation(
                    subject_id=entity.id,
                    predicate=SemanticResource.stat("requires"),
                    object_id=SemanticResource.stat("entity/missing"),
                    confidence=0.8,
                    evidence="semantic rationale",
                ),
            ),
            provenance=ExtractionProvenance(extractor="test", extractor_version="1"),
        )


def test_cross_domain_equivalence_is_outside_extraction_contract() -> None:
    with pytest.raises(ValueError, match="outside Slice 4"):
        ExtractedRelation(
            subject_id=SemanticResource.stat("entity/a"),
            predicate=SemanticResource.stat("equivalentTo"),
            object_id=SemanticResource.stat("entity/b"),
            confidence=0.5,
            evidence="semantic rationale",
        )
