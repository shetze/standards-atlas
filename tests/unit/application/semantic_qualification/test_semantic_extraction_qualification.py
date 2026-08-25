from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    SemanticExtractionQualificationConfig,
    qualify_semantic_extractions,
)
from standards_atlas.domain.model import (
    ClauseSemanticExtraction,
    DocumentSemanticExtraction,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionProvenance,
    SemanticResource,
)


def test_semantic_extraction_qualification_scores_ontology_conformance() -> None:
    entity_a = ExtractedEntity(
        id=SemanticResource.stat("entity/a"),
        class_iri=SemanticResource.stat("EngineeringConcept"),
        label="verification",
        confidence=0.9,
        evidence="engineering concept",
    )
    entity_b = ExtractedEntity(
        id=SemanticResource.stat("entity/b"),
        class_iri=SemanticResource.stat("Activity"),
        label="verify",
        confidence=0.8,
        evidence="activity",
    )
    relation = ExtractedRelation(
        subject_id=entity_a.id,
        predicate=SemanticResource.stat("requires"),
        object_id=entity_b.id,
        confidence=0.85,
        evidence="requires verification",
    )
    extraction = DocumentSemanticExtraction(
        source_document_key="doc",
        clauses=(
            ClauseSemanticExtraction(
                clause_id="c1",
                ontology_versions=("standards-atlas-core@1.1.0",),
                entities=(entity_a, entity_b),
                relations=(relation,),
                provenance=ExtractionProvenance(extractor="test", extractor_version="1.0.0"),
            ),
        ),
    )
    report = qualify_semantic_extractions(
        (extraction,),
        SemanticExtractionQualificationConfig(
            ontology_versions=(
                "standards-atlas-core@1.1.0",
                "functional-safety@1.1.0",
            )
        ),
    )
    assert report.documents == 1
    assert report.clauses == 1
    assert report.ontology_conformance == 1.0
    assert report.gold_available is False
    assert report.entity_f1 is None
