from __future__ import annotations

from standards_atlas.adapters.filesystem.formal_semantic_projection_repository import (
    FileSystemFormalSemanticProjectionRepository,
)
from standards_atlas.domain.model import FormalSemanticProjection


def test_projection_repository_round_trips_versioned_payload(tmp_path) -> None:
    repository = FileSystemFormalSemanticProjectionRepository(tmp_path)
    projection = FormalSemanticProjection(
        source_document_key="ISO/EXAMPLE:2026",
        projection_version="1.0.0",
        ontology_versions=("standards-atlas-core@2.0.0",),
    )

    repository.save(projection)

    assert repository.load("ISO/EXAMPLE:2026") == projection
    assert repository.load("missing") is None


def test_engineering_document_and_projection_roundtrip_keep_evidence_resolvable(tmp_path) -> None:
    import hashlib

    from standards_atlas.adapters.filesystem.document_repository import (
        FileSystemEngineeringDocumentRepository,
    )
    from standards_atlas.application.formal_semantics import (
        DeterministicFormalSemanticProjector,
        FormalEvidenceResolutionStatus,
        FormalProjectionEvidenceResolver,
    )
    from standards_atlas.domain.model import (
        Clause,
        ClauseId,
        ClauseType,
        DocumentKey,
        DocumentKnowledge,
        DocumentType,
        EngineeringDocument,
        EvidenceAnchor,
        EvidenceSourceKind,
        KnowledgeEntity,
        StandardReference,
        TextBlock,
    )

    text = "Plan requirement"
    heading = "Plan"
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        heading=heading,
        content=(TextBlock(id="body", text=text),),
    )
    body_anchor = EvidenceAnchor(
        id="anchor-body",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=4,
        content_hash=hashlib.sha256(b"Plan").hexdigest(),
    )
    heading_anchor = EvidenceAnchor(
        id="anchor-heading",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=4,
        content_hash=hashlib.sha256(b"Plan").hexdigest(),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Synthetic evidence roundtrip",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
        knowledge=DocumentKnowledge(
            ontology_versions=("standards-atlas-core@2.0.0",),
            evidence_anchors=(body_anchor, heading_anchor),
            entities=(
                KnowledgeEntity(
                    id="work-product",
                    class_iri="http://lunetix.org/standards-atlas#WorkProduct",
                    normalized_label="plan",
                    source_anchor_ids=(body_anchor.id, heading_anchor.id),
                ),
            ),
        ),
    )
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(document)
    reloaded_document = documents.load(document.key)

    projection = DeterministicFormalSemanticProjector().project(reloaded_document)
    projections = FileSystemFormalSemanticProjectionRepository(tmp_path)
    projections.save(projection)
    reloaded_projection = projections.load(document.key.value)
    assert reloaded_projection is not None

    resolver = FormalProjectionEvidenceResolver(reloaded_document, reloaded_projection)
    evidence_assertion = next(
        item
        for item in reloaded_projection.assertions
        if item.evidence_ids == ("anchor-body", "anchor-heading")
    )
    resolutions = resolver.resolve_assertion_evidence(evidence_assertion)

    assert [item.evidence_id for item in resolutions] == ["anchor-body", "anchor-heading"]
    assert all(item.status is FormalEvidenceResolutionStatus.RESOLVED for item in resolutions)
    assert [item.anchor.source_kind for item in resolutions if item.anchor is not None] == [
        EvidenceSourceKind.BODY,
        EvidenceSourceKind.HEADING,
    ]
