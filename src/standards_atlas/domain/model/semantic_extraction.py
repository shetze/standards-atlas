"""Auditable ontology-guided semantic knowledge extraction contracts."""

from __future__ import annotations

from typing import Literal

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


class ExtractionViolation(BaseModel):
    """Non-fatal rejected output from ontology-guided extraction."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["undeclared_class", "undeclared_property", "invalid_relation"]
    term: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ClauseSemanticExtraction(BaseModel):
    """Auditable semantic extraction for one source clause."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    ontology_versions: tuple[str, ...]
    entities: tuple[ExtractedEntity, ...] = ()
    relations: tuple[ExtractedRelation, ...] = ()
    violations: tuple[ExtractionViolation, ...] = ()
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


class ExtractionFailure(BaseModel):
    """Non-fatal LLM failure for one source clause."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    kind: Literal["timeout", "response_error", "unavailable"]
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class DocumentSemanticExtraction(BaseModel):
    """Rebuildable extraction artifact kept separate from EngineeringDocument."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    source_document_key: str = Field(min_length=1)
    extraction_version: str = Field(default="1.0.0", min_length=1)
    clauses: tuple[ClauseSemanticExtraction, ...] = ()
    failures: tuple[ExtractionFailure, ...] = ()

    @model_validator(mode="after")
    def clause_ids_are_unique(self) -> DocumentSemanticExtraction:
        ids = [item.clause_id for item in self.clauses]
        if len(ids) != len(set(ids)):
            raise ValueError("semantic extraction may contain each clause only once")
        failure_ids = [item.clause_id for item in self.failures]
        if len(failure_ids) != len(set(failure_ids)):
            raise ValueError("semantic extraction may contain each failed clause only once")
        overlap = set(ids) & set(failure_ids)
        if overlap:
            overlap_ids = sorted(overlap)
            raise ValueError(
                f"semantic extraction clause cannot be both successful and failed: {overlap_ids!r}"
            )
        return self
