"""Auditable ontology-guided semantic knowledge extraction contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .formal_semantics import FORMAL_SEMANTIC_NAMESPACE, SemanticResource

_FORBIDDEN_CROSS_DOMAIN_PREDICATES = {
    f"{FORMAL_SEMANTIC_NAMESPACE}equivalentTo",
    f"{FORMAL_SEMANTIC_NAMESPACE}closeMatch",
    f"{FORMAL_SEMANTIC_NAMESPACE}exactMatch",
    f"{FORMAL_SEMANTIC_NAMESPACE}broadMatch",
    f"{FORMAL_SEMANTIC_NAMESPACE}narrowMatch",
    f"{FORMAL_SEMANTIC_NAMESPACE}relatedMatch",
}


class ExtractionProvenance(BaseModel):
    """Reproducibility metadata for one extraction result."""

    model_config = ConfigDict(frozen=True)

    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    input_hash: str | None = None
    raw_response_hash: str | None = None


class ExtractedEntity(BaseModel):
    """One engineering entity grounded in the formal ontology vocabulary."""

    model_config = ConfigDict(frozen=True)

    id: SemanticResource
    class_iri: SemanticResource
    label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def class_uses_stat_namespace(self) -> ExtractedEntity:
        if not self.class_iri.iri.startswith(FORMAL_SEMANTIC_NAMESPACE):
            raise ValueError("extracted entity classes must use the canonical stat namespace")
        return self


class ExtractedRelation(BaseModel):
    """One ontology-grounded relation between extracted entities."""

    model_config = ConfigDict(frozen=True)

    subject_id: SemanticResource
    predicate: SemanticResource
    object_id: SemanticResource
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def relation_is_local_and_ontology_grounded(self) -> ExtractedRelation:
        if not self.predicate.iri.startswith(FORMAL_SEMANTIC_NAMESPACE):
            raise ValueError("extracted relation predicates must use the canonical stat namespace")
        if self.predicate.iri in _FORBIDDEN_CROSS_DOMAIN_PREDICATES:
            raise ValueError("cross-domain mapping relations are outside Slice 4")
        return self


class ClauseSemanticExtraction(BaseModel):
    """Auditable semantic extraction for one source clause."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    ontology_versions: tuple[str, ...]
    entities: tuple[ExtractedEntity, ...] = ()
    relations: tuple[ExtractedRelation, ...] = ()
    provenance: ExtractionProvenance

    @model_validator(mode="after")
    def relations_reference_known_entities(self) -> ClauseSemanticExtraction:
        known = {entity.id.iri for entity in self.entities}
        missing = {
            resource.iri
            for relation in self.relations
            for resource in (relation.subject_id, relation.object_id)
            if resource.iri not in known
        }
        if missing:
            raise ValueError(f"relations reference unknown extracted entities: {sorted(missing)!r}")
        return self


class DocumentSemanticExtraction(BaseModel):
    """Rebuildable extraction artifact kept separate from EngineeringDocument."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    source_document_key: str = Field(min_length=1)
    extraction_version: str = Field(default="1.0.0", min_length=1)
    clauses: tuple[ClauseSemanticExtraction, ...] = ()

    @model_validator(mode="after")
    def clause_ids_are_unique(self) -> DocumentSemanticExtraction:
        ids = [item.clause_id for item in self.clauses]
        if len(ids) != len(set(ids)):
            raise ValueError("semantic extraction may contain each clause only once")
        return self
